from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from backend import auth
from backend.models import AdminSession, UserType

NO_COOKIE = SimpleNamespace(cookies={})  # запрос без куки сессии


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(auth, "get_settings",
                        lambda: SimpleNamespace(session_hours=8, session_cookie_secure=False))


def make_input(**changes):
    data = {"email": " Anna@Example.RU ", "full_name": " Анна Иванова ", "password": "x" * 12}
    return auth.RegisterInput(**{**data, **changes})


def test_password_length_boundary():
    with pytest.raises(ValidationError):
        make_input(password="x" * 11)
    assert make_input(password="x" * 12)
    with pytest.raises(ValidationError):
        make_input(password="x" * 5)


def test_registration_cannot_create_admin_or_set_extra_fields():
    with pytest.raises(ValidationError):
        make_input(user_type="admin")
    with pytest.raises(ValidationError):
        make_input(is_active=True)


def test_email_and_name_are_normalized_without_changing_name_case():
    payload = make_input()
    assert payload.email == "anna@example.ru"
    assert payload.full_name == "Анна Иванова"


def test_register_stores_argon2_hash_and_returns_csrf_not_session_token(monkeypatch):
    monkeypatch.setattr(auth.secrets, "token_urlsafe", lambda size: "t" * 32)
    session = Mock()
    session.scalar.return_value = None
    result = auth.register(make_input(), NO_COOKIE, Response(), session)
    user = session.add.call_args_list[0].args[0]
    assert user.user_type == UserType.INDIVIDUAL
    assert user.password_hash.startswith("$argon2id$")
    assert result["csrf_token"] != "t" * 32
    assert "t" * 32 not in str(result)


def test_duplicate_email_gives_409():
    session = Mock()
    session.scalar.return_value = object()
    with pytest.raises(HTTPException) as error:
        auth.register(make_input(), NO_COOKIE, Response(), session)
    assert error.value.status_code == 409
    session.add.assert_not_called()


def test_parallel_duplicate_registration_gives_409():
    session = Mock()
    session.scalar.return_value = None
    session.flush.side_effect = IntegrityError("insert", {}, Exception())
    with pytest.raises(HTTPException) as error:
        auth.register(make_input(), NO_COOKIE, Response(), session)
    assert error.value.status_code == 409
    session.rollback.assert_called_once()


def regular_user(password="old-password-123"):
    return SimpleNamespace(id=5, email="a@b.cc", full_name="Анна", last_login_at=None,
                           user_type=UserType.INDIVIDUAL,
                           password_hash=auth.password_hasher.hash(password))


@pytest.mark.parametrize("old,new", [("wrong-password-1", "brand-new-password"),
                                     ("old-password-123", "old-password-123")])
def test_change_password_rejects_wrong_or_unchanged_password(old, new):
    with pytest.raises(HTTPException) as error:
        auth.change_password(auth.ChangePasswordInput(old_password=old, new_password=new),
                             NO_COOKIE, Response(), regular_user(), Mock())
    assert error.value.status_code == 400


def test_change_password_rejects_short_new_password():
    with pytest.raises(ValidationError):
        auth.ChangePasswordInput(old_password="old-password-123",
                                 new_password="x" * 5)


def test_change_password_updates_hash_and_revokes_old_sessions():
    user, session = regular_user(), Mock()
    auth.change_password(
        auth.ChangePasswordInput(old_password="old-password-123", new_password="brand-new-password"),
        NO_COOKIE, Response(), user, session)
    assert auth.verify_password("brand-new-password", user.password_hash)
    assert not auth.verify_password("old-password-123", user.password_hash)
    assert session.execute.call_count == 2  # все сессии удалены + уборка просроченных
    assert isinstance(session.add.call_args.args[0], AdminSession)  # выдана новая


