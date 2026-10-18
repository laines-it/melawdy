from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, BigIntPrimaryKey, CreatedAt, UpdatedAt
from backend.models.enums import UserType, enum_type

if TYPE_CHECKING:
    from backend.models.assessments import UserAssessment
    from backend.models.content import ContentItem
    from backend.models.documents import DocumentStatusHistory, RequestHistory, UserDocument
    from backend.models.fees import FeeCalculation
    from backend.models.favorites import UserFavorite


class User(BigIntPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    user_type: Mapped[UserType] = mapped_column(enum_type(UserType, "user_type"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    content_items: Mapped[list["ContentItem"]] = relationship(back_populates="creator")
    assessments: Mapped[list["UserAssessment"]] = relationship(back_populates="user")
    fee_calculations: Mapped[list["FeeCalculation"]] = relationship(back_populates="user")
    documents: Mapped[list["UserDocument"]] = relationship(back_populates="user")
    status_changes: Mapped[list["DocumentStatusHistory"]] = relationship(back_populates="actor")
    requests: Mapped[list["RequestHistory"]] = relationship(back_populates="user")
    favorites: Mapped[list["UserFavorite"]] = relationship(back_populates="user")

    #от брутфорса
    failed_login_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
