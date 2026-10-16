from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from backend.auth import SessionDep, UserDep
from backend.models import ApplicationType, FeeCalculation, FeeCalculationClass, FeeRate, MktuClass

router = APIRouter(prefix="/api/v1/public/fees", tags=["fees"])


class CalculationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_type_id: Annotated[int, Field(gt=0)]
    mktu_class_id: Annotated[int, Field(gt=0)] | None = None
    is_urgent: bool = False
    quantity: Annotated[int, Field(ge=1, le=100)] = 1


def effective_rates():
    today = datetime.now(timezone.utc).date()
    return (FeeRate.valid_from <= today,
            or_(FeeRate.valid_to.is_(None), FeeRate.valid_to >= today))


@router.get("/catalog")
def catalog(session: SessionDep) -> dict:
    applications = session.scalars(select(ApplicationType).order_by(ApplicationType.name)).all()
    classes = session.scalars(select(MktuClass).order_by(MktuClass.class_number)).all()
    rates = session.scalars(select(FeeRate).where(*effective_rates()).order_by(FeeRate.id)).all()
    return {
        "application_types": [{"id": str(item.id), "name": item.name,
                               "description": item.description} for item in applications],
        "mktu_classes": [{"id": str(item.id), "class_number": item.class_number,
                          "title": item.title, "description": item.description} for item in classes],
        "rates": [{"application_type_id": str(rate.application_type_id),
                   "mktu_class_id": str(rate.mktu_class_id) if rate.mktu_class_id is not None else None,
                   "is_urgent": rate.is_urgent} for rate in rates],
    }


@router.post("/calculate")
def calculate(payload: CalculationInput, session: SessionDep) -> dict:
    rates = session.scalars(select(FeeRate).where(
        FeeRate.application_type_id == payload.application_type_id,
        FeeRate.mktu_class_id == payload.mktu_class_id,
        FeeRate.is_urgent == payload.is_urgent,
        *effective_rates(),
    )).all()
    if not rates:
        raise HTTPException(404, "Действующая ставка для выбранных параметров не настроена")
    if len(rates) != 1:
        raise HTTPException(409, "Периоды ставок пересекаются. Обратитесь к администратору")
    rate = rates[0]
    total = (rate.amount * payload.quantity).quantize(Decimal("0.01"))
    if total > Decimal("999999999999.99"):
        raise HTTPException(422, "Сумма расчёта превышает допустимое значение")
    return {"rate_id": str(rate.id), "unit_amount": str(rate.amount),
            "quantity": payload.quantity, "total_amount": str(total),
            "currency": rate.currency, "legal_basis": rate.legal_basis,
            "valid_from": rate.valid_from.isoformat(),
            "valid_to": rate.valid_to.isoformat() if rate.valid_to else None}


@router.post("/calculations", status_code=201)
def save_calculation(payload: CalculationInput, session: SessionDep, user: UserDep) -> dict:
    result = calculate(payload, session)
    record = FeeCalculation(
        user_id=user.id, application_type_id=payload.application_type_id,
        is_urgent=payload.is_urgent, total_amount=Decimal(result["total_amount"]),
        currency=result["currency"], input_json=payload.model_dump(), breakdown_json=result,
    )
    if payload.mktu_class_id is not None:
        record.class_links.append(FeeCalculationClass(mktu_class_id=payload.mktu_class_id))
    session.add(record)
    session.commit()
    session.refresh(record)
    return {"id": str(record.id), **result}
