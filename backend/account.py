from fastapi import APIRouter, Response
from sqlalchemy import func, select

from backend.auth import SessionDep, UserDep
from backend.models import AssessmentSurvey, ContentItem, ContentStatus, FeeCalculation, UserDocument

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.get("/overview")
def overview(response: Response, session: SessionDep, user: UserDep) -> dict:
    response.headers["Cache-Control"] = "no-store"
    documents = session.scalars(select(UserDocument).where(UserDocument.user_id == user.id)
                               .order_by(UserDocument.created_at.desc(), UserDocument.id.desc()).limit(25))
    calculations = session.scalars(select(FeeCalculation).where(FeeCalculation.user_id == user.id)
                                  .order_by(FeeCalculation.created_at.desc(), FeeCalculation.id.desc()).limit(25))
    return {
        "stats": {
            "documents": session.scalar(select(func.count()).select_from(UserDocument)
                                        .where(UserDocument.user_id == user.id)),
            "articles": session.scalar(select(func.count()).select_from(ContentItem).where(
                ContentItem.status == ContentStatus.PUBLISHED, ContentItem.published_at <= func.now())),
            "surveys": session.scalar(select(func.count()).select_from(AssessmentSurvey)
                                      .where(AssessmentSurvey.is_active.is_(True))),
        },
        "documents": [{"id": str(item.id), "title": item.title, "status": item.status,
                       "due_date": item.due_date} for item in documents],
        "calculations": [{"id": str(item.id), "total_amount": str(item.total_amount),
                          "currency": item.currency, "created_at": item.created_at}
                         for item in calculations],
    }
