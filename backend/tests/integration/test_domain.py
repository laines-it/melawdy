from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.content_repository import ContentSearchRepository
from backend.db import SessionLocal, engine
from backend.models import (
    ApplicationType, AssessmentOption, AssessmentQuestion, AssessmentResult, AssessmentResultRule,
    AssessmentSurvey, Base, ContentCategory, ContentItem, ContentItemChunk, ContentItemTag,
    ContentStatus, ContentTag, ContentType, DocumentStatus, DocumentStatusHistory,
    DocumentTemplate, DocumentType, FeeCalculation, FeeCalculationClass, FeeRate,
    GlossaryTerm, GlossaryTermContent, MktuClass, QAPair, QuestionType, RequestHistory,
    User, UserAssessment, UserDocument, UserType,
)
from ml.constants import EMBEDDING_DIMENSIONS


def test_all_domain_tables_exist() -> None:
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())


def test_domain_objects_round_trip_with_json_money_and_relationships() -> None:
    token = uuid4().hex
    with SessionLocal() as session:
        user = User(email=f"{token}@example.test", full_name="Автор", password_hash="test-hash",
                    user_type=UserType.INDIVIDUAL)
        category = ContentCategory(name="Материалы", slug=token)
        content = ContentItem(title="Пример", slug=token, type=ContentType.ARTICLE,
                              category=category, creator=user)
        content.chunks.append(ContentItemChunk(chunk_index=0, body="Текст материала"))
        content.tag_links.append(ContentItemTag(tag=ContentTag(name=token, slug=token)))
        content.glossary_links.append(GlossaryTermContent(
            term=GlossaryTerm(term=token, definition="Краткое определение")))
        content.qa_pairs.append(QAPair(question="Вопрос", answer="Ответ", category=category))
        template = DocumentTemplate(document_type=DocumentType.CONTRACT, title="Шаблон",
                                    slug=token, body="Текст шаблона")
        result = AssessmentResult(code=token, title="Результат", description="Описание",
                                  recommended_content=content, recommended_document_template=template)
        survey = AssessmentSurvey(title="Опрос")
        question = AssessmentQuestion(text="Вопрос", question_type=QuestionType.SINGLE_CHOICE)
        question.options.append(AssessmentOption(text="Вариант", value="yes"))
        survey.questions.append(question)
        survey.rules.append(AssessmentResultRule(result=result, condition_json={"answer": "yes"}))
        session.add(UserAssessment(user=user, survey=survey, result=result, answers_json={"1": "yes"}))
        application_type = ApplicationType(code=token, name="Тип заявки")
        mktu_class = MktuClass(class_number=45, title="Класс")
        session.add(FeeRate(application_type=application_type, mktu_class=mktu_class,
                            amount=Decimal("100.25"), valid_from=date(2026, 1, 1), legal_basis="Тест"))
        calculation = FeeCalculation(user=user, application_type=application_type,
                                     total_amount=Decimal("100.25"), input_json={"count": 1},
                                     breakdown_json={"base": "100.25"})
        calculation.class_links.append(FeeCalculationClass(mktu_class=mktu_class))
        document = UserDocument(user=user, template=template, document_type=DocumentType.CONTRACT,
                                title="Мой документ", content_json={"fields": {"name": "Автор"}})
        document.status_history.append(DocumentStatusHistory(new_status=DocumentStatus.DRAFT, actor=user))
        session.add_all([calculation, document, RequestHistory(user=user, request_type="test",
                                                              request_params={"query": "пример"})])
        session.flush()
        ids = user.id, content.id, calculation.id, document.id
        session.expunge_all()
        loaded_user = session.get(User, ids[0])
        loaded_content = session.get(ContentItem, ids[1])
        assert loaded_user.assessments[0].answers_json == {"1": "yes"}
        assert loaded_content.chunks[0].body == "Текст материала"
        assert loaded_content.tag_links[0].tag.slug == token
        assert session.get(FeeCalculation, ids[2]).total_amount == Decimal("100.25")
        assert session.get(UserDocument, ids[3]).status_history[0].actor.id == ids[0]
        session.rollback()


def test_vectors_fts_and_edit_invalidation() -> None:
    vector = [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    token = uuid4().hex
    with SessionLocal() as session:
        content = ContentItem(title="Пример", slug=token, type=ContentType.ARTICLE,
                              status=ContentStatus.PUBLISHED, published_at=datetime.now(timezone.utc))
        chunk = ContentItemChunk(chunk_index=0, body="Авторское право", embedding=vector)
        content.chunks.append(chunk)
        draft = ContentItem(title="Черновик", slug=token + "-draft", type=ContentType.ARTICLE)
        draft.chunks.append(ContentItemChunk(chunk_index=0, body="Скрытый текст", embedding=vector))
        session.add_all([content, draft])
        session.flush()
        hits = ContentSearchRepository(session).nearest(vector)
        assert any(hit.chunk.id == chunk.id and hit.score == pytest.approx(1.0) for hit in hits)
        assert all(hit.chunk.content_item_id != draft.id for hit in hits)
        assert len(chunk.embedding) == EMBEDDING_DIMENSIONS
        assert session.scalar(text(
            "SELECT tsv @@ plainto_tsquery('russian', 'авторское') "
            "FROM content_item_chunks WHERE id = :id"
        ), {"id": chunk.id})

        before = chunk.updated_at
        session.execute(text("UPDATE content_item_chunks SET body = :body WHERE id = :id"),
                        {"id": chunk.id, "body": "Новый текст"})
        session.refresh(chunk)
        assert chunk.embedding is None
        assert chunk.updated_at > before
        session.rollback()


def test_duplicate_chunk_number_is_rejected() -> None:
    with SessionLocal() as session:
        content = ContentItem(title="Пример", slug=uuid4().hex, type=ContentType.ARTICLE)
        content.chunks = [ContentItemChunk(chunk_index=0, body="Один"),
                          ContentItemChunk(chunk_index=0, body="Два")]
        session.add(content)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
