from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from backend.admin_resources import RESOURCES, Resource, metadata
from backend.auth import AdminDep, SessionDep, require_admin
from backend.models import ContentCategory, ContentItem, ContentItemChunk, ContentStatus

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def get_resource(key: str) -> Resource:
    resource = RESOURCES.get(key)
    if resource is None:
        raise HTTPException(404, "Раздел не найден")
    return resource


def identity(resource: Resource, key: str):
    names = [column.key for column in inspect(resource.model).primary_key]
    try:
        values = tuple(int(part) for part in key.split(":"))
        if len(values) != len(names) or any(value <= 0 for value in values):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "Некорректный ID записи") from exc
    return values[0] if len(values) == 1 else values


def serialize(resource: Resource, record) -> dict:
    result = {column.key: getattr(record, column.key) for column in inspect(resource.model).columns
              if column.key not in {"embedding", "tsv"}}
    keys = [getattr(record, column.key) for column in inspect(resource.model).primary_key]
    result["id"] = ":".join(str(value) for value in keys)
    if resource.key == "articles":
        result["chunks"] = [chunk.body for chunk in sorted(record.chunks, key=lambda chunk: chunk.chunk_index)]
    return jsonable_encoder(result, custom_encoder={Decimal: str})


def validated(resource: Resource, payload: dict[str, Any]) -> dict:
    try:
        return resource.schema.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, jsonable_encoder(exc.errors(include_input=False, include_context=False))) from exc


def apply_article_chunks(record: ContentItem, bodies: list[str]) -> None:
    existing = {chunk.chunk_index: chunk for chunk in record.chunks}
    for index, body in enumerate(bodies):
        if index in existing:
            existing[index].body = body
        else:
            record.chunks.append(ContentItemChunk(chunk_index=index, body=body))
    for chunk in list(record.chunks):
        if chunk.chunk_index >= len(bodies):
            record.chunks.remove(chunk)


def validate_parent(session, parent_id: int | None, record_id: int | None) -> None:
    visited = {record_id} if record_id is not None else set()
    while parent_id is not None:
        if parent_id in visited:
            raise HTTPException(422, "Категория не может содержать сама себя")
        visited.add(parent_id)
        parent = session.get(ContentCategory, parent_id)
        if parent is None:
            raise HTTPException(422, "Родительская категория не найдена")
        parent_id = parent.parent_id


def save_record(resource: Resource, payload: dict, session, user, record=None) -> dict:
    values = validated(resource, payload)
    bodies = values.pop("chunks", None)
    if resource.key == "categories":
        validate_parent(session, values.get("parent_id"), record.id if record else None)
    if resource.key == "articles" and values["status"] == ContentStatus.PUBLISHED:
        values["published_at"] = values["published_at"] or datetime.now(timezone.utc)
    if record is None:
        record = resource.model(**values)
        if resource.key == "articles":
            record.created_by = user.id
        session.add(record)
    else:
        for name, value in values.items():
            setattr(record, name, value)
    if bodies is not None:
        apply_article_chunks(record, bodies)
    try:
        session.commit()
        session.refresh(record)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Запись не сохранена: проверьте уникальность полей и связанные записи") from exc
    return serialize(resource, record)


@router.get("/resources")
def resources(response: Response) -> list[dict]:
    response.headers["Cache-Control"] = "no-store"
    return [metadata(resource) for resource in RESOURCES.values()]


@router.get("/lookups/{key}")
def lookups(key: str, session: SessionDep,
            search: Annotated[str, Query(max_length=100)] = "") -> list[dict]:
    resource = get_resource(key)
    if len(inspect(resource.model).primary_key) != 1:
        raise HTTPException(422, "Этот раздел не используется как справочник")
    label = getattr(resource.model, resource.label_field)
    statement = select(resource.model).order_by(resource.model.id.desc()).limit(500)
    if search:
        statement = statement.where(label.icontains(search, autoescape=True))
    return [{"id": str(record.id), "label": str(getattr(record, resource.label_field))[:120]}
            for record in session.scalars(statement)]


@router.get("/{key}")
def list_records(key: str, session: SessionDep,
                 limit: Annotated[int, Query(ge=1, le=100)] = 25,
                 offset: Annotated[int, Query(ge=0)] = 0) -> dict:
    resource = get_resource(key)
    statement = select(resource.model).order_by(*[column.desc() for column in inspect(resource.model).primary_key])
    if key == "articles":
        statement = statement.options(selectinload(ContentItem.chunks))
    records = session.scalars(statement.offset(offset).limit(limit))
    return {"items": [serialize(resource, record) for record in records],
            "total": session.scalar(select(func.count()).select_from(resource.model))}


@router.post("/{key}", status_code=201)
def create_record(key: str, payload: dict[str, Any], session: SessionDep, user: AdminDep) -> dict:
    return save_record(get_resource(key), payload, session, user)


@router.get("/{key}/{record_id}")
def get_record(key: str, record_id: str, session: SessionDep) -> dict:
    resource = get_resource(key)
    record = session.get(resource.model, identity(resource, record_id))
    if record is None:
        raise HTTPException(404, "Запись не найдена")
    return serialize(resource, record)


@router.put("/{key}/{record_id}")
def update_record(key: str, record_id: str, payload: dict[str, Any], session: SessionDep, user: AdminDep) -> dict:
    resource = get_resource(key)
    record = session.get(resource.model, identity(resource, record_id))
    if record is None:
        raise HTTPException(404, "Запись не найдена")
    return save_record(resource, payload, session, user, record)


@router.delete("/{key}/{record_id}", status_code=204, response_class=Response)
def delete_record(key: str, record_id: str, session: SessionDep) -> None:
    resource = get_resource(key)
    record = session.get(resource.model, identity(resource, record_id))
    if record is None:
        raise HTTPException(404, "Запись не найдена")
    try:
        # Let the database apply the declared RESTRICT / CASCADE / SET NULL rules.
        session.execute(delete(resource.model).where(*[
            column == getattr(record, column.key) for column in inspect(resource.model).primary_key
        ]))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "Запись используется в других разделах и не может быть удалена") from exc
