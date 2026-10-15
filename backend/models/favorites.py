from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, BigIntPrimaryKey, CreatedAt

if TYPE_CHECKING:
    from backend.models.content import ContentItem
    from backend.models.users import User


class UserFavorite(BigIntPrimaryKey, CreatedAt, Base):
    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "content_item_id", name="uq_user_favorites_user_content"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_items.id", ondelete="CASCADE"), index=True
    )

    user: Mapped["User"] = relationship(back_populates="favorites")
    content_item: Mapped["ContentItem"] = relationship()