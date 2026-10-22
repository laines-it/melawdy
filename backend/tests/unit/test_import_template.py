import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from backend.import_template import import_template
from backend.models import DocumentTemplate

SOURCE = json.loads((Path(__file__).resolve().parents[3] / "docs/examples/coauthors-template.json")
                    .read_text(encoding="utf-8"))


@pytest.mark.parametrize("inserted_id,created", [(1, True), (None, False)])
def test_import_preserves_constructor_data_and_does_not_overwrite_existing_slug(inserted_id, created):
    template = DocumentTemplate(id=1, **SOURCE)
    session = Mock()
    session.scalar.side_effect = [inserted_id, template]

    result = import_template(session, SOURCE)

    assert result == {
        "created": created,
        "id": "1",
        "title": SOURCE["title"],
        "slug": "coauthors-agreement",
        "active": True,
        "sections": 12,
        "blocks": 44,
    }

    statement = session.scalar.call_args_list[0].args[0]
    sql = str(statement.compile()).upper()

    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql
    assert statement.compile().params["schema_json"] == SOURCE["schema_json"]
    assert statement.compile().params["structure_json"] == SOURCE["structure_json"]
    session.commit.assert_not_called()  # The caller owns the transaction.


def test_existing_template_is_reported_with_its_actual_values():
    existing = DocumentTemplate(id=3, **(SOURCE | {"title": "Отредактированное соглашение", "is_active": False}))
    session = Mock()
    session.scalar.side_effect = [None, existing]

    result = import_template(session, SOURCE)

    assert result["id"] == "3"
    assert result["created"] is False
    assert result["title"] == "Отредактированное соглашение"
    assert result["active"] is False
    session.add.assert_not_called()


def test_invalid_source_never_writes_to_database():
    session = Mock()
    with pytest.raises(ValidationError):
        import_template(session, SOURCE | {"title": ""})
    session.scalar.assert_not_called()
