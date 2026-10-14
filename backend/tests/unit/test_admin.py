from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from backend import admin, auth, manage_admin, public
from backend.admin_resources import RESOURCES, metadata
from backend.admin_schemas import ArticleInput, FeeRateInput
from backend.models import AdminSession, ContentItem, ContentItemChunk, User, UserType


def request(method="GET", token=None, csrf=None):
    headers = []
    if token is not None:
        headers.append((b"cookie", f"{auth.COOKIE_NAME}={token}".encode()))
    if csrf is not None:
        headers.append((b"x-csrf-token", csrf.encode()))
    return Request({"type": "http", "method": method, "path": "/", "headers": headers})

CSRF = "c" * 64

def stored_session(user):
    return SimpleNamespace(user=user, csrf_token_hash=auth.hash_token(CSRF))

def administrator():
    return User(id=7, email="admin@example.test", full_name="Admin",
                user_type=UserType.ADMIN, is_active=True,
                failed_login_attemts=0, locked_until=None)


def test_password_hash_is_argon2_and_invalid_hash_is_rejected():
    hashed = auth.password_hasher.hash("long-unit-test-password")
    assert hashed.startswith("$argon2id$")
    assert auth.verify_password("long-unit-test-password", hashed)
    assert not auth.verify_password("wrong", hashed)
    assert not auth.verify_password("password", "legacy-invalid-hash")


@pytest.mark.parametrize("token", [None, "", "short", "x" * 129])
def test_missing_or_malformed_session_is_rejected_without_query(token):
    session = Mock()
    with pytest.raises(HTTPException) as error:
        auth.require_admin(request(token=token), session)
    assert error.value.status_code == 401
    session.scalar.assert_not_called()


@pytest.mark.parametrize("state,expected", [("missing", 401), ("inactive", 401), ("nonadmin", 403)])
def test_session_requires_active_administrator(state, expected):
    user = administrator()
    if state == "inactive":
        user.is_active = False
    if state == "nonadmin":
        user.user_type = UserType.INDIVIDUAL
    session = Mock()
    session.scalar.return_value = None if state == "missing" else SimpleNamespace(user=user)
    with pytest.raises(HTTPException) as error:
        auth.require_admin(request(token="x" * 32), session)
    assert error.value.status_code == expected


@pytest.mark.parametrize("csrf", [None, "bad", "x" * 64, "я" * 64])
def test_writes_require_session_bound_csrf_token(csrf):
    session = Mock()
    session.scalar.return_value = stored_session(administrator())
    with pytest.raises(HTTPException) as error:
        auth.require_admin(request("POST", "x" * 32, csrf), session)
    assert error.value.status_code == 403


def test_valid_session_allows_reads_and_protected_writes():
    user = administrator()
    session = Mock()
    session.scalar.return_value = stored_session(user=user)
    token = "x" * 32
    assert auth.require_admin(request(token=token), session) is user
    assert auth.require_admin(request("PUT", token, CSRF), session) is user
    with pytest.raises(HTTPException) as error:
        auth.require_admin(request("PUT", token, "d" * 64), session)
    assert error.value.status_code == 403

def test_login_stores_only_token_hash_and_sets_private_cookie(monkeypatch):
    user = administrator()
    user.password_hash = "mocked"
    session = Mock()
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: True)
    monkeypatch.setattr(auth.secrets, "token_urlsafe", lambda size: "t" * 32)
    monkeypatch.setattr(auth.secrets, "token_hex", lambda size: "k" * 64)
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(session_hours=8, session_cookie_secure=True))
    response = Response()
    result = auth.login(auth.LoginInput(email=" ADMIN@EXAMPLE.TEST ", password="password"),
                        request(token="old" * 12), response, session)
    stored = session.add.call_args.args[0]
    assert isinstance(stored, AdminSession)
    assert stored.token_hash == auth.hash_token("t" * 32)
    assert stored.token_hash != "t" * 32
    assert stored.user_id == user.id
    assert stored.expires_at > datetime.now(timezone.utc)
    assert stored.csrf_token_hash == auth.hash_token("k" * 64)
    assert result["csrf_token"] == "k" * 32
    assert result["csfr_token"] != "t" * 32
    assert "password_hash" not in result["user"]
    cookie = response.headers["set-cookie"].lower()
    assert all(value in cookie for value in ["httponly", "secure", "samesite=strict", "path=/api/"])
    assert response.headers["cache-control"] == "no-store"
    assert session.execute.call_count == 2  # rotate previous token and discard expired sessions
    session.commit.assert_called_once()


@pytest.mark.parametrize("state", ["missing", "wrong-password", "inactive"])
def test_failed_login_never_creates_session(monkeypatch, state):
    user = administrator()
    user.password_hash = "mocked"
    if state == "inactive":
        user.is_active = False
    session = Mock()
    session.scalar.return_value = None if state == "missing" else user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: state != "wrong-password")
    with pytest.raises(HTTPException) as error:
        auth.login(auth.LoginInput(email="admin@example.test", password="password"), request(), Response(), session)
    assert error.value.status_code == 401
    session.add.assert_not_called()
    if state == "missing":
        session.commit.assert_not_called()
    else:
        assert user.failed_login_attempts == 1
        session.commit.assert_not_called()


