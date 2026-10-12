from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.models import Document
from backend.repository import DocumentRepository


def test_create_document_uses_session() -> None:
    session = Mock(spec=Session)
    repository = DocumentRepository(session)

    document = repository.create("Заголовок", "Содержание")

    assert isinstance(document, Document)
    assert document.title == "Заголовок"
    assert document.body == "Содержание"
    session.add.assert_called_once_with(document)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(document)


def test_get_document_uses_primary_key() -> None:
    session = Mock(spec=Session)
    document_id = uuid4()
    document = Document(title="Заголовок", body="Содержание")
    session.get.return_value = document

    assert DocumentRepository(session).get(document_id) is document
    session.get.assert_called_once_with(Document, document_id)


def test_list_documents_applies_pagination() -> None:
    session = Mock(spec=Session)
    document = Document(title="Заголовок", body="Содержание")
    session.scalars.return_value = [document]

    assert DocumentRepository(session).list_documents(limit=10, offset=5) == [document]
    statement = session.scalars.call_args.args[0]
    compiled = statement.compile(compile_kwargs={"literal_binds": True})
    assert "LIMIT 10" in str(compiled)
    assert "OFFSET 5" in str(compiled)
