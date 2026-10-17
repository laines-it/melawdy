from datetime import datetime, timedelta, timezone
import io
from types import SimpleNamespace
from unittest.mock import Mock

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException, Response
import pytest
from starlette.requests import Request

from backend import auth
from backend.models import User, UserType


def request():
    return Request({"type": "http", "method": "POST", "path": "/api/v1/auth/login", "headers": []})


def test_migration_chain_contains_the_existing_main_database_revision():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert set(script.get_heads()) == {"0008_template_constructor", "0007_e5_embeddings"}
    revisions = {revision.revision for revision in script.walk_revisions()}
    assert {"0001_initial", "0006_user_favorites", "0007_login_attempt_window",
            "0008_template_constructor", "0007_e5_embeddings"} <= revisions


def test_upgrade_from_old_frontlayout_adds_only_missing_schema():
    buffer = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=buffer), "0003_admin_sessions:head", sql=True)
    sql = buffer.getvalue()
    assert "ADD COLUMN csrf_token_hash" in sql
    assert "ADD COLUMN failed_login_attempts" in sql
    assert "ADD COLUMN locked_until" in sql
    assert "CREATE TABLE user_favorites" in sql
    assert "CREATE TABLE users" not in sql
    assert "DROP TABLE" not in sql


def test_upgrade_from_main_changes_only_embedding_dimension_and_index():
    buffer = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=buffer), "0008_template_constructor:head", sql=True)
    sql = buffer.getvalue()
    assert "ALTER TABLE content_item_chunks ALTER COLUMN embedding TYPE VECTOR(384) USING NULL::vector(384)" in sql
    assert "DROP INDEX ix_content_item_chunks_embedding" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert all(statement not in sql for statement in ["CREATE TABLE", "DROP TABLE", "DELETE FROM", "ALTER COLUMN body"])


def test_database_at_e5_head_requires_no_schema_changes():
    buffer = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=buffer), "0007_e5_embeddings:head", sql=True)
    assert all(statement not in buffer.getvalue() for statement in ["CREATE TABLE", "ALTER TABLE", "UPDATE alembic_version"])


def test_e5_downgrade_restores_legacy_dimension_without_changing_content():
    buffer = io.StringIO()
    command.downgrade(Config("alembic.ini", output_buffer=buffer), "0007_e5_embeddings:0006_user_favorites", sql=True)
    sql = buffer.getvalue()
    assert "TYPE VECTOR(1024) USING NULL::vector(1024)" in sql
    assert "DROP TABLE" not in sql and "DELETE FROM" not in sql


def test_existing_account_lock_is_respected(monkeypatch):
    session = Mock()
    user = User(id=7, user_type=UserType.ADMIN, is_active=True,
                locked_until=datetime.now(timezone.utc) + timedelta(minutes=10))
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: True)
    with pytest.raises(HTTPException) as error:
        auth.login(auth.LoginInput(email="admin@example.test", password="password"), request(), Response(), session)
    assert error.value.status_code == 401
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_failed_logins_persist_the_security_fields(monkeypatch):
    session = Mock()
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    user = User(id=7, user_type=UserType.ADMIN, is_active=True, failed_login_attempts=0, last_failed_login_at=old_time)
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: False)
    for attempt in range(auth.MAX_FAILED_LOGINS):
        with pytest.raises(HTTPException):
            auth.login(auth.LoginInput(email="admin@example.test", password="wrong"), request(), Response(), session)
        assert user.failed_login_attempts == attempt + 1
    assert user.locked_until > datetime.now(timezone.utc)
    assert session.commit.call_count == auth.MAX_FAILED_LOGINS
    session.add.assert_not_called()


def test_successful_login_after_lock_expiry_resets_security_fields(monkeypatch):
    session = Mock()
    user = User(id=7, user_type=UserType.ADMIN, is_active=True, failed_login_attempts=5,
                locked_until=datetime.now(timezone.utc) - timedelta(minutes=1))
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: True)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(session_hours=8, session_cookie_secure=False))
    result = auth.login(auth.LoginInput(email="admin@example.test", password="password"), request(), Response(), session)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert session.add.call_args.args[0].csrf_token_hash == auth.hash_token(result["csrf_token"])
