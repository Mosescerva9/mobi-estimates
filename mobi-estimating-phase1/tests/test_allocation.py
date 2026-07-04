"""Deterministic proportional allocation (largest-remainder) tests."""

from __future__ import annotations

from decimal import Decimal

from app.proposals.allocation import allocate_proportionally


def test_reconciles_exactly():
    parts = allocate_proportionally(Decimal("100.00"), [Decimal("90.83"), Decimal("75.19")])
    assert sum(parts) == Decimal("100.00")


def test_thirds_reconcile():
    parts = allocate_proportionally(Decimal("1.00"), [Decimal("1")] * 3)
    assert sum(parts) == Decimal("1.00")
    assert parts == [Decimal("0.34"), Decimal("0.33"), Decimal("0.33")]


def test_zero_total():
    assert allocate_proportionally(Decimal("0"), [Decimal("5"), Decimal("5")]) == \
        [Decimal("0.00"), Decimal("0.00")]


def test_all_zero_weights_even_split():
    parts = allocate_proportionally(Decimal("10.00"), [Decimal("0"), Decimal("0"), Decimal("0")])
    assert sum(parts) == Decimal("10.00")


def test_single_weight_gets_all():
    assert allocate_proportionally(Decimal("42.42"), [Decimal("7")]) == [Decimal("42.42")]


def test_empty():
    assert allocate_proportionally(Decimal("10"), []) == []


def test_proportions_respected():
    parts = allocate_proportionally(Decimal("300.00"), [Decimal("100"), Decimal("200")])
    assert parts == [Decimal("100.00"), Decimal("200.00")]


def test_many_lines_reconcile():
    weights = [Decimal("1.11") for _ in range(97)]
    parts = allocate_proportionally(Decimal("1000.00"), weights)
    assert sum(parts) == Decimal("1000.00")


def test_deterministic():
    a = allocate_proportionally(Decimal("100.00"), [Decimal("3"), Decimal("3"), Decimal("4")])
    b = allocate_proportionally(Decimal("100.00"), [Decimal("3"), Decimal("3"), Decimal("4")])
    assert a == b
