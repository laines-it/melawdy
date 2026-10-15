from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db import get_session
from backend.models import Document
from backend.repository import DocumentRepository
from backend.schemas import AnalyzeRequest, AnalyzeResponse, DocumentCreate, DocumentRead
from ml.pipeline import analyze
from backend import admin, auth, public, cabinet


app = FastAPI(title="MeLawDy API", version="0.1.0")
app.include_router(auth.router)
app.include_router(cabinet.router)
app.include_router(admin.router)
app.include_router(public.router)
SessionDep = Annotated[Session, Depends(get_session)]


def get_document_repository(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


RepositoryDep = Annotated[DocumentRepository, Depends(get_document_repository)]


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(session: SessionDep) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ready"}


@app.get("/api/v1/status")
def api_status() -> dict[str, str]:
    return {"status": "ok", "service": "melawdy-api"}


@app.post(
    "/api/v1/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_admin)],
)
def create_document(payload: DocumentCreate, repository: RepositoryDep) -> Document:
    return repository.create(title=payload.title, body=payload.body)


@app.get("/api/v1/documents", response_model=list[DocumentRead])
def list_documents(
    repository: RepositoryDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Document]:
    return repository.list_documents(limit=limit, offset=offset)


@app.get("/api/v1/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, repository: RepositoryDep) -> Document:
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze_question(payload: AnalyzeRequest) -> AnalyzeResponse:
    return analyze(payload.question)
