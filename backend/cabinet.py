import json
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from fastapi.responses import Response
from pydantic import BaseModel, Field
from backend.agreement import build_agreement



from backend.auth import SessionDep, UserDep
from backend.models import (
    ContentItem,
    ContentStatus,
    DeadlineStatus,
    DocumentStatus,
    DocumentStatusHistory,
    DocumentTemplate,
    DocumentType,
    FeeCalculation,
    RequestHistory,
    UserAssessment,
    UserDocument,
    UserFavorite,
)

router = APIRouter(prefix="/api/v1/cabinet", tags=["cabinet"])

ACTIVE_STATUSES = (DocumentStatus.DRAFT, DocumentStatus.IN_PROGRESS)
UPCOMING_DAYS = 7
MAX_CONTENT_BYTES = 64 * 1024
MAX_DOCUMENTS_PER_USER = 500
MAX_FAVORITES_PER_USER = 1000

RecordId = Annotated[int, Path(gt=0, lt=2 ** 63)]
DocumentTypeName = Literal["contract", "claim", "application", "other"]


def limit_content_size(value: dict[str, Any]) -> dict[str, Any]:
    try:
        size = len(json.dumps(value, ensure_ascii=False).encode())
    except (TypeError, RecursionError) as exc:
        raise ValueError("Содержимое документа не удалось обработать") from exc
    if size > MAX_CONTENT_BYTES:
        raise ValueError("Содержимое документа слишком большое")
    return value


class ProfileOut(BaseModel):
    id: int
    email: str
    full_name: str
    user_type: str
    last_login_at: datetime | None = None
    is_active: bool


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    document_type: DocumentTypeName = "other"
    content_json: dict[str, Any] = Field(default_factory=dict)
    due_date: date | None = None
    template_id: int | None = Field(default=None, gt=0, lt=2 ** 63)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Укажите название документа")
        return value

    @field_validator("content_json")
    @classmethod
    def check_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        return limit_content_size(value)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=500)
    document_type: DocumentTypeName | None = None
    status: Literal["draft", "in_progress", "completed", "archived"] | None = None
    content_json: dict[str, Any] | None = None
    due_date: date | None = None
    comment: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        return value

    @field_validator("content_json")
    @classmethod
    def check_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else limit_content_size(value)

    @model_validator(mode="after")
    def check_fields(self):
        sent = self.model_fields_set
        if not sent:
            raise ValueError("Нет данных для изменения")
        for name in ("title", "document_type", "status", "content_json", "comment"):
            if name in sent and getattr(self, name) is None:
                raise ValueError(f"Поле {name} не может быть null")
        if "comment" in sent and "status" not in sent:
            raise ValueError("Комментарий можно указать только вместе со статусом")
        return self


class StatusEntryOut(BaseModel):
    old_status: str | None
    new_status: str
    comment: str | None
    changed_at: datetime | None = None


class DocumentOut(BaseModel):
    id: int
    title: str
    document_type: str
    status: str
    due_date: date | None
    deadline_status: str
    template_id: int | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentDetailOut(DocumentOut):
    content_json: dict[str, Any]
    status_history: list[StatusEntryOut]


class FavoriteOut(BaseModel):
    id: int
    content_item_id: int
    title: str
    slug: str
    summary: str | None
    type: str
    published_at: datetime | None = None
    created_at: datetime | None = None

class AgreementIn(BaseModel):
    work_type: str = Field(default="Музыкальное произведение с текстом")



