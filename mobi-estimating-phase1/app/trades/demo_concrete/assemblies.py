"""Demonstration Concrete assembly templates (STRUCTURE ONLY — no prices).

Deliberately different from Painting: cubic-yard material with waste, **crew-hour**
placement/finishing labor, and equipment — proving the shared engine handles
materially different pricing paths with no Painting-specific code. Reference/
development only; not production-complete and contains no real cost data.
"""

from __future__ import annotations

from typing import Any

CONCRETE_ASSEMBLY_TEMPLATES: list[dict[str, Any]] = [
    {
        "assembly_code": "CONC-SLAB",
        "name": "Slab on grade",
        "scope_category": "slab_on_grade",
        "input_unit": "CY",
        "required_trade_data": ["mix_design"],
        "components": [
            # Concrete material by CY with explicit waste.
            {"component_type": "material", "cost_item_ref": "MAT-CONC-MIX",
             "quantity_factor": "1", "waste_factor": "0.05", "sequence": 1},
            # Reinforcing (lbs per CY).
            {"component_type": "material", "cost_item_ref": "MAT-REBAR",
             "quantity_factor": "120", "waste_factor": "0.03", "sequence": 2},
            # Placement labor — CREW-hour basis (different from painting labor-hour).
            {"component_type": "labor", "cost_item_ref": "CONCRETE_CREW",
             "production_ref": "PROD-CONC-PLACE", "crew_ref": "CREW-CONC",
             "quantity_factor": "1", "sequence": 3},
            # Finishing labor — crew-hour.
            {"component_type": "labor", "cost_item_ref": "CONCRETE_CREW",
             "production_ref": "PROD-CONC-FINISH", "crew_ref": "CREW-CONC",
             "quantity_factor": "1", "sequence": 4},
            # Pump/equipment with a minimum charge.
            {"component_type": "equipment", "cost_item_ref": "EQ-PUMP",
             "quantity_factor": "1", "conditions": {"fixed": True, "duration": "1"},
             "sequence": 5},
        ],
    },
]

_CATEGORY_TO_ASSEMBLY = {a["scope_category"]: a["assembly_code"]
                         for a in CONCRETE_ASSEMBLY_TEMPLATES}


def concrete_assembly_templates() -> list[dict[str, Any]]:
    return [dict(a) for a in CONCRETE_ASSEMBLY_TEMPLATES]


def map_concrete_scope(category_code: str, trade_data: dict[str, Any]) -> list[str]:
    code = _CATEGORY_TO_ASSEMBLY.get(category_code)
    return [code] if code else []


def validate_concrete_pricing_inputs(
    *, category_code: str, trade_data: dict[str, Any], assembly: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for required in assembly.get("required_trade_data", []):
        if trade_data.get(required) in (None, ""):
            errors.append(f"concrete assembly '{assembly['assembly_code']}' "
                          f"requires trade-data '{required}'")
    return errors
