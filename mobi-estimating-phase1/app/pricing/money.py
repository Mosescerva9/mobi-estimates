"""Canonical money + percentage arithmetic for the pricing engine.

All financial math uses ``Decimal`` — never binary floating point. NaN and
infinity are rejected. Rounding policy is **explicit and line-level authoritative**:

* Internal/intermediate values keep high precision (``CALC_PRECISION``, 6 dp).
* Currency is quantized to ``MONEY_PRECISION`` (2 dp) only at documented boundaries
  — each estimate *line item* total is the rounding boundary, and project rollups
  sum the already-rounded line totals (line-level rounding is authoritative).

See ``docs/pricing-calculation-order.md`` for the full policy.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MONEY_PRECISION = Decimal("0.01")   # display/quantization boundary (USD cents)
CALC_PRECISION = Decimal("0.000001")  # internal precision (6 dp)
RATE_PRECISION = Decimal("0.000001")
PERCENT_PRECISION = Decimal("0.000001")

ROUNDING = ROUND_HALF_UP
SUPPORTED_CURRENCIES = frozenset({"USD"})


class MoneyError(ValueError):
    """Raised for invalid monetary/rate/percentage inputs."""


def to_decimal(value: Any, *, field: str = "value", allow_negative: bool = False,
               allow_zero: bool = True) -> Decimal:
    """Parse a value to a finite ``Decimal``. Floats are converted via ``str`` so a
    documented JSON string like ``"0.1"`` is exact, not its binary approximation."""
    if value is None:
        raise MoneyError(f"Missing required value for '{field}'")
    if isinstance(value, bool):  # bool is an int subclass; never valid money
        raise MoneyError(f"'{field}' must be numeric, not boolean")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MoneyError(f"'{field}' is not a valid decimal: {value!r}") from exc
    if not dec.is_finite():
        raise MoneyError(f"'{field}' must be finite (NaN/Infinity rejected)")
    if not allow_negative and dec < 0:
        raise MoneyError(f"'{field}' must not be negative")
    if not allow_zero and dec == 0:
        raise MoneyError(f"'{field}' must not be zero")
    return dec


def money(value: Any, *, field: str = "amount", allow_negative: bool = False) -> Decimal:
    """A monetary amount kept at full internal precision (not yet quantized)."""
    return to_decimal(value, field=field, allow_negative=allow_negative)


def rate(value: Any, *, field: str = "rate", allow_negative: bool = False) -> Decimal:
    return to_decimal(value, field=field, allow_negative=allow_negative)


def percent(value: Any, *, field: str = "percent", allow_negative: bool = True) -> Decimal:
    """A percentage expressed as a fraction (0.20 == 20%)."""
    return to_decimal(value, field=field, allow_negative=allow_negative)


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary amount to the currency boundary (2 dp, half-up)."""
    return value.quantize(MONEY_PRECISION, rounding=ROUNDING)


def quantize_calc(value: Decimal) -> Decimal:
    """Round an intermediate value to internal precision (6 dp)."""
    return value.quantize(CALC_PRECISION, rounding=ROUNDING)


def apply_markup(cost: Decimal, markup_rate: Decimal) -> Decimal:
    """Sell = cost × (1 + markup_rate)."""
    if markup_rate < 0:
        raise MoneyError("markup rate must not be negative")
    return cost * (Decimal("1") + markup_rate)


def apply_margin(cost: Decimal, margin_rate: Decimal) -> Decimal:
    """Sell = cost ÷ (1 − margin_rate). A 20% markup is NOT a 20% margin."""
    if margin_rate < 0:
        raise MoneyError("margin rate must not be negative")
    if margin_rate >= 1:
        raise MoneyError("margin rate must be < 1 (100%)")
    return cost / (Decimal("1") - margin_rate)


def validate_currency(currency: str) -> str:
    if currency not in SUPPORTED_CURRENCIES:
        raise MoneyError(f"Unsupported currency '{currency}'")
    return currency