def _enum_val(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def today() -> date:
    return datetime.now(timezone.utc).date()


def deadline_status(doc_status: DocumentStatus, due_date: date | None, day: date) -> DeadlineStatus:
    if due_date is None:
        return DeadlineStatus.NONE
    if doc_status == DocumentStatus.COMPLETED:
        return DeadlineStatus.COMPLETED
    if doc_status not in ACTIVE_STATUSES:
        return DeadlineStatus.NONE
    if due_date < day:
        return DeadlineStatus.OVERDUE
    if due_date <= day + timedelta(days=UPCOMING_DAYS):
        return DeadlineStatus.UPCOMING
    return DeadlineStatus.NONE


def published_articles() -> tuple:
    return (ContentItem.status == ContentStatus.PUBLISHED, ContentItem.published_at <= func.now())


def count(session, model, *conditions) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def favorites_count(session, user) -> int:
    return session.scalar(
        select(func.count()).select_from(UserFavorite)
        .join(ContentItem, ContentItem.id == UserFavorite.content_item_id)
        .where(UserFavorite.user_id == user.id, *published_articles())) or 0


def get_own_document(session, user, document_id: int, with_history: bool = False) -> UserDocument:
    statement = select(UserDocument).where(
        UserDocument.id == document_id, UserDocument.user_id == user.id)
    if with_history:
        statement = statement.options(selectinload(UserDocument.status_history))
    doc = session.scalar(statement)
    if doc is None:
        raise HTTPException(404, "Документ не найден")
    return doc


def _document_out(doc: UserDocument, day: date) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        document_type=_enum_val(doc.document_type),
        status=_enum_val(doc.status),
        due_date=doc.due_date,
        deadline_status=_enum_val(deadline_status(doc.status, doc.due_date, day)),
        template_id=doc.template_id,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _document_detail(doc: UserDocument, day: date) -> DocumentDetailOut:
    return DocumentDetailOut(
        **_document_out(doc, day).model_dump(),
        content_json=doc.content_json or {},
        status_history=[
            StatusEntryOut(
                old_status=None if item.old_status is None else _enum_val(item.old_status),
                new_status=_enum_val(item.new_status),
                comment=item.comment,
                changed_at=item.changed_at,
            )
            for item in doc.status_history
        ],
    )


def _favorite_out(fav: UserFavorite) -> FavoriteOut:
    item = fav.content_item
    return FavoriteOut(
        id=fav.id,
        content_item_id=item.id,
        title=item.title,
        slug=item.slug,
        summary=item.summary,
        type=_enum_val(item.type),
        published_at=item.published_at,
        created_at=fav.created_at,
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: UserDep) -> ProfileOut:
    return ProfileOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        user_type=_enum_val(user.user_type),
        last_login_at=user.last_login_at,
        is_active=user.is_active,
    )


@router.get("/summary")
def summary(user: UserDep, session: SessionDep) -> dict:
    day = today()
    by_status = {item.value: 0 for item in DocumentStatus}
    for doc_status, amount in session.execute(
            select(UserDocument.status, func.count())
                    .where(UserDocument.user_id == user.id).group_by(UserDocument.status)):
        by_status[_enum_val(doc_status)] = amount
    active_with_due = (UserDocument.user_id == user.id, UserDocument.status.in_(ACTIVE_STATUSES),
                       UserDocument.due_date.is_not(None))
    overdue = count(session, UserDocument, *active_with_due, UserDocument.due_date < day)
    upcoming = count(session, UserDocument, *active_with_due, UserDocument.due_date >= day,
                     UserDocument.due_date <= day + timedelta(days=UPCOMING_DAYS))
    next_deadline = session.scalar(select(func.min(UserDocument.due_date)).where(
        *active_with_due, UserDocument.due_date >= day))
    favorites = favorites_count(session, user)
    calculations = count(session, FeeCalculation, FeeCalculation.user_id == user.id)
    requests = count(session, RequestHistory, RequestHistory.user_id == user.id)
    assessments = count(session, UserAssessment, UserAssessment.user_id == user.id)
    return {
        "documents": {"total": sum(by_status.values()), "by_status": by_status,
                      "overdue": overdue, "upcoming": upcoming, "next_deadline": next_deadline},
        "favorites": favorites,
        "calculations": calculations,
        "requests": requests,
        "assessments": assessments,
    }


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
        user: UserDep,
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
) -> list[DocumentOut]:
    q = select(UserDocument).where(UserDocument.user_id == user.id)
    if status_filter is not None:
        q = q.where(UserDocument.status == status_filter)
    q = q.order_by(UserDocument.updated_at.desc(), UserDocument.id.desc()).limit(limit).offset(offset)
    day = today()
    return [_document_out(d, day) for d in session.scalars(q).all()]


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: RecordId, user: UserDep, session: SessionDep) -> DocumentDetailOut:
    return _document_detail(get_own_document(session, user, document_id, with_history=True), today())


