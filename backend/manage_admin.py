"""Create an admin explicitly or bootstrap one from deployment environment variables."""
import argparse
import getpass
import os
from pathlib import Path
import secrets

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.auth import password_hasher
from backend.config import get_settings
from backend.db import SessionLocal
from backend.models import AdminSession, User, UserType


def create_admin(session: Session, email: str, password: str, name: str,
                 reset_password: bool = False) -> bool:
    email = email.strip().lower()
    user = session.scalar(select(User).where(func.lower(User.email) == email))
    if user is not None:
        if user.user_type != UserType.ADMIN:
            raise ValueError("Email уже принадлежит пользователю без роли администратора")
        if not reset_password:
            return False
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Пароль должен содержать от 12 до 1024 символов")
    if "@" not in email or len(email) > 320 or not name.strip():
        raise ValueError("Укажите корректный email и имя администратора")
    if user is not None:
        user.password_hash = password_hasher.hash(password)
        session.execute(delete(AdminSession).where(AdminSession.user_id == user.id))
    else:
        session.add(User(email=email, full_name=name.strip(), user_type=UserType.ADMIN,
                         is_active=True, password_hash=password_hasher.hash(password)))
    session.flush()
    return True


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Create a MeLawDy administrator")
    parser.add_argument("--email", default=settings.admin_email)
    parser.add_argument("--name", default=settings.admin_full_name)
    parser.add_argument("--from-env", action="store_true")
    parser.add_argument("--generate-password", action="store_true")
    parser.add_argument("--credentials-file", default=".admin-credentials")
    parser.add_argument("--reset-password", action="store_true")
    args = parser.parse_args()
    if args.from_env and not settings.admin_password:
        return
    password = (settings.admin_password if args.from_env else
                secrets.token_urlsafe(24) if args.generate_password else getpass.getpass("Пароль: "))
    credentials_path = None
    credentials_created = False
    try:
        if args.generate_password:
            credentials_path = Path(args.credentials_file)
            descriptor = os.open(credentials_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            credentials_created = True
            with os.fdopen(descriptor, "w") as output:
                output.write(f"Email: {args.email.strip().lower()}\nPassword: {password}\n")
        with SessionLocal.begin() as session:
            changed = create_admin(session, args.email, password, args.name, args.reset_password)
    except Exception:
        if credentials_created:
            credentials_path.unlink(missing_ok=True)
        raise
    if not changed:
        if credentials_path is not None:
            credentials_path.unlink()
        print("Администратор уже существует; пароль сохранён прежним")
    else:
        print(f"Администратор {args.email} создан или обновлён")
        if credentials_path is not None:
            print(f"Данные входа сохранены в {credentials_path} (доступ только владельцу)")


if __name__ == "__main__":
    main()
