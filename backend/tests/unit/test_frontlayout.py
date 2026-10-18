from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from backend import account, auth, fees, public
from backend.main import app
from backend.models import FeeCalculation, FeeRate, User, UserType
from ml.tfidf import SearchChunk


def rate(**values):
    defaults = dict(id=3, application_type_id=1, mktu_class_id=7, is_urgent=False,
                    amount=Decimal("123.45"), currency="RUB", valid_from=date(2026, 1, 1),
                    valid_to=None, legal_basis="Основание из справочника")
    return FeeRate(**(defaults | values))


def test_calculation_uses_exact_server_rate_and_decimal_money():
    session = Mock()
    session.scalars.return_value.all.return_value = [rate()]
    result = fees.calculate(fees.CalculationInput(application_type_id=1, mktu_class_id=7,
                                                quantity=3), session)
    assert result["total_amount"] == "370.35"
    assert result["unit_amount"] == "123.45"
    assert result["legal_basis"] == "Основание из справочника"
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "fee_rates.application_type_id = 1" in sql
    assert "fee_rates.mktu_class_id = 7" in sql
    assert "fee_rates.is_urgent = false" in sql
    assert "fee_rates.valid_from <=" in sql
    assert "fee_rates.valid_to IS NULL OR fee_rates.valid_to >=" in sql


def test_classless_urgent_calculation_has_no_implicit_class_fallback():
    session = Mock()
    session.scalars.return_value.all.return_value = [rate(mktu_class_id=None, is_urgent=True)]
    fees.calculate(fees.CalculationInput(application_type_id=1, is_urgent=True), session)
    sql = str(session.scalars.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "fee_rates.mktu_class_id IS NULL" in sql
    assert "fee_rates.is_urgent = true" in sql


@pytest.mark.parametrize("rates,expected", [([], 404), ([rate(), rate(id=4)], 409)])
def test_missing_and_overlapping_rates_do_not_produce_a_quote(rates, expected):
    session = Mock()
    session.scalars.return_value.all.return_value = rates
    with pytest.raises(HTTPException) as error:
        fees.calculate(fees.CalculationInput(application_type_id=1), session)
    assert error.value.status_code == expected


def test_validity_dates_are_inclusive_and_based_on_utc(monkeypatch):
    now = datetime(2026, 10, 15, 23, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(fees, "datetime", SimpleNamespace(now=lambda tz: now))
    session = Mock()
    session.scalars.return_value.all.return_value = [rate()]
    fees.calculate(fees.CalculationInput(application_type_id=1), session)
    parameters = session.scalars.call_args.args[0].compile().params
    assert parameters["valid_from_1"] == date(2026, 10, 15)
    assert parameters["valid_to_1"] == date(2026, 10, 15)


@pytest.mark.parametrize("values", [{"quantity": 0}, {"quantity": 101}, {"quantity": 1.5},
                                     {"application_type_id": 0}, {"mktu_class_id": -1},
                                     {"total_amount": "0.01"}, {"user_id": 99}])
def test_calculation_rejects_invalid_and_client_owned_fields(values):
    with pytest.raises(ValidationError):
        fees.CalculationInput(**({"application_type_id": 1} | values))


def test_calculation_rejects_total_that_cannot_be_saved():
    session = Mock()
    session.scalars.return_value.all.return_value = [rate(amount=Decimal("999999999999.99"))]
    with pytest.raises(HTTPException) as error:
        fees.calculate(fees.CalculationInput(application_type_id=1, quantity=2), session)
    assert error.value.status_code == 422


@pytest.mark.parametrize("class_id", [None, 7])
def test_saved_calculation_is_recomputed_and_owned_by_authenticated_user(class_id):
    session = Mock()
    session.scalars.return_value.all.return_value = [rate(mktu_class_id=class_id)]
    session.refresh.side_effect = lambda record: setattr(record, "id", 25)
    user = User(id=8, user_type=UserType.INDIVIDUAL)
    payload = fees.CalculationInput(application_type_id=1, mktu_class_id=class_id, quantity=2)
    result = fees.save_calculation(payload, session, user)
    stored = session.add.call_args.args[0]
    assert isinstance(stored, FeeCalculation)
    assert stored.user_id == 8
    assert stored.total_amount == Decimal("246.90")
    assert stored.input_json == payload.model_dump()
    assert stored.breakdown_json["rate_id"] == "3"
    assert [link.mktu_class_id for link in stored.class_links] == ([] if class_id is None else [7])
    assert result["id"] == "25"
    session.commit.assert_called_once()


def test_catalog_exposes_only_effective_rate_combinations():
    session = Mock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [SimpleNamespace(id=1, name="Процедура", description=None)]),
        SimpleNamespace(all=lambda: [SimpleNamespace(id=7, class_number=9, title="Класс", description="Описание")]),
        SimpleNamespace(all=lambda: [rate()]),
    ]
    result = fees.catalog(session)
    assert result["rates"] == [{"application_type_id": "1", "mktu_class_id": "7", "is_urgent": False}]
    assert result["mktu_classes"][0]["class_number"] == 9
    sql = str(session.scalars.call_args.args[0])
    assert "fee_rates.valid_from <=" in sql and "fee_rates.valid_to >=" in sql


