"""Trade-agnostic unit registry and dimension compatibility.

Units are deliberately small and explicit. The deterministic quantity engine uses
this registry to reject incompatible units (e.g. multiplying two lengths must
yield an area, not a length). Trade modules declare which units they support.
"""

from __future__ import annotations

from enum import Enum


class UnitDimension(str, Enum):
    LENGTH = "length"
    AREA = "area"
    VOLUME = "volume"
    COUNT = "count"
    VOLUME_LIQUID = "volume_liquid"
    WEIGHT = "weight"


class Unit(str, Enum):
    # Length
    LINEAR_FOOT = "LF"
    # Area
    SQUARE_FOOT = "SF"
    SQUARE_YARD = "SY"
    SQUARE = "SQ"  # roofing square = 100 SF
    # Volume
    CUBIC_FOOT = "CF"
    CUBIC_YARD = "CY"
    # Count
    EACH = "EA"
    # Liquid
    GALLON = "GAL"
    # Weight
    POUND = "LB"
    TON = "TON"


_UNIT_DIMENSIONS: dict[Unit, UnitDimension] = {
    Unit.LINEAR_FOOT: UnitDimension.LENGTH,
    Unit.SQUARE_FOOT: UnitDimension.AREA,
    Unit.SQUARE_YARD: UnitDimension.AREA,
    Unit.SQUARE: UnitDimension.AREA,
    Unit.CUBIC_FOOT: UnitDimension.VOLUME,
    Unit.CUBIC_YARD: UnitDimension.VOLUME,
    Unit.EACH: UnitDimension.COUNT,
    Unit.GALLON: UnitDimension.VOLUME_LIQUID,
    Unit.POUND: UnitDimension.WEIGHT,
    Unit.TON: UnitDimension.WEIGHT,
}


def unit_dimension(unit: Unit) -> UnitDimension:
    return _UNIT_DIMENSIONS[unit]


def units_compatible(a: Unit, b: Unit) -> bool:
    """True if two units measure the same physical dimension."""
    return unit_dimension(a) == unit_dimension(b)


def is_unit(value: str) -> bool:
    return value in Unit._value2member_map_


def coerce_unit(value: str | Unit) -> Unit:
    if isinstance(value, Unit):
        return value
    if value not in Unit._value2member_map_:
        raise ValueError(f"Unknown unit '{value}'")
    return Unit(value)
