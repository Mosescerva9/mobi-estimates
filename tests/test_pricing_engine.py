"""Deterministic pricing-engine component tests (hand-built snapshots)."""

from __future__ import annotations

from decimal import Decimal

from app.pricing.engine import price_snapshot


def _snap(*, assemblies, scope, **tables):
    base = {"currency": "USD", "pricing_date": "2026-06-01",
            "cost_book_version_id": "cbv", "stale_policy": "warn",
            "unverified_policy": "warn", "sources": {"s": {"verified": True}},
            "assemblies": assemblies, "scope_items": scope}
    base.update(tables)
    return base


def _scope_item(assembly, qty="100", unit="SF", trade="painting", cat="interior_walls",
                trade_data=None):
    return [{"id": "si1", "trade_code": trade, "category_code": cat,
             "description": "x", "quantity": qty, "unit": unit,
             "assembly_code": assembly, "trade_data": trade_data or {},
             "evidence": [{"verified_sheet_number": "A-101"}]}]


def test_material_with_coverage_and_waste():
    snap = _snap(
        assemblies={"A": {"trade_code": "painting", "components": [
            {"component_type": "material", "cost_item_ref": "M", "quantity_factor": "1",
             "waste_factor": "0.05", "sequence": 1}]}},
        material_rates={"M": {"unit_cost": "30.00", "coverage_per_unit": "300",
                              "source_id": "s"}},
        scope=_scope_item("A"))
    li = price_snapshot(snap).line_items[0]
    # 100*1.05 / 300 = 0.35 gal * 30 = 10.50
    assert li.material_cost == Decimal("10.50")
    assert li.status == "priced"


def test_labor_hour_calculation():
    snap = _snap(
        assemblies={"A": {"trade_code": "painting", "components": [
            {"component_type": "labor", "cost_item_ref": "PAINTER",
             "production_ref": "P", "quantity_factor": "1", "sequence": 1}]}},
        labor_rates={"PAINTER": {"loaded_rate": "50.00", "source_id": "s"}},
        production_rates={"P": {"basis": "units_per_labor_hour", "value": "200",
                                "source_id": "s"}},
        scope=_scope_item("A"))
    li = price_snapshot(snap).line_items[0]
    assert li.labor_hours == Decimal("0.5")  # 100/200
    assert li.labor_cost == Decimal("25.00")
    assert li.crew_hours == Decimal("0")


def test_crew_hour_calculation_distinct_from_labor_hour():
    snap = _snap(
        assemblies={"A": {"trade_code": "demo_concrete", "components": [
            {"component_type": "labor", "cost_item_ref": "CREW", "production_ref": "P",
             "crew_ref": "C", "quantity_factor": "1", "sequence": 1}]}},
        crews={"C": {"loaded_crew_hour_rate": "200.00"}},
        production_rates={"P": {"basis": "crew_hours_per_unit", "value": "0.30",
                                "crew_code": "C", "source_id": "s"}},
        scope=_scope_item("A", qty="10", unit="CY", trade="demo_concrete",
                          cat="slab_on_grade"))
    li = price_snapshot(snap).line_items[0]
    assert li.crew_hours == Decimal("3.0")   # 10 * 0.30
    assert li.labor_hours == Decimal("0")    # crew hours are NOT labor hours
    assert li.labor_cost == Decimal("600.00")


def test_equipment_minimum_charge():
    snap = _snap(
        assemblies={"A": {"trade_code": "demo_concrete", "components": [
            {"component_type": "equipment", "cost_item_ref": "EQ", "quantity_factor": "1",
             "conditions": {"fixed": True, "duration": "1"}, "sequence": 1}]}},
        equipment_rates={"EQ": {"basis": "day", "base_rate": "100.00",
                                "minimum_charge": "1200.00", "source_id": "s"}},
        scope=_scope_item("A", qty="5", unit="CY", trade="demo_concrete",
                          cat="slab_on_grade"))
    li = price_snapshot(snap).line_items[0]
    assert li.equipment_cost == Decimal("1200.00")  # min charge applied


def test_missing_material_rate_blocks_line():
    snap = _snap(
        assemblies={"A": {"trade_code": "painting", "components": [
            {"component_type": "material", "cost_item_ref": "MISSING", "sequence": 1}]}},
        material_rates={}, scope=_scope_item("A"))
    li = price_snapshot(snap).line_items[0]
    assert li.status == "incomplete"
    assert any(e.code == "missing_material_rate" for e in li.exceptions)


def test_missing_assembly_mapping_is_unpriced_but_visible():
    snap = _snap(assemblies={}, scope=[{"id": "si1", "trade_code": "painting",
        "category_code": "interior_walls", "description": "x", "quantity": "100",
        "unit": "SF", "assembly_code": None, "trade_data": {}, "evidence": []}])
    li = price_snapshot(snap).line_items[0]
    assert li.status == "unpriced"
    assert any(e.code == "missing_assembly_mapping" for e in li.exceptions)


def test_expired_rate_warns():
    snap = _snap(
        assemblies={"A": {"trade_code": "painting", "components": [
            {"component_type": "material", "cost_item_ref": "M", "sequence": 1}]}},
        material_rates={"M": {"unit_cost": "10.00", "source_id": "s",
                              "expiration_date": "2026-01-01"}},
        scope=_scope_item("A"))
    li = price_snapshot(snap).line_items[0]
    assert any(e.code == "expired_rate" and e.severity == "warning" for e in li.exceptions)


def test_unverified_source_blocks_when_policy_block():
    snap = _snap(
        assemblies={"A": {"trade_code": "painting", "components": [
            {"component_type": "material", "cost_item_ref": "M", "sequence": 1}]}},
        material_rates={"M": {"unit_cost": "10.00", "source_id": "u"}},
        scope=_scope_item("A"))
    snap["sources"] = {"u": {"verified": False}}
    snap["unverified_policy"] = "block"
    li = price_snapshot(snap).line_items[0]
    assert any(e.code == "unverified_source" and e.severity == "blocking"
               for e in li.exceptions)


def test_missing_required_trade_data_blocks():
    snap = _snap(
        assemblies={"A": {"trade_code": "painting", "required_trade_data": ["coating_system"],
            "components": [{"component_type": "other_direct", "cost_item_ref": "O", "sequence": 1}]}},
        other_direct={"O": {"unit_rate": "1.00"}}, scope=_scope_item("A"))
    li = price_snapshot(snap).line_items[0]
    assert li.status == "incomplete"
    assert any(e.code == "missing_assembly_input" for e in li.exceptions)


def test_deterministic_and_no_float():
    def build():
        return _snap(
            assemblies={"A": {"trade_code": "painting", "components": [
                {"component_type": "labor", "cost_item_ref": "PAINTER", "production_ref": "P",
                 "sequence": 1}]}},
            labor_rates={"PAINTER": {"loaded_rate": "50.00", "source_id": "s"}},
            production_rates={"P": {"basis": "units_per_labor_hour", "value": "150",
                                    "source_id": "s"}},
            scope=_scope_item("A"))
    a = price_snapshot(build()).line_items[0]
    b = price_snapshot(build()).line_items[0]
    assert a.labor_cost == b.labor_cost
    assert isinstance(a.labor_cost, Decimal)
    # Component detail preserves the rate id + production ref.
    comp = a.components[0]
    assert comp["rate_id"] == "PAINTER" and comp["production_ref"] == "P"
