from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from backend.auth import SessionDep
from backend.models import AssessmentQuestion, AssessmentSurvey, ContentItem, ContentStatus

router = APIRouter(prefix="/api/v1/public", tags=["public"])


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
