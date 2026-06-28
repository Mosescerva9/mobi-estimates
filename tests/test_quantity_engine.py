"""Deterministic quantity engine + formula tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.estimating.quantities import (
    FormulaError,
    FormulaRegistry,
    QuantityInputError,
)
from app.estimating.units import Unit, units_compatible
from app.trades.demo_concrete import SlabVolumeFormula
from app.trades.painting.quantities import (
    BaseLengthFormula,
    CeilingAreaFormula,
    DoorLeafFaceAreaFormula,
    FrameScheduleCountFormula,
    NetWallAreaFormula,
    OpeningDeductionFormula,
    WallGrossAreaFormula,
    painting_formulas,
)


def test_painting_wall_area():
    result = WallGrossAreaFormula().calculate({"length_ft": "20", "height_ft": "9"})
    assert result.value == Decimal("180.0000")
    assert result.unit == Unit.SQUARE_FOOT


def test_painting_ceiling_area():
    result = CeilingAreaFormula().calculate({"length_ft": "12", "width_ft": "10"})
    assert result.value == Decimal("120.0000")


def test_painting_opening_deduction():
    result = OpeningDeductionFormula().calculate(
        {"openings": [{"width_ft": "3", "height_ft": "7", "count": "2"}]}
    )
    assert result.value == Decimal("42.0000")


def test_painting_net_wall_area():
    result = NetWallAreaFormula().calculate(
        {"gross_area_sf": "180", "deduction_sf": "42"}
    )
    assert result.value == Decimal("138.0000")


def test_painting_net_wall_area_negative_rejected():
    with pytest.raises(QuantityInputError):
        NetWallAreaFormula().calculate({"gross_area_sf": "10", "deduction_sf": "40"})


def test_painting_door_face_area():
    result = DoorLeafFaceAreaFormula().calculate(
        {"width_ft": "3", "height_ft": "7", "sides": "2"}
    )
    assert result.value == Decimal("42.0000")


def test_painting_frame_count():
    assert FrameScheduleCountFormula().calculate({"count": "5"}).value == Decimal("5.0000")


def test_painting_base_length():
    result = BaseLengthFormula().calculate({"segments_ft": ["10", "12.5", "7.5"]})
    assert result.value == Decimal("30.0000")
    assert result.unit == Unit.LINEAR_FOOT


def test_second_trade_slab_volume_uses_different_unit():
    result = SlabVolumeFormula().calculate(
        {"length_ft": "27", "width_ft": "10", "thickness_in": "6"}
    )
    assert result.value == Decimal("5.0000")
    assert result.unit == Unit.CUBIC_YARD


def test_decimal_precision_not_float():
    result = WallGrossAreaFormula().calculate({"length_ft": "0.1", "height_ft": "0.2"})
    # 0.1 * 0.2 == 0.02 exactly with Decimal (not 0.020000000000000004).
    assert result.value == Decimal("0.0200")
    assert isinstance(result.value, Decimal)


def test_missing_input_rejected():
    with pytest.raises(QuantityInputError):
        WallGrossAreaFormula().calculate({"length_ft": "10"})


def test_negative_input_rejected():
    with pytest.raises(QuantityInputError):
        WallGrossAreaFormula().calculate({"length_ft": "-10", "height_ft": "9"})


def test_unexpected_input_rejected():
    with pytest.raises(QuantityInputError):
        WallGrossAreaFormula().calculate(
            {"length_ft": "10", "height_ft": "9", "extra": "1"}
        )


def test_reproducibility():
    inputs = {"length_ft": "20", "height_ft": "9"}
    a = WallGrossAreaFormula().calculate(inputs)
    b = WallGrossAreaFormula().calculate(inputs)
    assert a.value == b.value
    assert a.formula_version == b.formula_version


def test_formula_version_recorded():
    result = WallGrossAreaFormula().calculate({"length_ft": "1", "height_ft": "1"})
    assert result.formula_id == "painting.wall_gross_area"
    assert result.formula_version == "1.0"


def test_unit_compatibility():
    assert units_compatible(Unit.SQUARE_FOOT, Unit.SQUARE_YARD) is True
    assert units_compatible(Unit.SQUARE_FOOT, Unit.LINEAR_FOOT) is False


# --- Registry guards -------------------------------------------------------
def _registry() -> FormulaRegistry:
    registry = FormulaRegistry()
    for formula in painting_formulas():
        registry.register(formula)
    registry.register(SlabVolumeFormula())
    return registry


def test_arbitrary_formula_name_rejected():
    with pytest.raises(FormulaError):
        _registry().get("painting.make_up_a_number")


def test_formula_must_be_registered_for_trade():
    registry = _registry()
    # The painting wall formula is not available to the concrete trade.
    with pytest.raises(FormulaError):
        registry.get_for_trade("painting.wall_gross_area", "demo_concrete")


def test_duplicate_formula_registration_rejected():
    registry = FormulaRegistry()
    registry.register(WallGrossAreaFormula())
    with pytest.raises(FormulaError):
        registry.register(WallGrossAreaFormula())
