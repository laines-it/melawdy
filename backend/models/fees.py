from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String,
    Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, BigIntPrimaryKey, CreatedAt

if TYPE_CHECKING:
    from backend.models.users import User


class MktuClass(BigIntPrimaryKey, Base):
    __tablename__ = "mktu_classes"
    __table_args__ = (CheckConstraint("class_number BETWEEN 1 AND 45", name="class_number_range"),)

    class_number: Mapped[int] = mapped_column(Integer, unique=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    rates: Mapped[list["FeeRate"]] = relationship(back_populates="mktu_class")
    calculation_links: Mapped[list["FeeCalculationClass"]] = relationship(back_populates="mktu_class")


class ApplicationType(BigIntPrimaryKey, Base):
    __tablename__ = "application_types"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    rates: Mapped[list["FeeRate"]] = relationship(back_populates="application_type")
    calculations: Mapped[list["FeeCalculation"]] = relationship(back_populates="application_type")


class FeeRate(BigIntPrimaryKey, Base):
    __tablename__ = "fee_rates"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_date_range"),
        Index(
            "uq_fee_rates_effective", "application_type_id", "mktu_class_id", "is_urgent",
            "valid_from", unique=True, postgresql_nulls_not_distinct=True,
        ),
    )

    application_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("application_types.id", ondelete="RESTRICT"), index=True
    )
    mktu_class_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("mktu_classes.id", ondelete="RESTRICT"), index=True
    )
    is_urgent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'RUB'"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    legal_basis: Mapped[str] = mapped_column(Text)
    application_type: Mapped[ApplicationType] = relationship(back_populates="rates")
    mktu_class: Mapped[MktuClass | None] = relationship(back_populates="rates")


class FeeCalculation(BigIntPrimaryKey, CreatedAt, Base):
    __tablename__ = "fee_calculations"
    __table_args__ = (CheckConstraint("total_amount >= 0", name="amount_nonnegative"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    application_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("application_types.id", ondelete="RESTRICT"), index=True
    )
    is_urgent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'RUB'"))
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    breakdown_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    user: Mapped["User"] = relationship(back_populates="fee_calculations")
    application_type: Mapped[ApplicationType] = relationship(back_populates="calculations")
    class_links: Mapped[list["FeeCalculationClass"]] = relationship(
        back_populates="calculation", cascade="all, delete-orphan", passive_deletes=True
    )


class FeeCalculationClass(Base):
    __tablename__ = "fee_calculation_classes"

    calculation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fee_calculations.id", ondelete="CASCADE"), primary_key=True
    )
    mktu_class_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mktu_classes.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    calculation: Mapped[FeeCalculation] = relationship(back_populates="class_links")
    mktu_class: Mapped[MktuClass] = relationship(back_populates="calculation_links")
