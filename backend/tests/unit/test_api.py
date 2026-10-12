from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pgvector.sqlalchemy import VECTOR
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import CreateTable

from backend.main import (
    analyze_question,
    api_status,
    create_document,
    get_document,
    healthz,
    list_documents,
    readyz,
)
from backend.models import DocumentChunk
from backend.repository import DocumentRepository
from backend.schemas import AnalyzeRequest, DocumentCreate


def test_health_and_status() -> None:
    assert healthz() == {"status": "ok"}
    assert api_status() == {"status": "ok", "service": "melawdy-api"}


def test_readiness_checks_database_and_reports_failure() -> None:
    session = Mock()
    assert readyz(session) == {"status": "ready"}
    session.execute.assert_called_once()

    session.execute.side_effect = SQLAlchemyError("unavailable")
    with pytest.raises(HTTPException) as error:
        readyz(session)
    assert error.value.status_code == 503


def test_document_routes_delegate_to_repository() -> None:
    document_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        title="Договор",
        body="Текст документа",
        created_at=datetime.now(timezone.utc),
    )
    repository = Mock(spec=DocumentRepository)
    repository.create.return_value = document
    repository.list_documents.return_value = [document]
    repository.get.return_value = document

    payload = DocumentCreate(title=" Договор ", body=" Текст документа ")
    assert create_document(payload, repository) is document
    repository.create.assert_called_once_with(title="Договор", body="Текст документа")

    assert list_documents(repository, limit=10, offset=0) == [document]
    repository.list_documents.assert_called_once_with(limit=10, offset=0)

    assert get_document(document_id, repository) is document
    repository.get.assert_called_once_with(document_id)


def test_missing_document_returns_404() -> None:
    repository = Mock(spec=DocumentRepository)
    repository.get.return_value = None
    with pytest.raises(HTTPException) as error:
        get_document(uuid4(), repository)
    assert error.value.status_code == 404


def test_input_schemas_reject_blank_text() -> None:
    with pytest.raises(ValidationError):
        DocumentCreate(title="   ", body="Текст")
    with pytest.raises(ValidationError):
        DocumentCreate(title="Документ", body="   ")
    with pytest.raises(ValidationError):
        AnalyzeRequest(question="   ")


def test_analyze_contract_is_explicitly_unconfigured() -> None:
    response = analyze_question(AnalyzeRequest(question="Какие права у потребителя?"))
    assert response.model_ready is False
    assert response.status == "not_implemented"


def test_chunk_model_declares_pgvector_column() -> None:
    column = DocumentChunk.__table__.c.embedding
    assert isinstance(column.type, VECTOR)
    ddl = str(CreateTable(DocumentChunk.__table__).compile(dialect=postgresql.dialect()))
    assert "VECTOR" in ddl.upper()
