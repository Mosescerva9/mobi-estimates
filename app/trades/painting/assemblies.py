"""Painting reference assembly templates (STRUCTURE ONLY — no prices).

These define how a painting scope item decomposes into labor/material/equipment/
other-direct components and which cost-item codes each references. Actual dollar
rates live in a cost book (fictional values in tests). No market prices are bundled
here. Coats, substrate, coverage, height/access are never assumed — required inputs
are declared and enforced.
"""

from __future__ import annotations

from typing import Any

# Cost-item codes referenced by these templates (rates supplied by a cost book).
PAINTER = "PAINTER"

PAINTING_ASSEMBLY_TEMPLATES: list[dict[str, Any]] = [
    {
        "assembly_code": "PT-INT-WALL",
        "name": "Interior wall coating",
        "scope_category": "interior_walls",
        "input_unit": "SF",
        "required_trade_data": ["coating_system", "finish_coats"],
        "required_evidence_types": ["finish_schedule", "room_finish_schedule"],
        "components": [
            {"component_type": "labor", "cost_item_ref": PAINTER,
             "production_ref": "PROD-PT-PREP", "quantity_factor": "1", "sequence": 1},
            {"component_type": "material", "cost_item_ref": "MAT-PT-PRIMER",
             "quantity_factor": "1", "waste_factor": "0.05", "sequence": 2},
            {"component_type": "labor", "cost_item_ref": PAINTER,
             "production_ref": "PROD-PT-FINISH", "quantity_factor": "1", "sequence": 3},
            {"component_type": "material", "cost_item_ref": "MAT-PT-FINISH",
             "quantity_factor": "1", "waste_factor": "0.05", "sequence": 4},
            {"component_type": "other_direct", "cost_item_ref": "ODC-MASKING",
             "quantity_factor": "1", "sequence": 5},
        ],
    },
    {
        "assembly_code": "PT-INT-CEILING",
        "name": "Interior ceiling coating",
        "scope_category": "interior_ceilings",
        "input_unit": "SF",
        "required_trade_data": ["coating_system", "finish_coats"],
        "components": [
            {"component_type": "labor", "cost_item_ref": PAINTER,
             "production_ref": "PROD-PT-FINISH", "quantity_factor": "1", "sequence": 1},
            {"component_type": "material", "cost_item_ref": "MAT-PT-FINISH",
             "quantity_factor": "1", "waste_factor": "0.05", "sequence": 2},
        ],
    },
    {
        "assembly_code": "PT-DOOR-FRAME",
        "name": "Door frame coating",
        "scope_category": "door_frames",
        "input_unit": "EA",
        "required_trade_data": ["coating_system"],
        "components": [
            {"component_type": "labor", "cost_item_ref": PAINTER,
             "production_ref": "PROD-PT-FRAME", "quantity_factor": "1", "sequence": 1},
            {"component_type": "material", "cost_item_ref": "MAT-PT-FINISH",
             "quantity_factor": "0.5", "waste_factor": "0.10", "sequence": 2},
        ],
    },
    {
        "assembly_code": "PT-SURFACE-PREP",
        "name": "Surface preparation",
        "scope_category": "surface_preparation",
        "input_unit": "SF",
        "required_trade_data": [],
        "components": [
            {"component_type": "labor", "cost_item_ref": PAINTER,
             "production_ref": "PROD-PT-PREP", "quantity_factor": "1", "sequence": 1},
        ],
    },
]

_CATEGORY_TO_ASSEMBLY = {a["scope_category"]: a["assembly_code"]
                         for a in PAINTING_ASSEMBLY_TEMPLATES}


def painting_assembly_templates() -> list[dict[str, Any]]:
    return [dict(a) for a in PAINTING_ASSEMBLY_TEMPLATES]


def map_painting_scope(category_code: str, trade_data: dict[str, Any]) -> list[str]:
    code = _CATEGORY_TO_ASSEMBLY.get(category_code)
    return [code] if code else []


def validate_painting_pricing_inputs(
    *, category_code: str, trade_data: dict[str, Any], assembly: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for required in assembly.get("required_trade_data", []):
        if trade_data.get(required) in (None, ""):
            errors.append(f"painting assembly '{assembly['assembly_code']}' "
                          f"requires trade-data '{required}'")
    return errors
