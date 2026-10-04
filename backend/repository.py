from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Document


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, title: str, body: str) -> Document:
        document = Document(title=title, body=body)
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def list_documents(self, limit: int, offset: int) -> list[Document]:
        statement = (
            select(Document)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def get(self, document_id: UUID) -> Document | None:
        return self.session.get(Document, document_id)
