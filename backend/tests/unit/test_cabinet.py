from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from backend import cabinet
from backend.models import DeadlineStatus, DocumentStatus, DocumentType, UserDocument

DAY = date(2026, 10, 13)
USER = SimpleNamespace(id=42)


def make_document(**changes):
    values = dict(id=5, user_id=42, title="Договор", document_type=DocumentType.CONTRACT,
                  status=DocumentStatus.DRAFT, content_json={}, due_date=None, template_id=None)
    return UserDocument(**{**values, **changes})


@pytest.mark.parametrize("status,due,expected", [
    (DocumentStatus.DRAFT, None, DeadlineStatus.NONE),
    (DocumentStatus.DRAFT, DAY - timedelta(days=1), DeadlineStatus.OVERDUE),
    (DocumentStatus.IN_PROGRESS, DAY, DeadlineStatus.UPCOMING),
    (DocumentStatus.IN_PROGRESS, DAY + timedelta(days=cabinet.UPCOMING_DAYS), DeadlineStatus.UPCOMING),
    (DocumentStatus.DRAFT, DAY + timedelta(days=cabinet.UPCOMING_DAYS + 1), DeadlineStatus.NONE),
    (DocumentStatus.COMPLETED, DAY - timedelta(days=30), DeadlineStatus.COMPLETED),
    (DocumentStatus.ARCHIVED, DAY - timedelta(days=30), DeadlineStatus.NONE),
])
def test_deadline_status_is_computed_from_status_and_date(status, due, expected):
    assert cabinet.deadline_status(status, due, DAY) == expected


def test_missing_document_gives_404():
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        cabinet.get_own_document(session, USER, 5)
    assert error.value.status_code == 404


# --- схемы -----------------------------------------------------------------------------------

def test_create_input_rejects_unknown_blank_and_oversized_data():
    with pytest.raises(ValidationError):
        cabinet.DocumentCreate(title="x", user_id=1)
    with pytest.raises(ValidationError):
        cabinet.DocumentCreate(title="   ")
    with pytest.raises(ValidationError):
        cabinet.DocumentCreate(title="x", content_json={"text": "я" * 70_000})


@pytest.mark.parametrize("data", [
    {}, {"title": None}, {"status": None}, {"content_json": None}, {"document_type": None},
    {"comment": "Без статуса"}, {"deadline_status": "overdue"},
])
def test_update_rejects_empty_null_orphan_comment_and_client_set_deadline(data):
    with pytest.raises(ValidationError):
        cabinet.DocumentUpdate(**data)


def test_update_can_clear_due_date():
    assert cabinet.DocumentUpdate(due_date=None).model_dump(exclude_unset=True) == {"due_date": None}


def test_document_limit_is_enforced():
    session = Mock()
    session.scalar.return_value = cabinet.MAX_DOCUMENTS_PER_USER
    with pytest.raises(HTTPException) as error:
        cabinet.create_document(cabinet.DocumentCreate(title="Договор"), USER, session)
    assert error.value.status_code == 409
    session.add.assert_not_called()


def test_unknown_template_gives_422():
    session = Mock()
    session.scalar.return_value = 0
    session.get.return_value = None
    with pytest.raises(HTTPException) as error:
        cabinet.create_document(cabinet.DocumentCreate(title="Договор", template_id=77), USER, session)
    assert error.value.status_code == 422
    session.add.assert_not_called()


def test_create_belongs_to_user_computes_deadline_and_writes_first_history_row():
    session = Mock()
    session.scalar.return_value = 0
    session.add.side_effect = lambda obj: setattr(obj, "id", 11)  # так база выдаёт id
    result = cabinet.create_document(
        cabinet.DocumentCreate(title=" Договор ", due_date=date(2020, 1, 1)), USER, session)
    doc = session.add.call_args.args[0]
    assert doc.user_id == 42 and doc.title == "Договор"
    assert doc.status == DocumentStatus.DRAFT
    assert [item.new_status for item in doc.status_history] == [DocumentStatus.DRAFT]
    assert doc.status_history[0].changed_by == 42
    assert result.deadline_status == "overdue"
    assert [item.new_status for item in result.status_history] == ["draft"]
    session.commit.assert_called_once()


def test_status_change_is_logged_and_unchanged_status_is_not():
    doc = make_document()
    session = Mock()
    session.scalar.return_value = doc

    cabinet.update_document(5, cabinet.DocumentUpdate(status="draft"), USER, session)
    assert doc.status_history == []

    cabinet.update_document(
        5, cabinet.DocumentUpdate(status="completed", comment="Подписан"), USER, session)
    assert doc.status == DocumentStatus.COMPLETED
    entry = doc.status_history[0]
    assert (entry.old_status, entry.new_status, entry.comment, entry.changed_by) == (
        DocumentStatus.DRAFT, DocumentStatus.COMPLETED, "Подписан", 42)


def test_update_recomputes_deadline_status():
    doc = make_document(due_date=date(2020, 1, 1))
    session = Mock()
    session.scalar.return_value = doc
    cabinet.update_document(5, cabinet.DocumentUpdate(title="Новый"), USER, session)
    assert doc.deadline_status == DeadlineStatus.OVERDUE


def article():
    return SimpleNamespace(id=5, title="Статья", slug="stat", summary=None, type="article",
                           published_at=None)


def test_unpublished_article_cannot_be_favorited():
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        cabinet.add_favorite(5, USER, session)
    assert error.value.status_code == 404
    session.add.assert_not_called()


def test_adding_a_favorite_twice_returns_the_existing_one():
    existing = SimpleNamespace(id=9, created_at=None, content_item=article())
    session = Mock()
    session.scalar.side_effect = [article(), existing]
    result = cabinet.add_favorite(5, USER, session)
    assert result.id == 9
    session.add.assert_not_called()


def test_favorite_limit_is_enforced():
    session = Mock()
    session.scalar.side_effect = [article(), None, cabinet.MAX_FAVORITES_PER_USER]
    with pytest.raises(HTTPException) as error:
        cabinet.add_favorite(5, USER, session)
    assert error.value.status_code == 409
    session.add.assert_not_called()


def test_parallel_favorite_insert_gives_409_and_rolls_back():
    session = Mock()
    session.scalar.side_effect = [article(), None, 0]
    session.commit.side_effect = IntegrityError("insert", {}, Exception())
    with pytest.raises(HTTPException) as error:
        cabinet.add_favorite(5, USER, session)
    assert error.value.status_code == 409
    session.rollback.assert_called_once()


def test_summary_collects_all_counters():
    session = Mock()
    session.execute.return_value = [(DocumentStatus.DRAFT, 2), (DocumentStatus.COMPLETED, 1)]
    session.scalar.side_effect = [1, 2, date(2026, 10, 20), 3, 4, 5, 6]
    result = cabinet.summary(USER, session)
    assert result["documents"]["total"] == 3
    assert result["documents"]["by_status"] == {
        "draft": 2, "in_progress": 0, "completed": 1, "archived": 0}
    assert (result["documents"]["overdue"], result["documents"]["upcoming"]) == (1, 2)
    assert result["documents"]["next_deadline"] == date(2026, 10, 20)
    assert (result["favorites"], result["calculations"], result["requests"],
            result["assessments"]) == (3, 4, 5, 6)