from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from backend.auth import SessionDep
from backend.content_repository import ContentSearchRepository
from backend.models import (
    AssessmentQuestion, AssessmentSurvey, ContentItem, ContentStatus, DocumentTemplate, QAPair,
)
from ml.tfidf import TfidfIndex

router = APIRouter(prefix="/api/v1/public", tags=["public"])



def _published_clause():
    """Единый фильтр: статья опубликована и дата публикации наступила."""
    return (
        ContentItem.status == ContentStatus.PUBLISHED,
        ContentItem.published_at <= func.now(),
    )


def _article_ref(item: ContentItem) -> dict:
    """Ссылочные поля статьи: id, slug, title, link_title."""
    return {
        "id": str(item.id),
        "slug": item.slug or "",
        "title": item.title,
        "link_title": getattr(item, "link_title", None),
    }



@router.get("/capabilities")
def capabilities() -> dict:
    return {"music_check": {"available": False,
                            "message": "Проверка аудиофайлов пока не подключена. Результаты проверки недоступны."}}



@router.get("/faq")
def list_faq(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 4) -> list[dict]:
    items = session.scalars(select(QAPair).outerjoin(ContentItem).where(or_(
        QAPair.content_item_id.is_(None),
        (ContentItem.status == ContentStatus.PUBLISHED) & (ContentItem.published_at <= func.now()),
    )).order_by(QAPair.sort_order, QAPair.id).limit(limit))

    result = []
    for item in items:
        article = item.content_item if item.content_item_id else None
        ref = _article_ref(article) if article else None
        result.append({
            "id": str(item.id),
            "question": item.question,
            "answer": item.answer,
            "content_item_id": ref["id"] if ref else None,
            "content_slug": ref["slug"] if ref else None,
            "content_title": ref["title"] if ref else None,
            "link_title": ref["link_title"] if ref else None,
        })
    return result


@router.get("/search")
def search(session: SessionDep, query: Annotated[str, Query(min_length=1, max_length=1000)],
           limit: Annotated[int, Query(ge=1, le=100)] = 10) -> list[dict]:
    if not query.strip():
        raise HTTPException(422, "Введите поисковый запрос")

    hits = TfidfIndex(ContentSearchRepository(session).list_chunks()).search(query, limit)
    if not hits:
        return []

    article_ids = {hit.chunk.content_item_id for hit in hits}
    rows = session.execute(
        select(
            ContentItem.id,
            ContentItem.title,
            ContentItem.slug,
            getattr(ContentItem, "link_title", None) if hasattr(ContentItem, "link_title") else ContentItem.title,
        ).where(
            ContentItem.id.in_(article_ids),
            *_published_clause(),
        )
    ).all()

    by_id = {}
    for row in rows:
        item_id, title, slug, link_title = row
        by_id[item_id] = {
            "id": str(item_id),
            "title": title,
            "slug": slug or "",
            "link_title": link_title,
        }

    result = []
    for hit in hits:
        ref = by_id.get(hit.chunk.content_item_id)
        if not ref:
            continue
        result.append({
            "article_id": ref["id"],
            "article_slug": ref["slug"],
            "title": ref["title"],
            "link_title": ref["link_title"],
            "body": hit.chunk.body,
            "score": hit.score,
        })
    return result



@router.get("/templates")
def list_templates(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                   offset: Annotated[int, Query(ge=0)] = 0) -> list[dict]:
    items = session.scalars(select(DocumentTemplate).where(DocumentTemplate.is_active.is_(True))
                            .order_by(DocumentTemplate.id.desc()).limit(limit).offset(offset))
    return [{"id": str(item.id), "title": item.title, "description": item.description} for item in items]


@router.get("/templates/{template_id}")
def read_template(template_id: int, session: SessionDep) -> dict:
    item = session.scalar(select(DocumentTemplate).where(
        DocumentTemplate.id == template_id, DocumentTemplate.is_active.is_(True)))
    if item is None:
        raise HTTPException(404, "Шаблон не найден")
    return {"id": str(item.id), "title": item.title, "description": item.description, "body": item.body,
            "slug": item.slug, "document_type": item.document_type,
            "schema_json": item.schema_json or {}, "structure_json": item.structure_json or {}}



@router.get("/articles")
def list_articles(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                  offset: Annotated[int, Query(ge=0)] = 0) -> list[dict]:
    items = session.scalars(select(ContentItem).where(
        *_published_clause(),
    ).order_by(ContentItem.published_at.desc(), ContentItem.id.desc()).limit(limit).offset(offset))

    result = []
    for item in items:
        ref = _article_ref(item)
        result.append({
            **ref,
            "summary": item.summary,
            "published_at": item.published_at,
        })
    return result


@router.get("/articles/{key}")
def read_article(key: str, session: SessionDep) -> dict:
    """Read a published article by its stored slug or legacy numeric ID."""
    key = str(key)
    if not key or len(key) > 255 or not all(ch.isalnum() or ch in "-_" for ch in key):
        raise HTTPException(404, "Статья не найдена")

    stmt = select(ContentItem).options(
        selectinload(ContentItem.chunks),
        selectinload(ContentItem.category),
    ).where(*_published_clause())

    if key.isascii() and key.isdigit():
        if not 1 <= int(key) <= 9223372036854775807:
            raise HTTPException(404, "Статья не найдена")
        stmt = stmt.where(ContentItem.id == int(key))
    else:
        stmt = stmt.where(ContentItem.slug == key)

    item = session.scalar(stmt)
    if item is None:
        raise HTTPException(404, "Статья не найдена")

    category = None
    if item.category is not None:
        category = {"id": str(item.category.id), "name": item.category.name or ""}

    chunks = [chunk.body for chunk in sorted(item.chunks, key=lambda c: c.chunk_index) if chunk.body]

    return {
        **_article_ref(item),
        "summary": item.summary,
        "published_at": item.published_at,
        "category": category,
        "chunks": chunks,
    }



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