def test_logout_revokes_database_session_and_cookie():
    session = Mock()
    response = Response()
    auth.logout(request("POST", "x" * 32), response, administrator(), session)
    session.execute.assert_called_once()
    session.commit.assert_called_once()
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_admin_creation_sets_role_and_hashes_password():
    session = Mock()
    session.scalar.return_value = None
    password = "long-unit-test-password"
    assert manage_admin.create_admin(session, " ADMIN@EXAMPLE.TEST ", password, " Admin ")
    user = session.add.call_args.args[0]
    assert user.email == "admin@example.test" and user.full_name == "Admin"
    assert user.user_type == UserType.ADMIN and user.is_active
    assert user.password_hash != password
    assert auth.verify_password(password, user.password_hash)
    session.flush.assert_called_once()


def test_bootstrap_does_not_reset_existing_admin_or_promote_users():
    session = Mock()
    user = administrator()
    user.password_hash = "unchanged"
    session.scalar.return_value = user
    assert not manage_admin.create_admin(session, user.email, "long-test-password", "Admin")
    assert user.password_hash == "unchanged"
    session.execute.assert_not_called()
    user.user_type = UserType.INDIVIDUAL
    with pytest.raises(ValueError):
        manage_admin.create_admin(session, user.email, "long-test-password", "Admin")


def test_explicit_password_reset_revokes_sessions():
    session = Mock()
    user = administrator()
    session.scalar.return_value = user
    assert manage_admin.create_admin(session, user.email, "long-test-password", "Admin", reset_password=True)
    assert auth.verify_password("long-test-password", user.password_hash)
    session.execute.assert_called_once()


def test_short_admin_password_is_rejected():
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(ValueError):
        manage_admin.create_admin(session, "admin@example.test", "short", "Admin")
    session.add.assert_not_called()


def test_bootstrap_preserves_manually_configured_admin_login():
    session = Mock()
    user = administrator()
    user.email = "admin"
    user.password_hash = "unchanged"
    session.scalar.return_value = user
    assert not manage_admin.create_admin(session, "admin", "admin", "Admin")
    assert user.password_hash == "unchanged"
    session.execute.assert_not_called()
    session.add.assert_not_called()
    with pytest.raises(ValueError):
        manage_admin.create_admin(session, "admin", "admin", "Admin", reset_password=True)


def test_every_admin_route_is_protected_and_resources_are_allowlisted():
    for route in admin.router.routes:
        assert any(dependency.call is auth.require_admin for dependency in route.dependant.dependencies)
    assert len(RESOURCES) == 17
    with pytest.raises(HTTPException) as error:
        admin.get_resource("users")
    assert error.value.status_code == 404
    for resource in RESOURCES.values():
        fields = metadata(resource)["fields"]
        assert {field["name"] for field in fields} == set(resource.schema.model_fields)
        assert not ({"password_hash", "embedding", "tsv", "created_by"} & set(resource.schema.model_fields))
    assert next(field for field in metadata(RESOURCES["fee-rates"])["fields"]
                if field["name"] == "amount")["kind"] == "decimal"


@pytest.mark.parametrize("key", ["0", "-1", "abc", "1:2", ""])
def test_invalid_scalar_identity_is_rejected(key):
    with pytest.raises(HTTPException) as error:
        admin.identity(RESOURCES["articles"], key)
    assert error.value.status_code == 422


def test_composite_identity_and_serialization_preserve_foreign_keys():
    assert admin.identity(RESOURCES["article-tags"], "3:4") == (3, 4)
    from backend.models import ContentItemTag
    assert admin.serialize(RESOURCES["article-tags"], ContentItemTag(content_item_id=3, tag_id=4)) == {
        "id": "3:4", "content_item_id": 3, "tag_id": 4,
    }


@pytest.mark.parametrize("extra", [{"created_by": 1}, {"password_hash": "hash"}, {"id": 12}])
def test_article_rejects_server_owned_fields(extra):
    with pytest.raises(ValidationError):
        ArticleInput(title="Article", slug="article", chunks=["Text"], **extra)


@pytest.mark.parametrize("chunks", [[], ["   "]])
def test_article_requires_nonblank_text(chunks):
    with pytest.raises(ValidationError):
        ArticleInput(title="Article", slug="article", chunks=chunks)


def test_article_chunk_updates_preserve_identity_and_order():
    item = ContentItem(title="Article", slug="article", type="article")
    first = ContentItemChunk(id=1, chunk_index=0, body="First")
    second = ContentItemChunk(id=2, chunk_index=1, body="Second")
    item.chunks.extend([first, second])
    admin.apply_article_chunks(item, ["Changed"])
    assert item.chunks == [first] and first.body == "Changed"
    admin.apply_article_chunks(item, ["Changed", "New"])
    assert item.chunks[0] is first
    assert item.chunks[1].chunk_index == 1 and item.chunks[1].body == "New"
    assert "embedding" not in admin.serialize(RESOURCES["chunks"], first)
    assert "tsv" not in admin.serialize(RESOURCES["chunks"], first)


