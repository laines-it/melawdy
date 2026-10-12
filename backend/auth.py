from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload

from backend.config import get_settings
from backend.db import get_session
from backend.models import AdminSession, User, UserType

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
COOKIE_NAME = "melawdy_session"
SessionDep = Annotated[Session, Depends(get_session)]
password_hasher = PasswordHash.recommended()
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"melawdy-csrf", hashlib.sha256).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False


def session_response(user: User, token: str) -> dict:
    return {"user": {"id": user.id, "email": user.email, "full_name": user.full_name,
                     "user_type": user.user_type}, "csrf_token": csrf_token(token)}


def require_admin(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(COOKIE_NAME, "")
    if not 20 <= len(token) <= 128:
        raise HTTPException(401, "Войдите в аккаунт администратора")
    stored = session.scalar(
        select(AdminSession).options(joinedload(AdminSession.user))
        .where(AdminSession.token_hash == hash_token(token), AdminSession.expires_at > func.now())
    )
    if stored is None or not stored.user.is_active:
        raise HTTPException(401, "Сессия истекла. Войдите заново")
    if stored.user.user_type != UserType.ADMIN:
        raise HTTPException(403, "Нужны права администратора")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if len(supplied) != 64 or not supplied.isascii() or not hmac.compare_digest(supplied, csrf_token(token)):
            raise HTTPException(403, "Обновите страницу и повторите действие")
    return stored.user


AdminDep = Annotated[User, Depends(require_admin)]


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, session: SessionDep) -> dict:
    user = session.scalar(select(User).where(func.lower(User.email) == payload.email))
    valid = verify_password(payload.password, user.password_hash if user else _dummy_hash)
    if not valid or user is None or not user.is_active or user.user_type != UserType.ADMIN:
        raise HTTPException(401, "Неверный email или пароль")
    now = datetime.now(timezone.utc)
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    previous = request.cookies.get(COOKIE_NAME)
    if previous:
        session.execute(delete(AdminSession).where(AdminSession.token_hash == hash_token(previous)))
    session.execute(delete(AdminSession).where(AdminSession.expires_at <= now))
    session.add(AdminSession(token_hash=hash_token(token), user_id=user.id,
                             expires_at=now + timedelta(hours=settings.session_hours)))
    user.last_login_at = now
    session.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=settings.session_hours * 3600,
                        httponly=True, secure=settings.session_cookie_secure,
                        samesite="strict", path="/api/")
    response.headers["Cache-Control"] = "no-store"
    return session_response(user, token)


@router.get("/me")
def me(request: Request, response: Response, user: AdminDep) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return session_response(user, request.cookies[COOKIE_NAME])


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: AdminDep, session: SessionDep) -> None:
    session.execute(delete(AdminSession).where(
        AdminSession.token_hash == hash_token(request.cookies[COOKIE_NAME])))
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/", httponly=True, samesite="strict",
                           secure=get_settings().session_cookie_secure)
