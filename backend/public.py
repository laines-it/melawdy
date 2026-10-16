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
    return [{"id": str(item.id), "question": item.question, "answer": item.answer,
             "content_item_id": str(item.content_item_id) if item.content_item_id else None} for item in items]


@router.get("/search")
def search(session: SessionDep, query: Annotated[str, Query(min_length=1, max_length=1000)],
           limit: Annotated[int, Query(ge=1, le=100)] = 10) -> list[dict]:
    if not query.strip():
        raise HTTPException(422, "Введите поисковый запрос")
    hits = TfidfIndex(ContentSearchRepository(session).list_chunks()).search(query, limit)
    if not hits:
        return []
    titles = dict(session.execute(select(ContentItem.id, ContentItem.title).where(
        ContentItem.id.in_({hit.chunk.content_item_id for hit in hits}),
        ContentItem.status == ContentStatus.PUBLISHED, ContentItem.published_at <= func.now(),
    )).all())
    return [{"article_id": str(hit.chunk.content_item_id), "title": titles[hit.chunk.content_item_id],
             "body": hit.chunk.body, "score": hit.score} for hit in hits if hit.chunk.content_item_id in titles]


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
    return {"id": str(item.id), "title": item.title, "description": item.description, "body": item.body}


@router.get("/articles")
def list_articles(session: SessionDep, limit: Annotated[int, Query(ge=1, le=100)] = 25,
                  offset: Annotated[int, Query(ge=0)] = 0) -> list[dict]:
    items = session.scalars(select(ContentItem).where(
        ContentItem.status == ContentStatus.PUBLISHED, ContentItem.published_at <= func.now()
    ).order_by(ContentItem.published_at.desc(), ContentItem.id.desc()).limit(limit).offset(offset))
    return [{"id": str(item.id), "title": item.title, "slug": item.slug,
             "summary": item.summary, "published_at": item.published_at} for item in items]


@router.get("/articles/{article_id}")
def read_article(article_id: int, session: SessionDep) -> dict:
    item = session.scalar(select(ContentItem).options(selectinload(ContentItem.chunks)).where(
        ContentItem.id == article_id, ContentItem.status == ContentStatus.PUBLISHED,
        ContentItem.published_at <= func.now()))
    if item is None:
        raise HTTPException(404, "Статья не найдена")
    return {"id": str(item.id), "title": item.title, "summary": item.summary,
            "chunks": [chunk.body for chunk in item.chunks]}


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
