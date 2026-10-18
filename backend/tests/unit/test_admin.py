from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from backend import admin, auth, public
from backend.admin_resources import RESOURCES, metadata
from backend.admin_schemas import ArticleInput, FeeRateInput
from backend.models import ContentItem, ContentItemChunk


def administrator():
    return SimpleNamespace(id=7)


def test_every_admin_route_is_protected_and_resources_are_allowlisted():
    for route in admin.router.routes:
        assert any(dependency.call is auth.require_admin for dependency in route.dependant.dependencies)
    with pytest.raises(HTTPException) as error:
        admin.get_resource("users")
    assert error.value.status_code == 404
    for resource in RESOURCES.values():
        fields = metadata(resource)["fields"]
        assert {field["name"] for field in fields} == {
            field.alias or name for name, field in resource.schema.model_fields.items()
        }
        assert not ({"password_hash", "embedding", "tsv", "created_by"} & set(resource.schema.model_fields))
    assert next(field for field in metadata(RESOURCES["fee-rates"])["fields"]
                if field["name"] == "amount")["kind"] == "decimal"


@pytest.mark.parametrize("key", ["0", "-1", "abc", "1:2", ""])
def test_invalid_scalar_identity_is_rejected(key):
    with pytest.raises(HTTPException) as error:
        admin.identity(RESOURCES["articles"], key)
    assert error.value.status_code == 422


def test_composite_identity_and_serialization_preserve_foreign_keys():
    assert admin.identity(RESOURCES["article-tags"], "3:4") == (3, 4)
    from backend.models import ContentItemTag
    assert admin.serialize(RESOURCES["article-tags"], ContentItemTag(content_item_id=3, tag_id=4)) == {
        "id": "3:4", "content_item_id": 3, "tag_id": 4,
    }


@pytest.mark.parametrize("extra", [{"created_by": 1}, {"password_hash": "hash"}, {"id": 12}])
def test_article_rejects_server_owned_fields(extra):
    with pytest.raises(ValidationError):
        ArticleInput(title="Article", slug="article", chunks=["Text"], **extra)


@pytest.mark.parametrize("chunks", [[], ["   "]])
def test_article_requires_nonblank_text(chunks):
    with pytest.raises(ValidationError):
        ArticleInput(title="Article", slug="article", chunks=chunks)


def test_article_chunk_updates_preserve_identity_and_order():
    item = ContentItem(title="Article", slug="article", type="article")
    first = ContentItemChunk(id=1, chunk_index=0, body="First")
    second = ContentItemChunk(id=2, chunk_index=1, body="Second")
    item.chunks.extend([first, second])
    admin.apply_article_chunks(item, ["Changed"])
    assert item.chunks == [first] and first.body == "Changed"
    admin.apply_article_chunks(item, ["Changed", "New"])
    assert item.chunks[0] is first
    assert item.chunks[1].chunk_index == 1 and item.chunks[1].body == "New"
    assert "embedding" not in admin.serialize(RESOURCES["chunks"], first)
    assert "tsv" not in admin.serialize(RESOURCES["chunks"], first)


def test_publication_sets_date_and_author_on_server():
    session = Mock()
    user = administrator()
    result = admin.save_record(RESOURCES["articles"], {
        "title": "Article", "slug": "article", "status": "published", "chunks": ["Text"],
    }, session, user)
    record = session.add.call_args.args[0]
    assert record.created_by == user.id
    assert record.published_at.tzinfo is not None
    assert result["chunks"] == ["Text"]
    session.commit.assert_called_once()


def test_invalid_foreign_key_or_duplicate_rolls_back():
    session = Mock()
    session.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    with pytest.raises(HTTPException) as error:
        admin.save_record(RESOURCES["tags"], {"name": "Tag", "slug": "tag"}, session, administrator())
    assert error.value.status_code == 409
    session.rollback.assert_called_once()


def test_delete_uses_database_foreign_key_rules_and_reports_conflicts():
    from backend.models import ContentCategory
    session = Mock()
    session.get.return_value = ContentCategory(id=1, name="Category", slug="category")
    session.execute.side_effect = IntegrityError("delete", {}, Exception("referenced"))
    with pytest.raises(HTTPException) as error:
        admin.delete_record("categories", "1", session)
    assert error.value.status_code == 409
    session.rollback.assert_called_once()
    session.delete.assert_not_called()


def test_category_parent_cycles_are_rejected():
    session = Mock()
    session.get.side_effect = [SimpleNamespace(parent_id=3), SimpleNamespace(parent_id=1)]
    with pytest.raises(HTTPException) as error:
        admin.validate_parent(session, parent_id=2, record_id=1)
    assert error.value.status_code == 422


def test_fee_rates_keep_decimal_precision_and_check_dates():
    values = dict(application_type_id=1, amount="123456789012.34", valid_from="2026-01-01", legal_basis="Example")
    assert FeeRateInput(**values).amount == Decimal("123456789012.34")
    with pytest.raises(ValidationError):
        FeeRateInput(**{**values, "amount": "1.001"})
    with pytest.raises(ValidationError):
        FeeRateInput(**values, valid_to="2025-12-31")


def test_public_query_excludes_drafts_and_scheduled_articles():
    session = Mock()
    session.scalars.return_value = []
    assert public.list_articles(session, limit=25, offset=0) == []
    statement = session.scalars.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "content_items.status = 'published'" in sql
    assert "content_items.published_at <= now()" in sql
