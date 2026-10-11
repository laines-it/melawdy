from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger, CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, BigIntPrimaryKey, CreatedAt, UpdatedAt
from backend.models.enums import ContentStatus, ContentType, enum_type
from ml.constants import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from backend.models.users import User


class ContentCategory(BigIntPrimaryKey, Base):
    __tablename__ = "content_categories"
    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),
    )

    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("content_categories.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))

    parent: Mapped["ContentCategory | None"] = relationship(
        back_populates="children", remote_side="ContentCategory.id"
    )
    children: Mapped[list["ContentCategory"]] = relationship(back_populates="parent")
    items: Mapped[list["ContentItem"]] = relationship(back_populates="category")
    qa_pairs: Mapped[list["QAPair"]] = relationship(back_populates="category")


class ContentItem(BigIntPrimaryKey, CreatedAt, UpdatedAt, Base):
    __tablename__ = "content_items"
    __table_args__ = (
        CheckConstraint("status <> 'published' OR published_at IS NOT NULL", name="publication_date"),
        Index("ix_content_items_status_published_at", "status", "published_at"),
    )

    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("content_categories.id", ondelete="RESTRICT"), index=True
    )
    type: Mapped[ContentType] = mapped_column(enum_type(ContentType, "content_type"))
    title: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ContentStatus] = mapped_column(
        enum_type(ContentStatus, "content_status"), server_default=text("'draft'")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    category: Mapped[ContentCategory | None] = relationship(back_populates="items")
    creator: Mapped["User | None"] = relationship(back_populates="content_items")
    chunks: Mapped[list["ContentItemChunk"]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ContentItemChunk.chunk_index",
    )
    tag_links: Mapped[list["ContentItemTag"]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan", passive_deletes=True
    )
    glossary_links: Mapped[list["GlossaryTermContent"]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan", passive_deletes=True
    )
    qa_pairs: Mapped[list["QAPair"]] = relationship(back_populates="content_item")


class ContentItemChunk(BigIntPrimaryKey, UpdatedAt, Base):
    __tablename__ = "content_item_chunks"
    __table_args__ = (
        UniqueConstraint("content_item_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
        CheckConstraint("btrim(body) <> ''", name="body_not_blank"),
        Index("ix_content_item_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_content_item_chunks_embedding", "embedding", postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    content_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_items.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('russian'::regconfig, body)", persisted=True)
    )
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(EMBEDDING_DIMENSIONS))

    content_item: Mapped[ContentItem] = relationship(back_populates="chunks")


class ContentTag(BigIntPrimaryKey, Base):
    __tablename__ = "content_tags"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    content_links: Mapped[list["ContentItemTag"]] = relationship(
        back_populates="tag", cascade="all, delete-orphan", passive_deletes=True
    )


class ContentItemTag(Base):
    __tablename__ = "content_item_tags"

    content_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    content_item: Mapped[ContentItem] = relationship(back_populates="tag_links")
    tag: Mapped[ContentTag] = relationship(back_populates="content_links")


class GlossaryTerm(BigIntPrimaryKey, CreatedAt, Base):
    __tablename__ = "glossary_terms"

    term: Mapped[str] = mapped_column(String(255), unique=True)
    definition: Mapped[str] = mapped_column(Text)
    full_definition: Mapped[str | None] = mapped_column(Text)
    content_links: Mapped[list["GlossaryTermContent"]] = relationship(
        back_populates="term", cascade="all, delete-orphan", passive_deletes=True
    )


class GlossaryTermContent(Base):
    __tablename__ = "glossary_term_content"

    term_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("glossary_terms.id", ondelete="CASCADE"), primary_key=True
    )
    content_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    term: Mapped[GlossaryTerm] = relationship(back_populates="content_links")
    content_item: Mapped[ContentItem] = relationship(back_populates="glossary_links")


class QAPair(BigIntPrimaryKey, Base):
    __tablename__ = "qa_pairs"
    __table_args__ = (CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),)

    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("content_categories.id", ondelete="SET NULL"), index=True
    )
    content_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("content_items.id", ondelete="SET NULL"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    category: Mapped[ContentCategory | None] = relationship(back_populates="qa_pairs")
    content_item: Mapped[ContentItem | None] = relationship(back_populates="qa_pairs")
