from http.cookies import SimpleCookie
from uuid import uuid4

from fastapi import HTTPException, Response
import pytest
from sqlalchemy import select
from starlette.requests import Request

from backend import account, auth
from backend.db import SessionLocal
from backend.models import AdminSession, User, UserType


def test_registration_persists_user_and_session_without_administrator_access(monkeypatch):
    email = f"{uuid4().hex}@example.test"
    password = "registration-test-password"
    with SessionLocal() as session:
        monkeypatch.setattr(session, "commit", session.flush)
        response = Response()
        request = Request({"type": "http", "method": "POST", "path": "/api/v1/auth/register", "headers": []})
        result = auth.register(auth.RegisterInput(email=email, full_name="Новый пользователь", password=password),
                               request, response, session)
        user = session.scalar(select(User).where(User.email == email))
        assert user.user_type == UserType.INDIVIDUAL
        assert auth.verify_password(password, user.password_hash)
        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        token = cookie[auth.COOKIE_NAME].value
        stored = session.get(AdminSession, auth.hash_token(token))
        assert stored.user_id == user.id
        assert stored.csrf_token_hash == auth.hash_token(result["csrf_token"])
        authenticated = Request({"type": "http", "method": "POST", "path": "/", "headers": [
            (b"cookie", f"{auth.COOKIE_NAME}={token}".encode()),
            (b"x-csrf-token", result["csrf_token"].encode()),
        ]})
        assert auth.require_user(authenticated, session).id == user.id
        with pytest.raises(HTTPException) as error:
            auth.require_admin(authenticated, session)
        assert error.value.status_code == 403
        assert account.overview(Response(), session, user)["documents"] == []
        with pytest.raises(HTTPException) as duplicate:
            auth.register(auth.RegisterInput(email=email, full_name="Повтор", password=password),
                          request, Response(), session)
        assert duplicate.value.status_code == 409
        session.rollback()
