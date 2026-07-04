"""Shared, trade-agnostic deterministic geometry helpers.

Pure ``Decimal`` arithmetic reused by trade-module formulas. Keeping the geometry
here (rather than in any one trade) keeps the math consistent and testable across
every trade.
"""

from __future__ import annotations

from decimal import Decimal

CUBIC_FEET_PER_CUBIC_YARD = Decimal("27")
INCHES_PER_FOOT = Decimal("12")


def rectangle_area(length: Decimal, width: Decimal) -> Decimal:
    """Area of a rectangle (same length unit in → unit² out)."""
    return length * width


def prism_volume(length: Decimal, width: Decimal, height: Decimal) -> Decimal:
    return length * width * height


def inches_to_feet(inches: Decimal) -> Decimal:
    return inches / INCHES_PER_FOOT


def cubic_feet_to_cubic_yards(cubic_feet: Decimal) -> Decimal:
    return cubic_feet / CUBIC_FEET_PER_CUBIC_YARD


def sum_segments(segments: list[Decimal]) -> Decimal:
    total = Decimal("0")
    for segment in segments:
        total += segment
    return total
