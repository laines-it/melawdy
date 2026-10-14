from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

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


class RegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    full_name: str = Field(min_length=1, max_length=255)
    user_type: Literal["individual", "organization", "lawyer"] = "individual"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or " " in value:
            raise ValueError("Укажите корректный email")
        return value

    @field_validator("full_name")
    @classmethod
    def full_name(cls, value: str):
        value = value.strip().lower()
        if not value:
            raise ValueError("Укажите имя и фамилию")
        return value


class ChangePasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

#просмотреть работу с токеном и поправить
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


def require_user(request: Request, session: SessionDep) -> User:
    token = request.cookies.get(COOKIE_NAME, "")
    if not 20 <= len(token) <= 128:
        raise HTTPException(401, "Войдите в аккаунт")
    stored = session.scalar(
        select(AdminSession).options(joinedload(AdminSession.user))
        .where(AdminSession.token_hash == hash_token(token), AdminSession.expires_at > func.now())
    )
    if stored is None or not stored.user.is_active:
        raise HTTPException(401, "Сессия истекла. Войдите заново")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if len(supplied) != 64 or not supplied.isascii() or not hmac.compare_digest(supplied, csrf_token(token)):
            raise HTTPException(403, "Обновите страницу и повторите действие")
    return stored.user


def require_admin(request: Request, session: SessionDep) -> User:
    user = require_user(request, session)
    if user.user_type != UserType.ADMIN:
        raise HTTPException(403, "Нужны права администратора")
    return user


UserDep = Annotated[User, Depends(require_user)]
AdminDep = Annotated[User, Depends(require_admin)]


def start_session(user: User, request: Request, response: Response, session: Session) -> dict:
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


@router.post("/login")
def login(payload: LoginInput, request: Request, response: Response, session: SessionDep) -> dict:
    now = datetime.now(timezone.utc)
    user = session.scalar(select(User).where(func.lower(User.email) == payload.email))
    valid = verify_password(payload.password, user.password_hash if user else _dummy_hash)
    if user:
        if user.locked_until and user.locked_until > now:
            raise HTTPException(401, "Неверный email или пароль")
        if not valid or not user.is_active:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)

            session.commit()
            raise HTTPException(401, "Неверный email или пароль")
    else:
        raise HTTPException(401, "Неверный email или пароль")

    user.failed_login_attempts = 0
    user.locked_until = None
    session.commit()

    return start_session(user, request, response, session)


@router.post("/register", status_code=201)
def register(payload: RegisterInput, request: Request, response: Response, session: SessionDep) -> dict:
    new = session.scalar(select(User).where(func.lower(User.email) == payload.email))
    if new is not None:
        raise HTTPException(409, "Пользователь с таким email уже существует")
    user = User(email=payload.email, password_hash=password_hasher.hash(payload.password),
                full_name=payload.full_name, user_type=UserType(payload.user_type), is_active=True)
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Пользователь с таким email уже существует")
    return start_session(user, request, response, session)


@router.post("/change-password")
def change_password(payload: ChangePasswordInput, request: Request, response: Response, user: UserDep,
                    session: SessionDep) -> dict:
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, "Текущий пароль неверный")
    if payload.old_password == payload.new_password:
        raise HTTPException(400, "Новый пароль должен отличаться от предыдущего")
    user.password_hash = password_hasher.hash(payload.new_password)
    session.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
    return start_session(user, request, response, session)


@router.get("/me")
def me(request: Request, response: Response, user: UserDep) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return session_response(user, request.cookies[COOKIE_NAME])


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: UserDep, session: SessionDep) -> None:
    session.execute(delete(AdminSession).where(
        AdminSession.token_hash == hash_token(request.cookies[COOKIE_NAME])))
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/", httponly=True, samesite="strict",
                           secure=get_settings().session_cookie_secure)