@router.post("/documents", response_model=DocumentDetailOut, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, user: UserDep, session: SessionDep) -> DocumentDetailOut:
    if count(session, UserDocument, UserDocument.user_id == user.id) >= MAX_DOCUMENTS_PER_USER:
        raise HTTPException(409, "Достигнут лимит документов")
    if payload.template_id is not None:
        template = session.get(DocumentTemplate, payload.template_id)
        if template is None or not template.is_active:
            raise HTTPException(422, "Шаблон не найден")
    day = today()
    doc = UserDocument(
        user_id=user.id,
        title=payload.title,
        document_type=DocumentType(payload.document_type),
        content_json=payload.content_json,
        due_date=payload.due_date,
        template_id=payload.template_id,
        status=DocumentStatus.DRAFT,
    )
    doc.deadline_status = deadline_status(doc.status, doc.due_date, day)
    doc.status_history.append(
        DocumentStatusHistory(old_status=None, new_status=DocumentStatus.DRAFT, changed_by=user.id))
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return _document_detail(doc, day)


@router.patch("/documents/{document_id}", response_model=DocumentDetailOut)
def update_document(document_id: RecordId, payload: DocumentUpdate, user: UserDep,
                    session: SessionDep) -> DocumentDetailOut:
    doc = get_own_document(session, user, document_id, with_history=True)
    data = payload.model_dump(exclude_unset=True)
    comment = data.pop("comment", None)
    new_status = data.pop("status", None)
    if "document_type" in data:
        data["document_type"] = DocumentType(data["document_type"])
    for key, value in data.items():
        setattr(doc, key, value)
    if new_status is not None:
        new_status = DocumentStatus(new_status)
        if new_status != doc.status:
            doc.status_history.append(DocumentStatusHistory(
                old_status=doc.status, new_status=new_status, comment=comment, changed_by=user.id))
            doc.status = new_status
        elif comment is not None:
            doc.status_history.append(DocumentStatusHistory(
                old_status=doc.status,
                new_status=doc.status,
                comment=comment,
                changed_by=user.id,
            ))
    day = today()
    doc.deadline_status = deadline_status(doc.status, doc.due_date, day)
    session.commit()
    session.refresh(doc)
    return _document_detail(doc, day)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_document(document_id: RecordId, user: UserDep, session: SessionDep) -> None:
    doc = get_own_document(session, user, document_id)
    session.execute(delete(DocumentStatusHistory).where(DocumentStatusHistory.document_id == doc.id))
    session.execute(delete(UserDocument).where(
        UserDocument.id == doc.id, UserDocument.user_id == user.id))
    session.commit()


@router.get("/favorites", response_model=list[FavoriteOut])
def list_favorites(
        user: UserDep,
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FavoriteOut]:
    q = (
        select(UserFavorite)
        .join(ContentItem, ContentItem.id == UserFavorite.content_item_id)
        .options(selectinload(UserFavorite.content_item))
        .where(UserFavorite.user_id == user.id, *published_articles())
        .order_by(UserFavorite.created_at.desc(), UserFavorite.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_favorite_out(f) for f in session.scalars(q).all()]


@router.post("/favorites/{content_item_id}", response_model=FavoriteOut, status_code=status.HTTP_201_CREATED)
def add_favorite(content_item_id: RecordId, user: UserDep, session: SessionDep) -> FavoriteOut:
    item = session.scalar(select(ContentItem).where(ContentItem.id == content_item_id, *published_articles()))
    if item is None:
        raise HTTPException(404, "Статья не найдена или не опубликована")

    existing = session.scalar(
        select(UserFavorite)
        .options(selectinload(UserFavorite.content_item))
        .where(UserFavorite.user_id == user.id, UserFavorite.content_item_id == content_item_id)
    )
    if existing is not None:
        return _favorite_out(existing)

    if favorites_count(session, user) >= MAX_FAVORITES_PER_USER:
        raise HTTPException(409, "Достигнут лимит избранного")

    fav = UserFavorite(user_id=user.id, content_item_id=content_item_id)
    session.add(fav)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Уже в избранном")

    fav = session.scalar(
        select(UserFavorite)
        .options(selectinload(UserFavorite.content_item))
        .where(UserFavorite.id == fav.id)
    )
    return _favorite_out(fav)


@router.delete("/favorites/{content_item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def remove_favorite(content_item_id: RecordId, user: UserDep, session: SessionDep) -> None:
    fav = session.scalar(select(UserFavorite).where(
        UserFavorite.user_id == user.id, UserFavorite.content_item_id == content_item_id))
    if fav is None:
        raise HTTPException(404, "В избранном нет этой статьи")
    session.delete(fav)
    session.commit()

@router.post("/documents/coauthors-agreement")
def create_coauthors_agreement(payload: AgreementIn, user: UserDep) -> Response:
    raw = build_agreement(payload.work_type)
    return Response(
        content=raw,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="agreement.docx"'},
    )