def test_account_overview_filters_private_records_by_owner():
    session = Mock()
    session.scalars.side_effect = [
        [SimpleNamespace(id=12, title="Мой документ", status="draft", due_date=None)],
        [SimpleNamespace(id=13, total_amount=Decimal("123.45"), currency="RUB", created_at=None)],
    ]
    session.scalar.side_effect = [1, 20, 3]
    response = Response()
    result = account.overview(response, session, User(id=8))
    assert result["stats"] == {"documents": 1, "articles": 20, "surveys": 3}
    assert result["documents"][0]["title"] == "Мой документ"
    assert result["calculations"][0]["total_amount"] == "123.45"
    assert response.headers["cache-control"] == "no-store"
    for call, table in zip(session.scalars.call_args_list, ["user_documents", "fee_calculations"]):
        sql = str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert f"{table}.user_id = 8" in sql
        assert "LIMIT 25" in sql
    assert "user_documents.user_id" in str(session.scalar.call_args_list[0].args[0])
    assert "content_items.status" in str(session.scalar.call_args_list[1].args[0])
    assert "assessment_surveys.is_active" in str(session.scalar.call_args_list[2].args[0])


def test_account_and_saving_require_existing_user_session_and_csrf():
    routes = {route.path: route for router in [account.router, fees.router] for route in router.routes}
    for path in ["/api/v1/account/overview", "/api/v1/public/fees/calculations"]:
        assert path in app.openapi()["paths"]
        assert any(dependency.call is auth.require_user for dependency in routes[path].dependant.dependencies)


def test_search_reuses_published_corpus_and_does_not_return_hidden_articles(monkeypatch):
    repository = Mock()
    repository.list_chunks.return_value = [SearchChunk(1, 4, "музыка права"), SearchChunk(2, 5, "музыка")]
    monkeypatch.setattr(public, "ContentSearchRepository", lambda session: repository)
    session = Mock()
    session.execute.return_value.all.return_value = [SimpleNamespace(id=4, title="Права на музыку", summary="Описание")]
    result = public.search(session, query="музыка", limit=10, method="tfidf")
    assert result == [{"article_id": "4", "title": "Права на музыку", "body": "Описание", "summary": "Описание"}]
    sql = str(session.execute.call_args.args[0])
    assert "content_items.status" in sql and "content_items.published_at <= now()" in sql


def test_blank_search_is_rejected_before_accessing_database():
    session = Mock()
    with pytest.raises(HTTPException) as error:
        public.search(session, query="   ", limit=10)
    assert error.value.status_code == 422
    session.execute.assert_not_called()


def test_faq_filters_unpublished_linked_articles():
    session = Mock()
    session.scalars.return_value = [SimpleNamespace(id=2, question="Вопрос", answer="Ответ", content_item_id=None)]
    assert public.list_faq(session, limit=4)[0]["answer"] == "Ответ"
    sql = str(session.scalars.call_args.args[0])
    assert "qa_pairs.content_item_id IS NULL" in sql
    assert "content_items.status" in sql and "content_items.published_at <= now()" in sql


def test_templates_filter_inactive_records_and_missing_template_returns_404():
    session = Mock()
    session.scalars.return_value = []
    assert public.list_templates(session, limit=25, offset=0) == []
    assert "document_templates.is_active IS true" in str(session.scalars.call_args.args[0])
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        public.read_template(3, session)
    assert error.value.status_code == 404
    assert "document_templates.is_active IS true" in str(session.scalar.call_args.args[0])


def test_audio_capability_does_not_claim_to_produce_results():
    assert public.capabilities()["music_check"]["available"] is False
