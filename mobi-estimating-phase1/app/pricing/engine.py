"""Deterministic, pure-Python pricing engine.

Prices approved scope items from a self-contained, immutable **snapshot** (so a
historical estimate reprices identically even if the live cost book changes). No AI,
no floats — only ``Decimal``. A required component that cannot be priced marks the
whole line *incomplete* and emits a visible exception; unpriced scope never silently
disappears.

The engine is trade-agnostic: it reads assembly component structures and rate tables
from the snapshot and never branches on a specific trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.pricing.money import (
    MoneyError,
    quantize_calc,
    quantize_money,
    to_decimal,
)
from app.pricing.schemas import (
    CREW_BASES,
    DURATION_EQUIPMENT_BASES,
    ComponentType,
    EquipmentRateBasis,
    ExceptionCode,
    ExceptionSeverity,
    ProductionBasis,
)

PRICING_ENGINE_VERSION = "1.0.0"
ROUNDING_POLICY = "line_level_half_up_2dp"


@dataclass
class PricingException:
    code: str
    severity: str
    message: str
    scope_item_id: str | None = None
    component_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "severity": self.severity, "message": self.message,
            "scope_item_id": self.scope_item_id, "component_ref": self.component_ref,
        }


@dataclass
class LineItem:
    scope_item_id: str
    trade_code: str
    category_code: str
    description: str
    location: str | None
    assembly_code: str | None
    quantity: Decimal
    unit: str | None
    labor_hours: Decimal = Decimal("0")
    crew_hours: Decimal = Decimal("0")
    labor_cost: Decimal = Decimal("0")
    material_cost: Decimal = Decimal("0")
    equipment_cost: Decimal = Decimal("0")
    subcontract_cost: Decimal = Decimal("0")
    other_direct_cost: Decimal = Decimal("0")
    direct_cost_total: Decimal = Decimal("0")
    status: str = "priced"  # priced | incomplete | unpriced
    components: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[PricingException] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope_item_id": self.scope_item_id, "trade_code": self.trade_code,
            "category_code": self.category_code, "description": self.description,
            "location": self.location, "assembly_code": self.assembly_code,
            "quantity": str(self.quantity), "unit": self.unit,
            "labor_hours": str(quantize_calc(self.labor_hours)),
            "crew_hours": str(quantize_calc(self.crew_hours)),
            "labor_cost": str(quantize_money(self.labor_cost)),
            "material_cost": str(quantize_money(self.material_cost)),
            "equipment_cost": str(quantize_money(self.equipment_cost)),
            "subcontract_cost": str(quantize_money(self.subcontract_cost)),
            "other_direct_cost": str(quantize_money(self.other_direct_cost)),
            "direct_cost_total": str(quantize_money(self.direct_cost_total)),
            "status": self.status,
            "components": self.components,
            "exceptions": [e.as_dict() for e in self.exceptions],
            "evidence": self.evidence,
        }


@dataclass
class EngineResult:
    line_items: list[LineItem]
    exceptions: list[PricingException]

    @property
    def has_blocking(self) -> bool:
        return any(e.severity == ExceptionSeverity.BLOCKING.value
                   for e in self.all_exceptions())

    def all_exceptions(self) -> list[PricingException]:
        out = list(self.exceptions)
        for li in self.line_items:
            out.extend(li.exceptions)
        return out


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


class _Pricer:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.s = snapshot
        self.pricing_date = _parse_date(snapshot.get("pricing_date")) or date.today()
        self.stale_policy = snapshot.get("stale_policy", "warn")
        self.unverified_policy = snapshot.get("unverified_policy", "warn")
        self.sources = snapshot.get("sources", {})

    # --- rate source / date validation ------------------------------------
    def _check_source(self, source_id: str | None, scope_id: str, ref: str,
                       expiration: Any) -> list[PricingException]:
        issues: list[PricingException] = []
        exp = _parse_date(expiration)
        if exp is not None and exp < self.pricing_date:
            sev = (ExceptionSeverity.BLOCKING.value if self.stale_policy == "block"
                   else ExceptionSeverity.WARNING.value)
            issues.append(PricingException(
                ExceptionCode.EXPIRED_RATE.value, sev,
                f"Rate '{ref}' expired on {exp.isoformat()} (priced {self.pricing_date.isoformat()})",
                scope_id, ref))
        source = self.sources.get(str(source_id)) if source_id else None
        if source is not None and not source.get("verified", False):
            sev = (ExceptionSeverity.BLOCKING.value if self.unverified_policy == "block"
                   else ExceptionSeverity.WARNING.value)
            issues.append(PricingException(
                ExceptionCode.UNVERIFIED_SOURCE.value, sev,
                f"Rate '{ref}' uses an unverified cost source", scope_id, ref))
        return issues

    # --- component pricing -------------------------------------------------
    def _price_material(self, comp, qty, scope_id):
        ref = comp["cost_item_ref"]
        rates = self.s.get("material_rates", {})
        mat = rates.get(ref)
        if mat is None:
            return None, PricingException(ExceptionCode.MISSING_MATERIAL_RATE.value,
                ExceptionSeverity.BLOCKING.value, f"No material rate for '{ref}'",
                scope_id, ref), []
        qf = to_decimal(comp.get("quantity_factor", "1"), field="quantity_factor")
        waste = to_decimal(comp.get("waste_factor") or "0", field="waste_factor")
        extra: list[PricingException] = []
        # Waste is separate unless the source already includes it.
        if mat.get("waste_included") and waste > 0:
            waste = Decimal("0")
        required = qty * qf * (Decimal("1") + waste)
        # Coverage conversion (e.g. SF of wall -> gallons).
        coverage = mat.get("coverage_per_unit")
        if comp.get("conversion_id") or (coverage not in (None, "")):
            if coverage in (None, ""):
                return None, PricingException(ExceptionCode.MISSING_UNIT_CONVERSION.value,
                    ExceptionSeverity.BLOCKING.value,
                    f"Material '{ref}' needs coverage data to convert units",
                    scope_id, ref), []
            purchase_qty = required / to_decimal(coverage, field="coverage")
        else:
            purchase_qty = required
        unit_cost = to_decimal(mat["unit_cost"], field="unit_cost")
        cost = quantize_calc(purchase_qty * unit_cost)
        extra += self._check_source(mat.get("source_id"), scope_id, ref,
                                    mat.get("expiration_date"))
        detail = {"type": "material", "ref": ref, "required": str(quantize_calc(required)),
                  "purchase_qty": str(quantize_calc(purchase_qty)),
                  "unit_cost": str(unit_cost), "waste_factor": str(waste),
                  "cost": str(quantize_money(cost))}
        return ("material", cost, detail), None, extra

    def _price_labor(self, comp, qty, scope_id):
        prod_ref = comp.get("production_ref")
        prods = self.s.get("production_rates", {})
        prod = prods.get(prod_ref) if prod_ref else None
        if prod is None:
            return None, PricingException(ExceptionCode.MISSING_PRODUCTION_RATE.value,
                ExceptionSeverity.BLOCKING.value,
                f"No production rate '{prod_ref}' for labor component", scope_id,
                comp.get("cost_item_ref")), []
        basis = ProductionBasis(prod["basis"])
        qf = to_decimal(comp.get("quantity_factor", "1"), field="quantity_factor")
        eff_qty = qty * qf
        value = to_decimal(prod["value"], field="production_value", allow_zero=False)
        extra: list[PricingException] = []
        labor_hours = Decimal("0")
        crew_hours = Decimal("0")

        if basis == ProductionBasis.LABOR_HOURS_PER_UNIT:
            labor_hours = eff_qty * value
        elif basis == ProductionBasis.UNITS_PER_LABOR_HOUR:
            labor_hours = eff_qty / value
        elif basis == ProductionBasis.CREW_HOURS_PER_UNIT:
            crew_hours = eff_qty * value
        elif basis == ProductionBasis.UNITS_PER_CREW_HOUR:
            crew_hours = eff_qty / value
        elif basis == ProductionBasis.MANUAL_ALLOWANCE:
            labor_hours = value  # explicit total hours allowance
        else:  # units_per_shift and anything unhandled
            return None, PricingException(ExceptionCode.MANUAL_REVIEW_REQUIRED.value,
                ExceptionSeverity.BLOCKING.value,
                f"Production basis '{basis.value}' requires manual review",
                scope_id, comp.get("cost_item_ref")), []

        if basis in CREW_BASES:
            crew_code = comp.get("crew_ref") or prod.get("crew_code")
            crew = self.s.get("crews", {}).get(crew_code) if crew_code else None
            if crew is None:
                return None, PricingException(ExceptionCode.MISSING_CREW.value,
                    ExceptionSeverity.BLOCKING.value,
                    f"No crew '{crew_code}' for crew-hour production", scope_id,
                    comp.get("cost_item_ref")), []
            crew_rate = to_decimal(crew["loaded_crew_hour_rate"], field="crew_rate")
            cost = quantize_calc(crew_hours * crew_rate)
            rate_used, rate_id = crew_rate, crew_code
        else:
            classification = comp["cost_item_ref"]
            lr = self.s.get("labor_rates", {}).get(classification)
            if lr is None:
                return None, PricingException(ExceptionCode.MISSING_LABOR_RATE.value,
                    ExceptionSeverity.BLOCKING.value,
                    f"No loaded labor rate for '{classification}'", scope_id,
                    classification), []
            rate_used = to_decimal(lr["loaded_rate"], field="loaded_rate")
            cost = quantize_calc(labor_hours * rate_used)
            rate_id = classification
            extra += self._check_source(lr.get("source_id"), scope_id, classification,
                                        lr.get("expiration_date"))
        extra += self._check_source(prod.get("source_id"), scope_id, prod_ref,
                                    prod.get("expiration_date"))
        detail = {"type": "labor", "ref": comp.get("cost_item_ref"),
                  "production_ref": prod_ref, "basis": basis.value,
                  "labor_hours": str(quantize_calc(labor_hours)),
                  "crew_hours": str(quantize_calc(crew_hours)),
                  "rate": str(rate_used), "rate_id": rate_id,
                  "cost": str(quantize_money(cost))}
        return ("labor", cost, detail, labor_hours, crew_hours), None, extra

    def _price_equipment(self, comp, qty, scope_id):
        ref = comp["cost_item_ref"]
        eq = self.s.get("equipment_rates", {}).get(ref)
        if eq is None:
            return None, PricingException(ExceptionCode.CALCULATION_FAILURE.value,
                ExceptionSeverity.BLOCKING.value, f"No equipment rate for '{ref}'",
                scope_id, ref), []
        basis = EquipmentRateBasis(eq["basis"])
        qf = to_decimal(comp.get("quantity_factor", "1"), field="quantity_factor")
        fixed = bool(comp.get("conditions", {}).get("fixed"))
        duration = comp.get("conditions", {}).get("duration")
        if basis in DURATION_EQUIPMENT_BASES:
            if duration is None and not fixed and qf == 0:
                return None, PricingException(ExceptionCode.MISSING_EQUIPMENT_DURATION.value,
                    ExceptionSeverity.BLOCKING.value,
                    f"Equipment '{ref}' ({basis.value}) needs an explicit duration",
                    scope_id, ref), []
            units = (to_decimal(duration, field="duration") if duration is not None
                     else (qf if fixed else qty * qf))
        else:  # each
            units = qf if fixed else qty * qf
        base_rate = to_decimal(eq["base_rate"], field="base_rate")
        cost = units * base_rate
        for adder in ("delivery", "pickup", "fuel"):
            if eq.get(adder) not in (None, ""):
                cost += to_decimal(eq[adder], field=adder)
        min_charge = eq.get("minimum_charge")
        if min_charge not in (None, ""):
            cost = max(cost, to_decimal(min_charge, field="minimum_charge"))
        cost = quantize_calc(cost)
        extra = self._check_source(eq.get("source_id"), scope_id, ref,
                                   eq.get("expiration_date"))
        detail = {"type": "equipment", "ref": ref, "basis": basis.value,
                  "units": str(quantize_calc(units)), "base_rate": str(base_rate),
                  "operator_included": bool(eq.get("operator_included")),
                  "cost": str(quantize_money(cost))}
        return ("equipment", cost, detail), None, extra

    def _price_other(self, comp, qty, scope_id):
        ref = comp["cost_item_ref"]
        odc = self.s.get("other_direct", {}).get(ref)
        if odc is None:
            return None, PricingException(ExceptionCode.CALCULATION_FAILURE.value,
                ExceptionSeverity.BLOCKING.value, f"No other-direct-cost item '{ref}'",
                scope_id, ref), []
        qf = to_decimal(comp.get("quantity_factor", "1"), field="quantity_factor")
        fixed = bool(comp.get("conditions", {}).get("fixed"))
        units = qf if fixed else qty * qf
        unit_rate = to_decimal(odc["unit_rate"], field="unit_rate")
        cost = quantize_calc(units * unit_rate)
        detail = {"type": "other_direct", "ref": ref, "units": str(quantize_calc(units)),
                  "unit_rate": str(unit_rate), "cost": str(quantize_money(cost))}
        return ("other_direct", cost, detail), None, []

    def _price_subcontract(self, comp, qty, scope_id):
        ref = comp["cost_item_ref"]
        sub = self.s.get("subcontract", {}).get(ref)
        if sub is None:
            return None, PricingException(ExceptionCode.CALCULATION_FAILURE.value,
                ExceptionSeverity.BLOCKING.value, f"No subcontract quote '{ref}'",
                scope_id, ref), []
        extra: list[PricingException] = []
        base = to_decimal(sub["base_amount"], field="base_amount")
        leveling = to_decimal(sub.get("leveling_adjustment") or "0",
                              field="leveling_adjustment", allow_negative=True)
        cost = quantize_calc(base + leveling)
        if not sub.get("verified", False):
            extra.append(PricingException(ExceptionCode.MISSING_SUBCONTRACT_REVIEW.value,
                ExceptionSeverity.WARNING.value,
                f"Subcontract quote '{ref}' is unverified / scope not reviewed",
                scope_id, ref))
        detail = {"type": "subcontract", "ref": ref, "base_amount": str(base),
                  "leveling_adjustment": str(leveling), "cost": str(quantize_money(cost))}
        return ("subcontract", cost, detail), None, extra

    # --- line pricing ------------------------------------------------------
    def price_line(self, scope: dict[str, Any]) -> LineItem:
        scope_id = scope["id"]
        line = LineItem(
            scope_item_id=scope_id, trade_code=scope["trade_code"],
            category_code=scope["category_code"], description=scope.get("description", ""),
            location=scope.get("location"), assembly_code=scope.get("assembly_code"),
            quantity=to_decimal(scope.get("quantity") or "0", field="quantity"),
            unit=scope.get("unit"), evidence=scope.get("evidence", []),
        )
        assembly_code = scope.get("assembly_code")
        if not assembly_code:
            line.status = "unpriced"
            line.exceptions.append(PricingException(
                ExceptionCode.MISSING_ASSEMBLY_MAPPING.value,
                ExceptionSeverity.BLOCKING.value,
                "No approved assembly mapping for this scope item", scope_id))
            return line
        assembly = self.s.get("assemblies", {}).get(assembly_code)
        if assembly is None:
            line.status = "unpriced"
            line.exceptions.append(PricingException(
                ExceptionCode.MISSING_ASSEMBLY_MAPPING.value,
                ExceptionSeverity.BLOCKING.value,
                f"Assembly '{assembly_code}' is not in the snapshot", scope_id))
            return line

        # Required trade-data inputs for the assembly.
        trade_data = scope.get("trade_data") or {}
        for required in assembly.get("required_trade_data", []):
            if trade_data.get(required) in (None, ""):
                line.exceptions.append(PricingException(
                    ExceptionCode.MISSING_ASSEMBLY_INPUT.value,
                    ExceptionSeverity.BLOCKING.value,
                    f"Assembly '{assembly_code}' requires trade-data '{required}'",
                    scope_id))

        dispatch = {
            ComponentType.MATERIAL.value: self._price_material,
            ComponentType.LABOR.value: self._price_labor,
            ComponentType.EQUIPMENT.value: self._price_equipment,
            ComponentType.OTHER_DIRECT.value: self._price_other,
            ComponentType.SUBCONTRACT.value: self._price_subcontract,
        }
        for comp in sorted(assembly.get("components", []),
                           key=lambda c: c.get("sequence", 0)):
            ctype = comp["component_type"]
            pricer = dispatch.get(ctype)
            if pricer is None:
                line.exceptions.append(PricingException(
                    ExceptionCode.CALCULATION_FAILURE.value,
                    ExceptionSeverity.BLOCKING.value,
                    f"Unknown component type '{ctype}'", scope_id,
                    comp.get("cost_item_ref")))
                continue
            try:
                result, blocker, extra = pricer(comp, line.quantity, scope_id)
            except MoneyError as exc:
                result, blocker, extra = None, PricingException(
                    ExceptionCode.CALCULATION_FAILURE.value,
                    ExceptionSeverity.BLOCKING.value, str(exc), scope_id,
                    comp.get("cost_item_ref")), []
            line.exceptions.extend(extra)
            if blocker is not None:
                line.exceptions.append(blocker)
                continue
            kind, cost = result[0], result[1]
            line.components.append(result[2])
            if kind == "material":
                line.material_cost += cost
            elif kind == "labor":
                line.labor_cost += cost
                line.labor_hours += result[3]
                line.crew_hours += result[4]
            elif kind == "equipment":
                line.equipment_cost += cost
            elif kind == "subcontract":
                line.subcontract_cost += cost
            elif kind == "other_direct":
                line.other_direct_cost += cost

        line.direct_cost_total = (
            line.labor_cost + line.material_cost + line.equipment_cost
            + line.subcontract_cost + line.other_direct_cost
        )
        # Quantize each component bucket at the line boundary (line-level rounding).
        line.labor_cost = quantize_money(line.labor_cost)
        line.material_cost = quantize_money(line.material_cost)
        line.equipment_cost = quantize_money(line.equipment_cost)
        line.subcontract_cost = quantize_money(line.subcontract_cost)
        line.other_direct_cost = quantize_money(line.other_direct_cost)
        line.direct_cost_total = (
            line.labor_cost + line.material_cost + line.equipment_cost
            + line.subcontract_cost + line.other_direct_cost
        )
        if any(e.severity == ExceptionSeverity.BLOCKING.value for e in line.exceptions):
            line.status = "incomplete"
        return line


def price_snapshot(snapshot: dict[str, Any]) -> EngineResult:
    """Price every scope item in a snapshot deterministically."""
    pricer = _Pricer(snapshot)
    lines = [pricer.price_line(scope) for scope in snapshot.get("scope_items", [])]
    return EngineResult(line_items=lines, exceptions=[])
