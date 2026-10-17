from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)

    @field_validator("title", "body")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text must not be blank")
        return value


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str
    created_at: datetime


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)

    @field_validator("question")
    @classmethod
    def require_non_blank_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank")
        return value


class AnalyzeResponse(BaseModel):
    status: str
    model_ready: bool
    message: str


class SearchResponse(BaseModel):
    article_ids: list[str]
    title: str | None
    summary: str | None
