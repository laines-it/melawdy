import ast
import operator
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from backend.auth import SessionDep, UserDep
from backend.import_fees import CATALOG_CODE
from backend.models import ApplicationType, FeeCalculation, FeeCatalog

router = APIRouter(prefix="/api/v1/public/fees/tree", tags=["fees"])


class TreeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    procedure_id: str
    stages: list[str] = Field(default_factory=list)
    classes: int = Field(default=1, ge=1, le=10000)
    item_names_per_class: int = Field(default=1, ge=1, le=1000000)
    need_paper_certificate: bool = False
    court_id: str | None = None
    claim_type: str | None = None
    claim_amount: Decimal = Field(default=Decimal(0), ge=0, le=Decimal("999999999999.99"))
    complaint: str | None = None
    applicant: str | None = None


def choose(items: list[dict], value: str | None, key: str = "id") -> dict:
    for item in items:
        if item.get(key) == value:
            return item
    raise HTTPException(422, "Выберите все параметры процедуры")


def formula(expression: str, values: dict) -> Decimal:
    """Evaluate only arithmetic, parameter names and max from the stored formula."""
    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name) and node.id in values:
            return Decimal(values[node.id])
        operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}
        if isinstance(node, ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](evaluate(node.left), evaluate(node.right))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "max" and node.args and not node.keywords):
            return max(evaluate(argument) for argument in node.args)
        raise HTTPException(422, "Неподдерживаемая формула в справочнике")

    return evaluate(ast.parse(expression, mode="eval").body)


@router.get("")
def catalog(session: SessionDep) -> dict:
    record = session.get(FeeCatalog, CATALOG_CODE)
    if record is None:
        raise HTTPException(503, "Справочник пошлин ещё не загружен")
    return record.source_json


@router.post("/calculate")
def calculate(payload: TreeInput, session: SessionDep) -> dict:
    source = catalog(session)
    entries = source["procedures"] + source["service_selection"]["options"]
    procedure = choose(entries, payload.procedure_id)
    values = {"classes": payload.classes, "item_names_per_class": payload.item_names_per_class,
              "claim_amount": payload.claim_amount}
    fees = []
    if "stage_selection" in procedure:
        stages = set(payload.stages)
        if payload.need_paper_certificate:
            stages.add("paper_certificate")
        if not stages:
            raise HTTPException(422, "Выберите хотя бы один этап")
        for stage_id in sorted(stages):
            fees.append(choose(procedure["stage_selection"]["stages"], stage_id))
    elif "court_selection" in procedure:
        if payload.claim_type in ("rospatent_appeal", "appeals"):
            branch = procedure[payload.claim_type]
            if payload.claim_type == "appeals":
                court = choose(procedure["court_selection"]["options"], payload.court_id)
                branch = choose(branch["courts"], court["name"], "court")
                branch = choose(branch["complaints"], payload.complaint, "name")
            fees.append({"name": branch.get("name", procedure[payload.claim_type]["name"]),
                         **choose(branch["options"], payload.applicant, "applicant")})
        else:
            court = choose(procedure["court_selection"]["options"], payload.court_id)
            claim = choose(procedure["claim_type"]["options"], payload.claim_type)
            if claim["id"] == "property":
                property_claim = court["property_claim"]
                tier = next((tier for tier in property_claim["fee_tiers"]
                             if tier["to"] is None or payload.claim_amount <= tier["to"]), None)
                if tier is None:
                    raise HTTPException(422, "Для этой суммы иска в справочнике нет ставки")
                amount = min(formula(tier["formula"], values), Decimal(property_claim["maximum_fee"]))
                fees.append({"name": claim["name"], "fee": {"type": "fixed", "amount": amount,
                             "original": tier["original"], "currency": property_claim["fee_currency"]}})
            else:
                branch = choose(claim["courts"], court["name"], "court")
                fees.append({"name": claim["name"],
                             **choose(branch["options"], payload.applicant, "applicant")})
    else:
        fees.append(procedure)

    breakdown = []
    for item in fees:
        fee = item["fee"]
        amount = (formula(fee["expression"], values) if fee["type"] == "formula"
                  else Decimal(str(fee.get("amount", fee.get("min", 0)))))
        maximum = Decimal(str(fee.get("max", amount)))
        breakdown.append({"name": item["name"], "amount": str(amount.quantize(Decimal("0.01"))),
                          "max_amount": str(maximum.quantize(Decimal("0.01"))),
                          "formula": fee.get("original", ""), "note": item.get("note", "")})
    total = sum((Decimal(item["amount"]) for item in breakdown), Decimal(0))
    maximum = sum((Decimal(item["max_amount"]) for item in breakdown), Decimal(0))
    if maximum > Decimal("999999999999.99"):
        raise HTTPException(422, "Сумма расчёта превышает допустимое значение")
    return {"name": procedure["name"], "total_amount": str(total), "total_max_amount": str(maximum),
            "currency": fees[0]["fee"]["currency"],
            "approximate": procedure.get("fee", {}).get("type") == "approximate_range",
            "breakdown": breakdown}


@router.post("/calculations", status_code=201)
def save_calculation(payload: TreeInput, session: SessionDep, user: UserDep) -> dict:
    result = calculate(payload, session)
    application_id = session.scalar(select(ApplicationType.id).where(ApplicationType.code == payload.procedure_id))
    if application_id is None:
        raise HTTPException(503, "Процедура ещё не загружена")
    record = FeeCalculation(
        user_id=user.id, application_type_id=application_id, is_urgent=False,
        total_amount=Decimal(result["total_amount"]), currency=result["currency"],
        input_json=payload.model_dump(mode="json"), breakdown_json=result,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return {"id": str(record.id), **result}
