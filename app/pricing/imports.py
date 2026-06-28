"""Lean CSV import for cost-book inputs (preview + atomic commit).

Validates every row before committing anything: unknown columns, invalid decimals,
invalid units, and duplicate identifiers are rejected, and a failed file imports
nothing (all-or-nothing). Templates live in ``docs/cost-book-csv-import.md`` and use
fictional example values only.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from app.estimating.units import is_unit
from app.pricing.money import MoneyError, to_decimal

# Allowed columns per import kind. Extra columns are rejected.
_SCHEMAS: dict[str, dict[str, Any]] = {
    "labor_rates": {
        "required": ["classification", "trade_code", "loaded_rate",
                     "effective_date", "source_id"],
        "decimals": ["loaded_rate"],
        "id": "classification",
    },
    "material_rates": {
        "required": ["material_code", "description", "trade_code", "purchase_unit",
                     "unit_cost", "effective_date", "source_id"],
        "decimals": ["unit_cost"],
        "units": ["purchase_unit"],
        "id": "material_code",
    },
    "equipment_rates": {
        "required": ["equipment_code", "description", "basis", "base_rate",
                     "effective_date", "source_id"],
        "decimals": ["base_rate"],
        "id": "equipment_code",
    },
    "production_rates": {
        "required": ["production_code", "trade_code", "scope_category",
                     "quantity_unit", "basis", "value", "effective_date", "source_id"],
        "decimals": ["value"],
        "units": ["quantity_unit"],
        "id": "production_code",
    },
}


class CsvImportError(ValueError):
    pass


def parse_csv(kind: str, content: str) -> dict[str, Any]:
    """Validate a CSV. Returns {'rows': [...], 'errors': [...], 'valid': bool}."""
    if kind not in _SCHEMAS:
        raise CsvImportError(f"Unknown import kind '{kind}'")
    schema = _SCHEMAS[kind]
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    allowed = set(schema["required"]) | {"expiration_date", "region", "notes",
                                         "crew_code", "assembly_code", "taxable",
                                         "manufacturer", "coverage_per_unit",
                                         "coverage_unit"}
    errors: list[dict[str, Any]] = []
    unknown = [h for h in headers if h not in allowed]
    if unknown:
        errors.append({"row": 0, "error": f"Unknown column(s): {sorted(unknown)}"})

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    id_field = schema["id"]
    for index, raw in enumerate(reader, start=1):
        row_errors: list[str] = []
        for col in schema["required"]:
            if not (raw.get(col) or "").strip():
                row_errors.append(f"missing '{col}'")
        for col in schema.get("decimals", []):
            value = (raw.get(col) or "").strip()
            if value:
                try:
                    to_decimal(value, field=col, allow_zero=False)
                except MoneyError as exc:
                    row_errors.append(str(exc))
        for col in schema.get("units", []):
            value = (raw.get(col) or "").strip()
            if value and not is_unit(value):
                row_errors.append(f"invalid unit '{value}' in '{col}'")
        identifier = (raw.get(id_field) or "").strip()
        if identifier:
            if identifier in seen_ids:
                row_errors.append(f"duplicate identifier '{identifier}'")
            seen_ids.add(identifier)
        if row_errors:
            errors.append({"row": index, "error": "; ".join(row_errors)})
        else:
            rows.append({k: (v or "").strip() for k, v in raw.items()})
    return {"kind": kind, "rows": rows, "errors": errors, "valid": not errors,
            "row_count": len(rows)}
