from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import fees, public
from backend.models import FeeCalculation, FeeRate, User, UserType


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


@pytest.mark.parametrize("rates,expected", [([], 404), ([rate(), rate(id=4)], 409)])
def test_missing_and_overlapping_rates_do_not_produce_a_quote(rates, expected):
    session = Mock()
    session.scalars.return_value.all.return_value = rates
    with pytest.raises(HTTPException) as error:
        fees.calculate(fees.CalculationInput(application_type_id=1), session)
    assert error.value.status_code == expected


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


def test_blank_search_is_rejected_before_accessing_database():
    session = Mock()
    with pytest.raises(HTTPException) as error:
        public.search(session, query="   ", limit=10)
    assert error.value.status_code == 422
    session.execute.assert_not_called()


def test_missing_template_returns_404():
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        public.read_template(3, session)
    assert error.value.status_code == 404
