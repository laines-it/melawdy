from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, BigIntPrimaryKey, CreatedAt, UpdatedAt
from backend.models.enums import DeadlineStatus, DocumentStatus, DocumentType, enum_type

if TYPE_CHECKING:
    from backend.models.users import User


class DocumentTemplate(BigIntPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "document_templates"

    document_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType, "document_type"))
    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    documents: Mapped[list["UserDocument"]] = relationship(back_populates="template")


class UserDocument(BigIntPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "user_documents"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("document_templates.id", ondelete="SET NULL"), index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType, "document_type"))
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[DocumentStatus] = mapped_column(
        enum_type(DocumentStatus, "document_status"), server_default=text("'draft'")
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    deadline_status: Mapped[DeadlineStatus] = mapped_column(
        enum_type(DeadlineStatus, "deadline_status"), server_default=text("'none'")
    )
    reminder_sent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    user: Mapped["User"] = relationship(back_populates="documents")
    template: Mapped[DocumentTemplate | None] = relationship(back_populates="documents")
    status_history: Mapped[list["DocumentStatusHistory"]] = relationship(
        back_populates="document", order_by="DocumentStatusHistory.changed_at"
    )


class DocumentStatusHistory(BigIntPrimaryKey, Base):
    __tablename__ = "document_status_history"

    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_documents.id", ondelete="RESTRICT"), index=True
    )
    old_status: Mapped[DocumentStatus | None] = mapped_column(enum_type(DocumentStatus, "document_status"))
    new_status: Mapped[DocumentStatus] = mapped_column(enum_type(DocumentStatus, "document_status"))
    comment: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped[UserDocument] = relationship(back_populates="status_history")
    actor: Mapped["User | None"] = relationship(back_populates="status_changes")


class RequestHistory(BigIntPrimaryKey, CreatedAt, Base):
    __tablename__ = "request_history"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    request_type: Mapped[str] = mapped_column(String(100))
    request_params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response_summary: Mapped[str | None] = mapped_column(Text)
    user: Mapped["User"] = relationship(back_populates="requests")
