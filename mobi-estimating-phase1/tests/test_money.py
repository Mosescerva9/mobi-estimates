"""Money / Decimal / markup-vs-margin tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.pricing.money import (
    MoneyError,
    apply_margin,
    apply_markup,
    money,
    quantize_money,
    to_decimal,
    validate_currency,
)


def test_decimal_parsing_from_string():
    assert to_decimal("0.1") == Decimal("0.1")


def test_float_parsed_via_str_is_exact():
    # 0.1 + 0.2 must be exact when each parsed as a decimal literal.
    assert to_decimal("0.1") + to_decimal("0.2") == Decimal("0.3")


def test_reject_nan():
    with pytest.raises(MoneyError):
        to_decimal("NaN")


def test_reject_infinity():
    with pytest.raises(MoneyError):
        to_decimal("Infinity")


def test_reject_negative_by_default():
    with pytest.raises(MoneyError):
        money("-5")


def test_allow_negative_credit():
    assert to_decimal("-5", allow_negative=True) == Decimal("-5")


def test_reject_boolean():
    with pytest.raises(MoneyError):
        to_decimal(True)


def test_currency_quantization():
    assert quantize_money(Decimal("1.005")) == Decimal("1.01")  # half-up
    assert quantize_money(Decimal("1.004")) == Decimal("1.00")


def test_markup_vs_margin_differ():
    cost = Decimal("100")
    assert apply_markup(cost, Decimal("0.20")) == Decimal("120")
    # 20% margin sells higher than 20% markup.
    assert apply_margin(cost, Decimal("0.20")) == Decimal("125")
    assert apply_markup(cost, Decimal("0.20")) != apply_margin(cost, Decimal("0.20"))


def test_margin_at_or_above_100_percent_rejected():
    with pytest.raises(MoneyError):
        apply_margin(Decimal("100"), Decimal("1.0"))
    with pytest.raises(MoneyError):
        apply_margin(Decimal("100"), Decimal("1.5"))


def test_unsupported_currency_rejected():
    assert validate_currency("USD") == "USD"
    with pytest.raises(MoneyError):
        validate_currency("EUR")


def test_repeating_decimal_quantizes_consistently():
    third = Decimal("100") / Decimal("3")
    assert quantize_money(third) == Decimal("33.33")


def test_large_total():
    total = sum((Decimal("1234567.89") for _ in range(1000)), Decimal("0"))
    assert quantize_money(total) == Decimal("1234567890.00")
