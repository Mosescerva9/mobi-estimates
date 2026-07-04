"""Shared, deterministic quantity engine (trade-agnostic).

Canonical quantities are computed only here, only in Python, and only with
``Decimal`` — never binary floating point and never by an AI provider. Trade
modules register concrete formulas; the engine validates inputs and units and
produces reproducible, side-effect-free results.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable

from app.estimating.units import Unit


QUANTITY_PRECISION = Decimal("0.0001")


class QuantityBasis(str, Enum):
    """How a scope item's quantity was obtained."""

    EXPLICIT_PLAN_QUANTITY = "explicit_plan_quantity"
    SCHEDULE_COUNT = "schedule_count"
    SCHEDULE_LENGTH = "schedule_length"
    SCHEDULE_AREA = "schedule_area"
    SCHEDULE_VOLUME = "schedule_volume"
    DRAWING_COUNT = "drawing_count"
    DIMENSION_INPUTS = "dimension_inputs"
    DETERMINISTIC_DERIVATION = "deterministic_derivation"
    MANUAL_REVIEWER_ENTRY = "manual_reviewer_entry"
    SUPPLIER_QUOTE_QUANTITY = "supplier_quote_quantity"
    SUBCONTRACTOR_QUOTE_QUANTITY = "subcontractor_quote_quantity"
    UNKNOWN = "unknown"


# Bases for which a provider/transcription may supply the number directly.
TRANSCRIBED_BASES: frozenset[QuantityBasis] = frozenset(
    {
        QuantityBasis.EXPLICIT_PLAN_QUANTITY,
        QuantityBasis.SCHEDULE_COUNT,
        QuantityBasis.SCHEDULE_LENGTH,
        QuantityBasis.SCHEDULE_AREA,
        QuantityBasis.SCHEDULE_VOLUME,
        QuantityBasis.DRAWING_COUNT,
        QuantityBasis.SUPPLIER_QUOTE_QUANTITY,
        QuantityBasis.SUBCONTRACTOR_QUOTE_QUANTITY,
    }
)

# Bases that REQUIRE a deterministic Python calculation (never a provider total).
DERIVED_BASES: frozenset[QuantityBasis] = frozenset(
    {QuantityBasis.DIMENSION_INPUTS, QuantityBasis.DETERMINISTIC_DERIVATION}
)


class QuantityInputError(ValueError):
    """Raised for missing, malformed, or out-of-range formula inputs."""


class FormulaError(ValueError):
    """Raised for formula-registry or formula-selection problems."""


@dataclass(frozen=True)
class QuantityResult:
    value: Decimal
    unit: Unit
    formula_id: str
    formula_version: str
    inputs: dict[str, Any]


def to_decimal(name: str, value: Any, *, allow_negative: bool = False,
               allow_zero: bool = True) -> Decimal:
    """Convert an input to ``Decimal`` deterministically and validate its sign.

    Floats are converted via ``str`` so that, e.g., ``0.1`` is parsed as the
    decimal literal a human typed rather than its binary approximation.
    """
    if value is None:
        raise QuantityInputError(f"Missing required input '{name}'")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise QuantityInputError(f"Input '{name}' is not a number: {value!r}") from exc
    if not dec.is_finite():
        raise QuantityInputError(f"Input '{name}' must be finite")
    if not allow_negative and dec < 0:
        raise QuantityInputError(f"Input '{name}' must not be negative")
    if not allow_zero and dec == 0:
        raise QuantityInputError(f"Input '{name}' must not be zero")
    return dec


def quantize(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_PRECISION, rounding=ROUND_HALF_UP)


class QuantityFormula(ABC):
    """Base class for a single deterministic quantity formula."""

    formula_id: str
    version: str
    output_unit: Unit
    supported_trade_codes: frozenset[str]
    required_inputs: tuple[str, ...] = ()
    allow_negative_output: bool = False

    def validate_inputs(self, inputs: dict[str, Any]) -> dict[str, Decimal]:
        """Default validation for simple scalar inputs. Override for complex ones."""
        if not isinstance(inputs, dict):
            raise QuantityInputError("Inputs must be an object")
        unexpected = set(inputs) - set(self.required_inputs)
        if unexpected:
            raise QuantityInputError(
                f"Unexpected input(s): {sorted(unexpected)}"
            )
        return {name: to_decimal(name, inputs.get(name)) for name in self.required_inputs}

    @abstractmethod
    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        ...

    def calculate(self, inputs: dict[str, Any]) -> QuantityResult:
        values = self.validate_inputs(inputs)
        raw = self._compute(values)
        if not isinstance(raw, Decimal):  # defensive: enforce Decimal everywhere
            raise FormulaError(f"Formula '{self.formula_id}' returned non-Decimal")
        if raw < 0 and not self.allow_negative_output:
            raise QuantityInputError("Computed quantity must not be negative")
        return QuantityResult(
            value=quantize(raw),
            unit=self.output_unit,
            formula_id=self.formula_id,
            formula_version=self.version,
            inputs={k: str(v) for k, v in values.items()},
        )


class FormulaRegistry:
    """Holds the formulas contributed by enabled trade modules."""

    def __init__(self) -> None:
        self._formulas: dict[str, QuantityFormula] = {}

    def register(self, formula: QuantityFormula) -> None:
        if formula.formula_id in self._formulas:
            raise FormulaError(f"Duplicate formula id '{formula.formula_id}'")
        self._formulas[formula.formula_id] = formula

    def clear(self) -> None:
        self._formulas.clear()

    def get(self, formula_id: str) -> QuantityFormula:
        if formula_id not in self._formulas:
            raise FormulaError(f"Unknown formula '{formula_id}'")
        return self._formulas[formula_id]

    def get_for_trade(self, formula_id: str, trade_code: str) -> QuantityFormula:
        formula = self.get(formula_id)
        if trade_code not in formula.supported_trade_codes:
            raise FormulaError(
                f"Formula '{formula_id}' is not registered for trade '{trade_code}'"
            )
        return formula

    def list_for_trade(self, trade_code: str) -> list[QuantityFormula]:
        return [
            f for f in self._formulas.values()
            if trade_code in f.supported_trade_codes
        ]

    def all(self) -> Iterable[QuantityFormula]:
        return tuple(self._formulas.values())


# Process-wide registry, populated from enabled trade modules at bootstrap.
formula_registry = FormulaRegistry()
