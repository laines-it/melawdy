from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from backend.main import (
    analyze_question,
    api_status,
    create_document,
    get_document,
    healthz,
    list_documents,
    readyz,
)
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
