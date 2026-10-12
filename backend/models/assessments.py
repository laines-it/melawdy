from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, BigIntPrimaryKey, CreatedAt
from backend.models.enums import QuestionType, enum_type

if TYPE_CHECKING:
    from backend.models.content import ContentItem
    from backend.models.documents import DocumentTemplate
    from backend.models.users import User


class AssessmentSurvey(BigIntPrimaryKey, CreatedAt, Base):
    __tablename__ = "assessment_surveys"
    __table_args__ = (CheckConstraint("version > 0", name="positive_version"),)

    title: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, server_default=sql_text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    questions: Mapped[list["AssessmentQuestion"]] = relationship(
        back_populates="survey", cascade="all, delete-orphan", passive_deletes=True,
        order_by="AssessmentQuestion.sort_order",
    )
    rules: Mapped[list["AssessmentResultRule"]] = relationship(
        back_populates="survey", cascade="all, delete-orphan", passive_deletes=True
    )
    assessments: Mapped[list["UserAssessment"]] = relationship(back_populates="survey")


class AssessmentQuestion(BigIntPrimaryKey, Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),)

    survey_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assessment_surveys.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[QuestionType] = mapped_column(enum_type(QuestionType, "question_type"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    is_required: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    survey: Mapped[AssessmentSurvey] = relationship(back_populates="questions")
    options: Mapped[list["AssessmentOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", passive_deletes=True,
        order_by="AssessmentOption.sort_order",
    )


class AssessmentOption(BigIntPrimaryKey, Base):
    __tablename__ = "assessment_options"
    __table_args__ = (CheckConstraint("sort_order >= 0", name="sort_order_nonnegative"),)

    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assessment_questions.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    question: Mapped[AssessmentQuestion] = relationship(back_populates="options")


class AssessmentResult(BigIntPrimaryKey, Base):
    __tablename__ = "assessment_results"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    recommended_content_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("content_items.id", ondelete="SET NULL"), index=True
    )
    recommended_document_template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("document_templates.id", ondelete="SET NULL"), index=True
    )
    recommended_content: Mapped["ContentItem | None"] = relationship()
    recommended_document_template: Mapped["DocumentTemplate | None"] = relationship()
    rules: Mapped[list["AssessmentResultRule"]] = relationship(back_populates="result")
    assessments: Mapped[list["UserAssessment"]] = relationship(back_populates="result")


class AssessmentResultRule(BigIntPrimaryKey, Base):
    __tablename__ = "assessment_result_rules"

    survey_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assessment_surveys.id", ondelete="CASCADE"), index=True
    )
    result_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assessment_results.id", ondelete="RESTRICT"), index=True
    )
    condition_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    survey: Mapped[AssessmentSurvey] = relationship(back_populates="rules")
    result: Mapped[AssessmentResult] = relationship(back_populates="rules")


class UserAssessment(BigIntPrimaryKey, CreatedAt, Base):
    __tablename__ = "user_assessments"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    survey_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("assessment_surveys.id", ondelete="RESTRICT"), index=True
    )
    result_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("assessment_results.id", ondelete="RESTRICT"), index=True
    )
    answers_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    user: Mapped["User"] = relationship(back_populates="assessments")
    survey: Mapped[AssessmentSurvey] = relationship(back_populates="assessments")
    result: Mapped[AssessmentResult | None] = relationship(back_populates="assessments")