def test_publication_sets_date_and_author_on_server():
    session = Mock()
    user = administrator()
    result = admin.save_record(RESOURCES["articles"], {
        "title": "Article", "slug": "article", "status": "published", "chunks": ["Text"],
    }, session, user)
    record = session.add.call_args.args[0]
    assert record.created_by == user.id
    assert record.published_at.tzinfo is not None
    assert result["chunks"] == ["Text"]
    session.commit.assert_called_once()


def test_invalid_foreign_key_or_duplicate_rolls_back():
    session = Mock()
    session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    with pytest.raises(HTTPException) as error:
        admin.save_record(RESOURCES["tags"], {"name": "Tag", "slug": "tag"}, session, administrator())
    assert error.value.status_code == 409
    session.rollback.assert_called_once()


def test_delete_uses_database_foreign_key_rules_and_reports_conflicts():
    from backend.models import ContentCategory
    session = Mock()
    session.get.return_value = ContentCategory(id=1, name="Category", slug="category")
    session.execute.side_effect = IntegrityError("delete", {}, Exception("referenced"))
    with pytest.raises(HTTPException) as error:
        admin.delete_record("categories", "1", session)
    assert error.value.status_code == 409
    session.rollback.assert_called_once()
    session.delete.assert_not_called()


def test_category_parent_cycles_are_rejected():
    session = Mock()
    session.get.side_effect = [SimpleNamespace(parent_id=3), SimpleNamespace(parent_id=1)]
    with pytest.raises(HTTPException) as error:
        admin.validate_parent(session, parent_id=2, record_id=1)
    assert error.value.status_code == 422


def test_fee_rates_keep_decimal_precision_and_check_dates():
    values = dict(application_type_id=1, amount="123456789012.34", valid_from="2026-01-01", legal_basis="Example")
    assert FeeRateInput(**values).amount == Decimal("123456789012.34")
    with pytest.raises(ValidationError):
        FeeRateInput(**{**values, "amount": "1.001"})
    with pytest.raises(ValidationError):
        FeeRateInput(**values, valid_to="2025-12-31")


def test_public_query_excludes_drafts_and_scheduled_articles():
    session = Mock()
    session.scalars.return_value = []
    assert public.list_articles(session, limit=25, offset=0) == []
    statement = session.scalars.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "content_items.status = 'published'" in sql
    assert "content_items.published_at <= now()" in sql


def test_regular_user_passes_require_user_but_not_require_admin():
    user = administrator()
    user.user_type = UserType.INDIVIDUAL
    session = Mock()
    session.scalar.return_value = stored_session(user)
    assert auth.require_user(request(token="x" * 32), session) is user
    with pytest.raises(HTTPException) as error:
        auth.require_admin(request(token="x" * 32), session)
    assert error.value.status_code == 403


def make_user():
    user = administrator()
    user.password_hash = "mocked"
    return user


def failed_attempt(monkeypatch, user):
    session = Mock()
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: False)
    with pytest.raises(HTTPException) as error:
        auth.login(auth.LoginInput(email="admin@example.test", password="password"),
                   request(), Response(), session)
    assert error.value.status_code == 401


def test_five_failed_logins_lock_the_account(monkeypatch):
    user = make_user()
    for _ in range(auth.MAX_FAILED_LOGINS):
        failed_attempt(monkeypatch, user)
    assert user.locked_until > datetime.now(timezone.utc)


def test_locked_account_rejects_even_the_correct_password(monkeypatch):
    user = make_user()
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    session = Mock()
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: True)
    with pytest.raises(HTTPException) as error:
        auth.login(auth.LoginInput(email="admin@example.test", password="password"),
                   request(), Response(), session)
    assert error.value.status_code == 401
    session.add.assert_not_called()


def test_expired_lock_starts_counting_from_zero(monkeypatch):
    user = make_user()
    user.failed_login_attempts = auth.MAX_FAILED_LOGINS
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    failed_attempt(monkeypatch, user)
    assert user.failed_login_attempts == 1 and user.locked_until is None


def test_successful_login_resets_failure_counter(monkeypatch):
    user = make_user()
    user.failed_login_attempts = 3
    session = Mock()
    session.scalar.return_value = user
    monkeypatch.setattr(auth, "verify_password", lambda password, hashed: True)
    monkeypatch.setattr(auth, "get_settings",
                        lambda: SimpleNamespace(session_hours=8, session_cookie_secure=False))
    auth.login(auth.LoginInput(email="admin@example.test", password="password"),
               request(), Response(), session)
    assert user.failed_login_attempts == 0 and user.locked_until is None


def test_me_issues_a_new_csrf_token_and_never_returns_the_session_cookie():
    session = Mock()
    token = "x" * 32
    result = auth.me(request(token=token), Response(), administrator(), session)
    assert len(result["csrf_token"]) == 64 and result["csrf_token"] != token
    session.execute.assert_called_once()
    session.commit.assert_called_once()