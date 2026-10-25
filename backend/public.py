from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from backend.auth import SessionDep
from backend.content_repository import ContentSearchRepository
from backend.models import (
    AssessmentQuestion, AssessmentSurvey, ContentItem, ContentStatus, DocumentTemplate, QAPair,
)
from backend.schemas import SearchResponse
from ml.embedding_search import search_embeddings
from ml.embeddings import EmbeddingConfigurationError
from ml.tfidf import TfidfIndex

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/capabilities")
def capabilities() -> dict:
    return {"music_check": {"available": False,
                            "message": "Проверка аудиофайлов пока не подключена. Результаты проверки недоступны."}}


@router.get("/faq")
def list_faq(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 4) -> list[dict]:
    items = session.scalars(select(QAPair).outerjoin(ContentItem).options(selectinload(QAPair.content_item)).where(or_(
        QAPair.content_item_id.is_(None),
        (ContentItem.status == ContentStatus.PUBLISHED) & (ContentItem.published_at <= func.now()),
    )).order_by(QAPair.sort_order, QAPair.id).limit(limit))
    return [{"id": str(item.id), "question": item.question, "answer": item.answer,
         "content_item_id": str(item.content_item_id) if item.content_item_id else None,
         "content_item_slug": item.content_item.slug if item.content_item else None} for item in items]


@router.get("/search", response_model=list[SearchResponse])
def search(session: SessionDep, query: Annotated[str, Query(min_length=1, max_length=1000)],
           limit: Annotated[int, Query(ge=1, le=100)] = 10,
           method: Literal["embeddings", "tfidf"] = "embeddings") -> list[dict]:
    if not query.strip():
        raise HTTPException(422, "Введите поисковый запрос")
    try:
        hits = (search_embeddings(query, session=session, limit=limit) if method == "embeddings"
                else TfidfIndex(ContentSearchRepository(session).list_chunks()).search(query, limit))
    except EmbeddingConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not hits:
        return []
    metadata = {row.id: row for row in session.execute(select(
        ContentItem.id, ContentItem.title, ContentItem.summary, ContentItem.slug,
    ).where(
        ContentItem.id.in_({hit.chunk.content_item_id for hit in hits}),
        ContentItem.status == ContentStatus.PUBLISHED, ContentItem.published_at <= func.now(),
    )).all()}
    ids = list(dict.fromkeys(hit.chunk.content_item_id for hit in hits
                             if hit.chunk.content_item_id in metadata))
    return [{"article_id": str(article_id), "slug": metadata[article_id].slug, "title": metadata[article_id].title,
             "body": metadata[article_id].summary or "", "summary": metadata[article_id].summary}
            for article_id in ids]


@router.get("/templates")
def list_templates(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                   offset: Annotated[int, Query(ge=0)] = 0) -> list[dict]:
    items = session.scalars(select(DocumentTemplate).where(DocumentTemplate.is_active.is_(True))
                            .order_by(DocumentTemplate.id.desc()).limit(limit).offset(offset))
    return [{"id": str(item.id), "title": item.title, "description": item.description} for item in items]


@router.get("/templates/{template_id:int}")
def read_template(template_id: int, session: SessionDep) -> dict:
    item = session.scalar(select(DocumentTemplate).where(
        DocumentTemplate.id == template_id, DocumentTemplate.is_active.is_(True)))
    if item is None:
        raise HTTPException(404, "Шаблон не найден")
    return {"id": str(item.id), "title": item.title, "description": item.description, "body": item.body,
            "slug": item.slug, "document_type": item.document_type,
            "schema_json": item.schema_json or {}, "structure_json": item.structure_json or {}}


@router.get("/templates/{slug}")
def read_template_by_slug(slug: str, session: SessionDep) -> dict:
    item = session.scalar(select(DocumentTemplate).where(
        DocumentTemplate.slug == slug, DocumentTemplate.is_active.is_(True)))
    if item is None:
        raise HTTPException(404, "Шаблон не найден")
    return {"id": str(item.id), "title": item.title, "description": item.description,
            "body": item.body, "slug": item.slug, "document_type": item.document_type,
            "schema_json": item.schema_json or {}, "structure_json": item.structure_json or {}}

@router.get("/articles")
def list_articles(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                  offset: Annotated[int, Query(ge=0)] = 0) -> list[dict]:
    items = session.scalars(select(ContentItem).where(
        ContentItem.status == ContentStatus.PUBLISHED, ContentItem.published_at <= func.now()
    ).order_by(ContentItem.published_at.desc(), ContentItem.id.desc()).limit(limit).offset(offset))
    return [{"id": str(item.id), "title": item.title, "slug": item.slug,
             "summary": item.summary, "published_at": item.published_at} for item in items]


@router.get("/articles/{slug}")
def read_article_by_slug(slug: str, session: SessionDep) -> dict:
    item = session.scalar(select(ContentItem).options(
        selectinload(ContentItem.chunks), selectinload(ContentItem.category),
    ).where(
        ContentItem.slug == slug,
        ContentItem.status == ContentStatus.PUBLISHED,
        ContentItem.published_at <= func.now(),
    ))
    if item is None:
        raise HTTPException(404, "Статья не найдена")
    return {"id": str(item.id), "slug": item.slug, "title": item.title,
            "summary": item.summary,
            "published_at": item.published_at, "updated_at": item.updated_at,
            "category": {"id": str(item.category.id), "name": item.category.name} if item.category else None,
            "chunks": [chunk.body for chunk in sorted(item.chunks, key=lambda c: c.chunk_index)]}


@router.get("/articles/{article_id}")
def read_article(article_id: int, session: SessionDep) -> dict:
    item = session.scalar(select(ContentItem).options(
        selectinload(ContentItem.chunks), selectinload(ContentItem.category),
    ).where(
        ContentItem.id == article_id, ContentItem.status == ContentStatus.PUBLISHED,
        ContentItem.published_at <= func.now()))
    if item is None:
        raise HTTPException(404, "Статья не найдена")
    return {"id": str(item.id), "title": item.title, "summary": item.summary,
            "published_at": item.published_at, "updated_at": item.updated_at,
            "category": {"id": str(item.category.id), "name": item.category.name} if item.category else None,
            "chunks": [chunk.body for chunk in sorted(item.chunks, key=lambda chunk: chunk.chunk_index)]}


@router.get("/surveys")
def list_surveys(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                 offset: Annotated[int, Query(ge=0)] = 0) -> list[dict]:
    surveys = session.scalars(select(AssessmentSurvey).where(AssessmentSurvey.is_active.is_(True))
                              .order_by(AssessmentSurvey.id.desc()).limit(limit).offset(offset))
    return [{"id": str(survey.id), "title": survey.title, "version": survey.version} for survey in surveys]


@router.get("/surveys/{survey_id}")
def read_survey(survey_id: int, session: SessionDep) -> dict:
    survey = session.scalar(select(AssessmentSurvey).options(
        selectinload(AssessmentSurvey.questions).selectinload(AssessmentQuestion.options)
    ).where(AssessmentSurvey.id == survey_id, AssessmentSurvey.is_active.is_(True)))
    if survey is None:
        raise HTTPException(404, "Опрос не найден")
    return {"id": str(survey.id), "title": survey.title, "version": survey.version,
            "questions": [{"id": str(question.id), "text": question.text,
                           "question_type": question.question_type, "is_required": question.is_required,
                           "options": [{"text": option.text, "value": option.value}
                                       for option in question.options]}
                          for question in survey.questions]}
