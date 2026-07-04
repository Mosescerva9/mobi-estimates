"""Deterministic Painting quantity formulas (reference set).

These prove the shared engine works for a real trade. They never assume wall
heights, door sizes, opening dimensions, coat counts, or waste factors — every
value must be a supplied, verified or reviewer-approved input.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.estimating.formulas import rectangle_area, sum_segments
from app.estimating.quantities import (
    QuantityFormula,
    QuantityInputError,
    to_decimal,
)
from app.estimating.units import Unit

_PAINTING = frozenset({"painting"})


class WallGrossAreaFormula(QuantityFormula):
    formula_id = "painting.wall_gross_area"
    version = "1.0"
    output_unit = Unit.SQUARE_FOOT
    supported_trade_codes = _PAINTING
    required_inputs = ("length_ft", "height_ft")

    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        return rectangle_area(values["length_ft"], values["height_ft"])


class CeilingAreaFormula(QuantityFormula):
    formula_id = "painting.ceiling_area"
    version = "1.0"
    output_unit = Unit.SQUARE_FOOT
    supported_trade_codes = _PAINTING
    required_inputs = ("length_ft", "width_ft")

    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        return rectangle_area(values["length_ft"], values["width_ft"])


class OpeningDeductionFormula(QuantityFormula):
    """Sum of opening areas (width × height × count) to deduct from a wall."""

    formula_id = "painting.opening_deduction"
    version = "1.0"
    output_unit = Unit.SQUARE_FOOT
    supported_trade_codes = _PAINTING
    required_inputs = ("openings",)

    def validate_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if set(inputs) - {"openings"}:
            raise QuantityInputError("Only 'openings' is permitted")
        openings = inputs.get("openings")
        if not isinstance(openings, list) or not openings:
            raise QuantityInputError("'openings' must be a non-empty list")
        normalized = []
        for index, opening in enumerate(openings):
            if not isinstance(opening, dict):
                raise QuantityInputError(f"opening[{index}] must be an object")
            width = to_decimal(f"opening[{index}].width_ft", opening.get("width_ft"))
            height = to_decimal(f"opening[{index}].height_ft", opening.get("height_ft"))
            count = to_decimal(
                f"opening[{index}].count", opening.get("count", 1), allow_zero=False
            )
            normalized.append({"width_ft": width, "height_ft": height, "count": count})
        return {"openings": normalized}

    def _compute(self, values: dict[str, Any]) -> Decimal:
        total = Decimal("0")
        for opening in values["openings"]:
            total += opening["width_ft"] * opening["height_ft"] * opening["count"]
        return total


class NetWallAreaFormula(QuantityFormula):
    formula_id = "painting.net_wall_area"
    version = "1.0"
    output_unit = Unit.SQUARE_FOOT
    supported_trade_codes = _PAINTING
    required_inputs = ("gross_area_sf", "deduction_sf")

    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        # Negative net area is rejected by the base class (deductions > gross).
        return values["gross_area_sf"] - values["deduction_sf"]


class DoorLeafFaceAreaFormula(QuantityFormula):
    """Door leaf face area; 'sides' must be supplied (commonly 2), never assumed."""

    formula_id = "painting.door_leaf_face_area"
    version = "1.0"
    output_unit = Unit.SQUARE_FOOT
    supported_trade_codes = _PAINTING
    required_inputs = ("width_ft", "height_ft", "sides")

    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        return values["width_ft"] * values["height_ft"] * values["sides"]


class FrameScheduleCountFormula(QuantityFormula):
    formula_id = "painting.frame_schedule_count"
    version = "1.0"
    output_unit = Unit.EACH
    supported_trade_codes = _PAINTING
    required_inputs = ("count",)

    def _compute(self, values: dict[str, Decimal]) -> Decimal:
        return values["count"]


class BaseLengthFormula(QuantityFormula):
    """Total base/trim length from validated perimeter segment lengths."""

    formula_id = "painting.base_length"
    version = "1.0"
    output_unit = Unit.LINEAR_FOOT
    supported_trade_codes = _PAINTING
    required_inputs = ("segments_ft",)

    def validate_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if set(inputs) - {"segments_ft"}:
            raise QuantityInputError("Only 'segments_ft' is permitted")
        segments = inputs.get("segments_ft")
        if not isinstance(segments, list) or not segments:
            raise QuantityInputError("'segments_ft' must be a non-empty list")
        return {
            "segments_ft": [
                to_decimal(f"segments_ft[{i}]", value)
                for i, value in enumerate(segments)
            ]
        }

    def _compute(self, values: dict[str, Any]) -> Decimal:
        return sum_segments(values["segments_ft"])


def painting_formulas() -> list[QuantityFormula]:
    return [
        WallGrossAreaFormula(),
        CeilingAreaFormula(),
        OpeningDeductionFormula(),
        NetWallAreaFormula(),
        DoorLeafFaceAreaFormula(),
        FrameScheduleCountFormula(),
        BaseLengthFormula(),
    ]
