from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.models import ContentStatus, ContentType, DocumentType, QuestionType

PositiveId = Annotated[int, Field(gt=0)]
ShortText = Annotated[str, Field(min_length=1, max_length=255)]
Title = Annotated[str, Field(min_length=1, max_length=500)]
Body = Annotated[str, Field(min_length=1, max_length=200_000)]
Order = Annotated[int, Field(ge=0)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CategoryInput(Input):
    name: ShortText
    slug: ShortText
    parent_id: PositiveId | None = None
    sort_order: Order = 0


class TagInput(Input):
    name: ShortText
    slug: ShortText


class ArticleInput(Input):
    title: Title
    slug: ShortText
    type: ContentType = ContentType.ARTICLE
    status: ContentStatus = ContentStatus.DRAFT
    category_id: PositiveId | None = None
    summary: Body | None = None
    published_at: AwareDatetime | None = None
    chunks: list[Body] = Field(min_length=1, max_length=256)


class ChunkInput(Input):
    content_item_id: PositiveId
    chunk_index: Order
    body: Body


class ArticleTagInput(Input):
    content_item_id: PositiveId
    tag_id: PositiveId


class GlossaryInput(Input):
    term: ShortText
    definition: Body
    full_definition: Body | None = None


class GlossaryLinkInput(Input):
    term_id: PositiveId
    content_item_id: PositiveId


class QAPairInput(Input):
    question: Body
    answer: Body
    category_id: PositiveId | None = None
    content_item_id: PositiveId | None = None
    sort_order: Order = 0


class SurveyInput(Input):
    title: Title
    version: Annotated[int, Field(ge=1)] = 1
    is_active: bool = True


class QuestionInput(Input):
    survey_id: PositiveId
    text: Body
    question_type: QuestionType = QuestionType.SINGLE_CHOICE
    sort_order: Order = 0
    is_required: bool = True


class OptionInput(Input):
    question_id: PositiveId
    text: Body
    value: ShortText
    sort_order: Order = 0


class ResultInput(Input):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    title: Title
    description: Body
    recommended_content_id: PositiveId | None = None
    recommended_document_template_id: PositiveId | None = None


class RuleInput(Input):
    survey_id: PositiveId
    result_id: PositiveId
    condition_json: dict[str, Any]
    priority: int = 0


class TemplateInput(Input):
    title: Title
    slug: ShortText
    document_type: DocumentType = DocumentType.CONTRACT
    description: Body | None = None
    body: Body
    file_path: Annotated[str, Field(max_length=1024)] | None = None
    is_active: bool = True
    constructor_schema: dict[str, Any] = Field(default_factory=dict, alias="schema_json")
    structure_json: dict[str, Any] = Field(default_factory=dict)


class ApplicationTypeInput(Input):
    code: Annotated[str, Field(min_length=1, max_length=100)]
    name: ShortText
    description: Body | None = None


class MktuInput(Input):
    class_number: Annotated[int, Field(ge=1, le=45)]
    title: Title
    description: Body | None = None


class FeeRateInput(Input):
    application_type_id: PositiveId
    mktu_class_id: PositiveId | None = None
    is_urgent: bool = False
    amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "RUB"
    valid_from: date
    valid_to: date | None = None
    legal_basis: Body

    @model_validator(mode="after")
    def check_dates(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("Дата окончания должна быть не раньше даты начала")
        return self
