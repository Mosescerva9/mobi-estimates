"""Phase 4 data access: cost books, versions, cost inputs, assemblies, mappings,
estimates, versions, line items, snapshots, and review events.

Reuses the shared SQLite connection from ``app.database``. Published cost-book
versions and approved estimate versions are immutable — mutation attempts raise
``ImmutableError``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection
from app.tenant_boundary import assert_same_tenant_project_access, build_tenant_project_context


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, default=str, sort_keys=True)


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (list, dict)):
        return value
    return json.loads(value)


def _new_id() -> str:
    return str(uuid4())


def _project_identity(c: sqlite3.Connection, project_id: UUID) -> dict[str, str]:
    row = c.execute(
        "SELECT id, tenant_id, company_id FROM projects WHERE id=?", (str(project_id),)
    ).fetchone()
    if row is None:
        raise ValueError("project not found")
    return build_tenant_project_context(
        tenant_id=row["tenant_id"],
        company_id=row["company_id"],
        project_id=row["id"],
    )


def _version_identity(c: sqlite3.Connection, version_id: str | UUID) -> dict[str, str]:
    row = c.execute(
        """
        SELECT ev.project_id, ev.tenant_id, ev.company_id
        FROM estimate_versions ev
        JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
        JOIN projects p ON p.id = ev.project_id
        WHERE ev.id=?
          AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
          AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
        """,
        (str(version_id),),
    ).fetchone()
    if row is None:
        raise ValueError("estimate version not found")
    return build_tenant_project_context(
        tenant_id=row["tenant_id"],
        company_id=row["company_id"],
        project_id=row["project_id"],
    )


def _estimate_identity(c: sqlite3.Connection, estimate_id: str | UUID) -> dict[str, str]:
    row = c.execute(
        """
        SELECT e.project_id, e.tenant_id, e.company_id
        FROM estimates e
        JOIN projects p ON p.id = e.project_id
        WHERE e.id=?
          AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
        """,
        (str(estimate_id),),
    ).fetchone()
    if row is None:
        raise ValueError("estimate not found")
    return build_tenant_project_context(
        tenant_id=row["tenant_id"],
        company_id=row["company_id"],
        project_id=row["project_id"],
    )


def _assert_estimate_project_identity(
    c: sqlite3.Connection, estimate_id: str | UUID, project_id: UUID
) -> dict[str, str]:
    estimate_identity = _estimate_identity(c, estimate_id)
    project_identity = _project_identity(c, project_id)
    assert_same_tenant_project_access(project_identity, estimate_identity)
    return estimate_identity


def _assert_version_project_identity(
    c: sqlite3.Connection, version_id: str | UUID, project_id: UUID
) -> dict[str, str]:
    version_identity = _version_identity(c, version_id)
    project_identity = _project_identity(c, project_id)
    assert_same_tenant_project_access(project_identity, version_identity)
    return version_identity


class ImmutableError(Exception):
    """Raised when mutating a published/approved (immutable) record."""


# ---------------------------------------------------------------------------
# Cost books + versions
# ---------------------------------------------------------------------------
def create_cost_book(data: dict[str, Any]) -> dict[str, Any]:
    cid = _new_id()
    now = _now()
    with get_connection() as c:
        c.execute(
            "INSERT INTO cost_books (id,name,description,currency,region,market,"
            "organization,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, data["name"], data.get("description", ""), data.get("currency", "USD"),
             data.get("region"), data.get("market"), data.get("organization"),
             "active", now, now),
        )
        c.commit()
    return get_cost_book(UUID(cid))


def get_cost_book(cost_book_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM cost_books WHERE id=?", (str(cost_book_id),)).fetchone()
    return dict(row) if row else None


def list_cost_books(*, limit: int, offset: int) -> tuple[list[dict], int]:
    with get_connection() as c:
        total = c.execute("SELECT COUNT(*) FROM cost_books").fetchone()[0]
        rows = c.execute("SELECT * FROM cost_books ORDER BY created_at DESC LIMIT ? OFFSET ?",
                         (limit, offset)).fetchall()
    return [dict(r) for r in rows], int(total)


def create_version(cost_book_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    vid = _new_id()
    with get_connection() as c:
        c.execute(
            "INSERT INTO cost_book_versions (id,cost_book_id,version_label,status,"
            "effective_date,expiration_date,pricing_date,description,source_notes,"
            "created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (vid, str(cost_book_id), data["version_label"], "draft",
             str(data.get("effective_date")), str(data["expiration_date"]) if data.get("expiration_date") else None,
             str(data.get("pricing_date")), data.get("description", ""),
             data.get("source_notes", ""), _now()),
        )
        c.commit()
    return get_version(UUID(vid))


def get_version(version_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM cost_book_versions WHERE id=?", (str(version_id),)).fetchone()
    return dict(row) if row else None


def list_versions(cost_book_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT * FROM cost_book_versions WHERE cost_book_id=? "
                         "ORDER BY created_at", (str(cost_book_id),)).fetchall()
    return [dict(r) for r in rows]


def assert_draft(version_id: UUID) -> dict[str, Any]:
    version = get_version(version_id)
    if version is None:
        raise ImmutableError("Cost-book version not found")
    if version["status"] != "draft":
        raise ImmutableError(
            f"Cost-book version is '{version['status']}' and is immutable; "
            "create a new draft version to make changes")
    return version


def publish_version(version_id: UUID, *, errors: list[str]) -> dict[str, Any]:
    version = get_version(version_id)
    if version is None:
        raise ImmutableError("Cost-book version not found")
    if version["status"] == "published":
        return version
    if version["status"] != "draft":
        raise ImmutableError(f"Cannot publish a '{version['status']}' version")
    if errors:
        raise ImmutableError("; ".join(errors))
    with get_connection() as c:
        c.execute("UPDATE cost_book_versions SET status='published', published_at=? WHERE id=?",
                  (_now(), str(version_id)))
        c.commit()
    return get_version(version_id)


def archive_version(version_id: UUID) -> dict[str, Any]:
    with get_connection() as c:
        c.execute("UPDATE cost_book_versions SET status='archived', archived_at=? WHERE id=?",
                  (_now(), str(version_id)))
        c.commit()
    return get_version(version_id)


# ---------------------------------------------------------------------------
# Generic cost-input insert/list (draft-only mutation)
# ---------------------------------------------------------------------------
def _insert(table: str, columns: dict[str, Any]) -> str:
    rid = columns.get("id") or _new_id()
    columns["id"] = rid
    columns.setdefault("created_at", _now())
    cols = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    with get_connection() as c:
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                  list(columns.values()))
        c.commit()
    return rid


def add_cost_source(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    rid = _insert("cost_sources", {
        "version_id": str(version_id), "source_type": data["source_type"],
        "source_name": data["source_name"], "effective_date": str(data.get("effective_date")),
        "expiration_date": str(data["expiration_date"]) if data.get("expiration_date") else None,
        "verified": 1 if data.get("verified") else 0,
        "payload": _dumps({k: str(v) for k, v in data.items()
                           if k not in {"source_type", "source_name", "effective_date",
                                        "expiration_date", "verified"}}),
        "updated_at": _now(),
    })
    return {"id": rid, **data}


def compute_loaded_labor_rate(data: dict[str, Any]) -> str:
    """Deterministically compute the loaded labor rate (Python, not provider).

    ``manual_all_in`` uses the verified all-in rate; ``component_calculated`` sums
    the base wage plus each burden component exactly once (never doubled). A
    pre-supplied ``loaded_rate`` (e.g. from a CSV import) is used as-is."""
    from decimal import Decimal
    from app.pricing.money import to_decimal
    if data.get("loaded_rate") is not None:
        return str(to_decimal(data["loaded_rate"], field="loaded_rate"))
    rate_type = data.get("rate_type", "manual_all_in")
    if rate_type == "manual_all_in":
        return str(to_decimal(data["manual_all_in_rate"], field="manual_all_in_rate"))
    total = to_decimal(data.get("base_hourly_wage"), field="base_hourly_wage")
    for value in (data.get("burden") or {}).values():
        if value not in (None, ""):
            total += to_decimal(value, field="burden")
    return str(total)


def add_labor_rate(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    loaded = compute_loaded_labor_rate(data)
    rid = _insert("labor_rates", {
        "version_id": str(version_id), "classification": data["classification"],
        "trade_code": data["trade_code"], "rate_type": data.get("rate_type", "manual_all_in"),
        "loaded_rate": loaded,
        "base_wage": str(data["base_hourly_wage"]) if data.get("base_hourly_wage") is not None else None,
        "burden": _dumps(data.get("burden")), "effective_date": str(data.get("effective_date")),
        "expiration_date": str(data["expiration_date"]) if data.get("expiration_date") else None,
        "source_id": str(data["source_id"]) if data.get("source_id") else None,
        "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, "loaded_rate": loaded, **data}


def compute_loaded_crew_hour_rate(version_id: UUID, data: dict[str, Any]) -> str:
    """Loaded crew-hour rate: supplied verified all-in, else computed in Python from
    member counts × each member's loaded labor rate in the same version."""
    from decimal import Decimal
    from app.pricing.money import to_decimal
    if data.get("loaded_crew_hour_rate") is not None:
        return str(to_decimal(data["loaded_crew_hour_rate"], field="loaded_crew_hour_rate"))
    labor = {r["classification"]: r["loaded_rate"] for r in list_inputs("labor_rates", version_id)}
    total = Decimal("0")
    for member in data.get("members", []):
        rate = labor.get(member["classification"])
        if rate is None:
            raise ImmutableError(
                f"Cannot compute crew rate: no labor rate for '{member['classification']}'")
        total += to_decimal(rate, field="loaded_rate") * to_decimal(member["count"], field="count")
    return str(total)


def add_crew(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    loaded = compute_loaded_crew_hour_rate(version_id, data)
    rid = _insert("crews", {
        "version_id": str(version_id), "crew_code": data["crew_code"],
        "trade_code": data["trade_code"], "name": data.get("name"),
        "members": _dumps(data.get("members")),
        "loaded_crew_hour_rate": loaded,
        "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, "loaded_crew_hour_rate": loaded, **data}


def add_production_rate(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    rid = _insert("production_rates", {
        "version_id": str(version_id), "production_code": data["production_code"],
        "trade_code": data["trade_code"], "scope_category": data.get("scope_category"),
        "assembly_code": data.get("assembly_code"), "quantity_unit": data.get("quantity_unit"),
        "basis": data["basis"], "value": str(data["value"]),
        "crew_code": data.get("crew_code"),
        "source_id": str(data["source_id"]) if data.get("source_id") else None,
        "effective_date": str(data.get("effective_date")),
        "expiration_date": str(data["expiration_date"]) if data.get("expiration_date") else None,
        "verified": 1 if data.get("verified") else 0, "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, **data}


def add_material_rate(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    rid = _insert("material_rates", {
        "version_id": str(version_id), "material_code": data["material_code"],
        "description": data.get("description"), "trade_code": data.get("trade_code"),
        "purchase_unit": data.get("purchase_unit"), "unit_cost": str(data["unit_cost"]),
        "coverage_per_unit": str(data["coverage_per_unit"]) if data.get("coverage_per_unit") is not None else None,
        "coverage_unit": data.get("coverage_unit"),
        "taxable": 1 if data.get("taxable", True) else 0,
        "freight_included": 1 if data.get("freight_included") else 0,
        "waste_included": 1 if data.get("waste_included") else 0,
        "source_id": str(data["source_id"]) if data.get("source_id") else None,
        "effective_date": str(data.get("effective_date")),
        "expiration_date": str(data["expiration_date"]) if data.get("expiration_date") else None,
        "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, **data}


def add_equipment_rate(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    rid = _insert("equipment_rates", {
        "version_id": str(version_id), "equipment_code": data["equipment_code"],
        "description": data.get("description"), "trade_code": data.get("trade_code"),
        "basis": data["basis"], "base_rate": str(data["base_rate"]),
        "delivery": str(data["delivery"]) if data.get("delivery") is not None else None,
        "pickup": str(data["pickup"]) if data.get("pickup") is not None else None,
        "fuel": str(data["fuel"]) if data.get("fuel") is not None else None,
        "operator_included": 1 if data.get("operator_included") else 0,
        "mobilization_included": 1 if data.get("mobilization_included") else 0,
        "minimum_charge": str(data["minimum_charge"]) if data.get("minimum_charge") is not None else None,
        "source_id": str(data["source_id"]) if data.get("source_id") else None,
        "effective_date": str(data.get("effective_date")),
        "expiration_date": str(data["expiration_date"]) if data.get("expiration_date") else None,
        "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, **data}


def add_subcontract_quote(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    rid = _insert("subcontract_quotes", {
        "version_id": str(version_id), "sub_code": data["sub_code"],
        "project_id": str(data["project_id"]) if data.get("project_id") else None,
        "trade_code": data.get("trade_code"), "vendor_label": data.get("vendor_label"),
        "base_amount": str(data["base_amount"]),
        "leveling_adjustment": str(data["leveling_adjustment"]) if data.get("leveling_adjustment") is not None else None,
        "verified": 1 if data.get("verified") else 0,
        "source_id": str(data["source_id"]) if data.get("source_id") else None,
        "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, **data}


def add_other_direct_cost(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    rid = _insert("other_direct_costs", {
        "version_id": str(version_id), "odc_code": data["odc_code"],
        "cost_type": data.get("cost_type"), "description": data.get("description"),
        "unit": data.get("unit"), "unit_rate": str(data["unit_rate"]),
        "taxable": 1 if data.get("taxable") else 0,
        "source_id": str(data["source_id"]) if data.get("source_id") else None,
        "payload": _dumps(data.get("payload")),
    })
    return {"id": rid, **data}


_IMPORT_ADDERS = {
    "labor_rates": "add_labor_rate",
    "material_rates": "add_material_rate",
    "equipment_rates": "add_equipment_rate",
    "production_rates": "add_production_rate",
}


def commit_import(version_id: UUID, kind: str, rows: list[dict[str, Any]]) -> int:
    """Atomically import validated CSV rows into a draft version (all-or-nothing)."""
    assert_draft(version_id)
    adder = globals()[_IMPORT_ADDERS[kind]]
    inserted = 0
    with get_connection() as c:  # single transaction for atomicity
        for row in rows:
            payload = {k: v for k, v in row.items() if v not in ("", None)}
            payload["version_id"] = str(version_id)
            _import_one(c, kind, payload)
            inserted += 1
        c.commit()
    return inserted


def _import_one(c: sqlite3.Connection, kind: str, row: dict[str, Any]) -> None:
    rid = _new_id()
    now = _now()
    if kind == "labor_rates":
        c.execute("INSERT INTO labor_rates (id,version_id,classification,trade_code,"
                  "rate_type,loaded_rate,effective_date,expiration_date,source_id,created_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (rid, row["version_id"], row["classification"], row["trade_code"],
                   "manual_all_in", row["loaded_rate"], row.get("effective_date"),
                   row.get("expiration_date"), row.get("source_id"), now))
    elif kind == "material_rates":
        c.execute("INSERT INTO material_rates (id,version_id,material_code,description,"
                  "trade_code,purchase_unit,unit_cost,effective_date,source_id,created_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (rid, row["version_id"], row["material_code"], row.get("description"),
                   row["trade_code"], row["purchase_unit"], row["unit_cost"],
                   row.get("effective_date"), row.get("source_id"), now))
    elif kind == "equipment_rates":
        c.execute("INSERT INTO equipment_rates (id,version_id,equipment_code,description,"
                  "basis,base_rate,effective_date,source_id,created_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?)",
                  (rid, row["version_id"], row["equipment_code"], row.get("description"),
                   row["basis"], row["base_rate"], row.get("effective_date"),
                   row.get("source_id"), now))
    elif kind == "production_rates":
        c.execute("INSERT INTO production_rates (id,version_id,production_code,trade_code,"
                  "scope_category,quantity_unit,basis,value,effective_date,source_id,created_at)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (rid, row["version_id"], row["production_code"], row["trade_code"],
                   row.get("scope_category"), row.get("quantity_unit"), row["basis"],
                   row["value"], row.get("effective_date"), row.get("source_id"), now))


def list_inputs(table: str, version_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(f"SELECT * FROM {table} WHERE version_id=? ORDER BY created_at",
                         (str(version_id),)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Assemblies
# ---------------------------------------------------------------------------
def add_assembly(version_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    assert_draft(version_id)
    aid = _new_id()
    with get_connection() as c:
        c.execute(
            "INSERT INTO assemblies (id,version_id,trade_code,assembly_code,name,"
            "description,scope_category,input_unit,output_basis,required_trade_data,"
            "required_evidence_types,required_quantity_basis,assembly_version,active,"
            "notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, str(version_id), data["trade_code"], data["assembly_code"],
             data.get("name"), data.get("description", ""), data.get("scope_category"),
             data.get("input_unit"), data.get("output_basis", "per_input_unit"),
             _dumps(data.get("required_trade_data", [])),
             _dumps(data.get("required_evidence_types", [])),
             _dumps(data.get("required_quantity_basis", [])),
             data.get("assembly_version", "1.0"), 1, data.get("notes", ""), _now()),
        )
        for comp in data.get("components", []):
            c.execute(
                "INSERT INTO assembly_components (id,assembly_id,component_type,"
                "cost_item_ref,quantity_factor,waste_factor,production_ref,crew_ref,"
                "conversion_id,minimum_charge,conditions,sequence,version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_new_id(), aid, comp["component_type"], comp["cost_item_ref"],
                 str(comp.get("quantity_factor", "1")),
                 str(comp["waste_factor"]) if comp.get("waste_factor") is not None else None,
                 comp.get("production_ref"), comp.get("crew_ref"),
                 comp.get("conversion_id"),
                 str(comp["minimum_charge"]) if comp.get("minimum_charge") is not None else None,
                 _dumps(comp.get("conditions", {})), comp.get("sequence", 0), "1.0"),
            )
        c.commit()
    return get_assembly(aid)


def get_assembly(assembly_id: str) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM assemblies WHERE id=?", (assembly_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        comps = c.execute("SELECT * FROM assembly_components WHERE assembly_id=? "
                          "ORDER BY sequence", (assembly_id,)).fetchall()
    data["required_trade_data"] = _loads(data.get("required_trade_data")) or []
    data["components"] = [_component_row(dict(cc)) for cc in comps]
    return data


def _component_row(cc: dict[str, Any]) -> dict[str, Any]:
    cc["conditions"] = _loads(cc.get("conditions")) or {}
    return cc


def list_assemblies(version_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute("SELECT id FROM assemblies WHERE version_id=? ORDER BY assembly_code",
                         (str(version_id),)).fetchall()
    return [get_assembly(r["id"]) for r in rows]


def get_assembly_by_code(version_id: UUID, assembly_code: str) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT id FROM assemblies WHERE version_id=? AND assembly_code=?",
                        (str(version_id), assembly_code)).fetchone()
    return get_assembly(row["id"]) if row else None


# ---------------------------------------------------------------------------
# Scope→assembly mappings
# ---------------------------------------------------------------------------
def upsert_mapping(project_id: UUID, scope_item_id: UUID, data: dict[str, Any]) -> dict:
    now = _now()
    with get_connection() as c:
        existing = c.execute("SELECT id FROM scope_assembly_mappings WHERE scope_item_id=?",
                             (str(scope_item_id),)).fetchone()
        if existing:
            c.execute("UPDATE scope_assembly_mappings SET assembly_code=?,confirmed_by=?,"
                      "confirmed_at=?,priority=? WHERE id=?",
                      (data["assembly_code"], data.get("confirmed_by"), now,
                       data.get("priority", 0), existing["id"]))
            mid = existing["id"]
        else:
            mid = _new_id()
            c.execute("INSERT INTO scope_assembly_mappings (id,project_id,scope_item_id,"
                      "trade_code,scope_category,trade_schema_version,assembly_code,priority,"
                      "confirmed_by,confirmed_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (mid, str(project_id), str(scope_item_id), data.get("trade_code"),
                       data.get("scope_category"), data.get("trade_schema_version"),
                       data["assembly_code"], data.get("priority", 0),
                       data.get("confirmed_by"), now, now))
        c.commit()
        row = c.execute("SELECT * FROM scope_assembly_mappings WHERE id=?", (mid,)).fetchone()
    return dict(row)


def get_mapping(project_id: UUID, scope_item_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute("SELECT * FROM scope_assembly_mappings WHERE project_id=? AND "
                        "scope_item_id=?", (str(project_id), str(scope_item_id))).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Estimates / versions / line items / snapshots / review
# ---------------------------------------------------------------------------
def create_estimate(project_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    eid = _new_id()
    now = _now()
    with get_connection() as c:
        identity = _project_identity(c, project_id)
        c.execute("INSERT INTO estimates (id,project_id,name,description,currency,status,"
                  "created_at,updated_at,tenant_id,company_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (eid, str(project_id), data["name"], data.get("description", ""),
                   data.get("currency", "USD"), "active", now, now,
                   identity["tenant_id"], identity["company_id"]))
        c.commit()
    return get_estimate(project_id, UUID(eid))


def get_estimate(project_id: UUID, estimate_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute(
            """
            SELECT e.*
            FROM estimates e
            JOIN projects p ON p.id = e.project_id
            WHERE e.id=? AND e.project_id=?
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(estimate_id), str(project_id)),
        ).fetchone()
    return dict(row) if row else None


def list_estimates(project_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            """
            SELECT e.*
            FROM estimates e
            JOIN projects p ON p.id = e.project_id
            WHERE e.project_id=?
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            ORDER BY e.created_at DESC
            """,
            (str(project_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def next_version_number(estimate_id: UUID) -> int:
    with get_connection() as c:
        row = c.execute(
            """
            SELECT COALESCE(MAX(ev.version_number),0)
            FROM estimate_versions ev
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE ev.estimate_id=?
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(estimate_id),),
        ).fetchone()
    return int(row[0]) + 1


def create_estimate_version(estimate_id: UUID, project_id: UUID, data: dict[str, Any]) -> dict:
    vid = _new_id()
    with get_connection() as c:
        identity = _assert_estimate_project_identity(c, estimate_id, project_id)
        c.execute(
            "INSERT INTO estimate_versions (id,estimate_id,project_id,version_number,status,"
            "cost_book_version_id,pricing_date,currency,markup_method,inclusions,exclusions,"
            "assumptions,clarifications,config,created_at,tenant_id,company_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, str(estimate_id), str(project_id), data["version_number"], "draft",
             str(data["cost_book_version_id"]), str(data.get("pricing_date")),
             data.get("currency", "USD"), data.get("markup_method", "markup"),
             _dumps(data.get("inclusions", [])), _dumps(data.get("exclusions", [])),
             _dumps(data.get("assumptions", [])), _dumps(data.get("clarifications", [])),
             _dumps(data.get("config", {})), _now(),
             identity["tenant_id"], identity["company_id"]))
        c.execute("UPDATE estimates SET current_version_id=?, updated_at=? WHERE id=? AND project_id=?",
                  (vid, _now(), str(estimate_id), str(project_id)))
        for ind in data.get("indirects", []):
            c.execute(
                "INSERT INTO estimate_indirects (id,version_id,payload,tenant_id,company_id) "
                "VALUES (?,?,?,?,?)",
                (_new_id(), vid, _dumps(ind), identity["tenant_id"], identity["company_id"]),
            )
        for adj in data.get("adjustments", []):
            c.execute(
                "INSERT INTO estimate_adjustments (id,version_id,payload,tenant_id,company_id) "
                "VALUES (?,?,?,?,?)",
                (_new_id(), vid, _dumps(adj), identity["tenant_id"], identity["company_id"]),
            )
        c.commit()
    return get_estimate_version(vid)


def get_estimate_version(version_id: str | UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute(
            """
            SELECT ev.*
            FROM estimate_versions ev
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE ev.id=?
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(version_id),),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("inclusions", "exclusions", "assumptions", "clarifications", "config", "exceptions"):
        d[k] = _loads(d.get(k))
    return d


def list_estimate_versions(estimate_id: UUID) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            """
            SELECT ev.*
            FROM estimate_versions ev
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE ev.estimate_id=?
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            ORDER BY ev.version_number
            """,
            (str(estimate_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def get_indirects(version_id: str) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            """
            SELECT i.payload
            FROM estimate_indirects i
            JOIN estimate_versions ev ON ev.id = i.version_id
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE i.version_id=?
              AND i.tenant_id = ev.tenant_id AND i.company_id = ev.company_id
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(version_id),),
        ).fetchall()
    return [_loads(r["payload"]) for r in rows]


def get_adjustments(version_id: str) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            """
            SELECT a.payload
            FROM estimate_adjustments a
            JOIN estimate_versions ev ON ev.id = a.version_id
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE a.version_id=?
              AND a.tenant_id = ev.tenant_id AND a.company_id = ev.company_id
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(version_id),),
        ).fetchall()
    return [_loads(r["payload"]) for r in rows]


def replace_line_items(version_id: str, project_id: UUID, lines: list[dict]) -> None:
    with get_connection() as c:
        identity = _assert_version_project_identity(c, version_id, project_id)
        c.execute("DELETE FROM estimate_line_items WHERE version_id=?", (str(version_id),))
        for li in lines:
            c.execute(
                "INSERT INTO estimate_line_items (id,version_id,project_id,trade_code,"
                "category_code,scope_item_id,assembly_code,description,location,quantity,"
                "unit,labor_hours,"
                "crew_hours,labor_cost,material_cost,equipment_cost,subcontract_cost,"
                "other_direct_cost,direct_cost_total,status,components,exceptions,evidence,"
                "overrides,created_at,tenant_id,company_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_new_id(), str(version_id), str(project_id), li["trade_code"],
                 li.get("category_code"),
                 li["scope_item_id"], li.get("assembly_code"), li.get("description"),
                 li.get("location"), li.get("quantity"), li.get("unit"),
                 li.get("labor_hours"), li.get("crew_hours"), li.get("labor_cost"),
                 li.get("material_cost"), li.get("equipment_cost"), li.get("subcontract_cost"),
                 li.get("other_direct_cost"), li.get("direct_cost_total"), li.get("status"),
                 _dumps(li.get("components", [])), _dumps(li.get("exceptions", [])),
                 _dumps(li.get("evidence", [])), _dumps(li.get("overrides", [])), _now(),
                 identity["tenant_id"], identity["company_id"]))
        c.commit()


def get_line_items(version_id: str) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            """
            SELECT li.*
            FROM estimate_line_items li
            JOIN estimate_versions ev ON ev.id = li.version_id AND ev.project_id = li.project_id
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE li.version_id=?
              AND li.tenant_id = ev.tenant_id AND li.company_id = ev.company_id
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            ORDER BY li.created_at
            """,
            (str(version_id),),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("components", "exceptions", "evidence", "overrides"):
            d[k] = _loads(d.get(k)) or []
        out.append(d)
    return out


def get_line_item(version_id: str, line_item_id: UUID) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute(
            """
            SELECT li.*
            FROM estimate_line_items li
            JOIN estimate_versions ev ON ev.id = li.version_id AND ev.project_id = li.project_id
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE li.id=? AND li.version_id=?
              AND li.tenant_id = ev.tenant_id AND li.company_id = ev.company_id
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(line_item_id), str(version_id)),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("components", "exceptions", "evidence", "overrides"):
        d[k] = _loads(d.get(k)) or []
    return d


def update_line_item(line_item_id: UUID, fields: dict[str, Any]) -> None:
    for k in ("overrides",):
        if k in fields:
            fields[k] = _dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as c:
        c.execute(f"UPDATE estimate_line_items SET {cols} WHERE id=?",
                  [*fields.values(), str(line_item_id)])
        c.commit()


def save_snapshot(version_id: str, snapshot_json: str, snapshot_hash: str) -> None:
    with get_connection() as c:
        identity = _version_identity(c, version_id)
        c.execute("DELETE FROM estimate_snapshots WHERE version_id=?", (str(version_id),))
        c.execute("INSERT INTO estimate_snapshots (id,version_id,snapshot_json,snapshot_hash,"
                  "created_at,tenant_id,company_id) VALUES (?,?,?,?,?,?,?)",
                  (_new_id(), str(version_id), snapshot_json, snapshot_hash, _now(),
                   identity["tenant_id"], identity["company_id"]))
        c.commit()


def get_snapshot(version_id: str) -> dict[str, Any] | None:
    with get_connection() as c:
        row = c.execute(
            """
            SELECT s.*
            FROM estimate_snapshots s
            JOIN estimate_versions ev ON ev.id = s.version_id
            JOIN estimates e ON e.id = ev.estimate_id AND e.project_id = ev.project_id
            JOIN projects p ON p.id = ev.project_id
            WHERE s.version_id=?
              AND s.tenant_id = ev.tenant_id AND s.company_id = ev.company_id
              AND ev.tenant_id = e.tenant_id AND ev.company_id = e.company_id
              AND e.tenant_id = p.tenant_id AND e.company_id = p.company_id
            """,
            (str(version_id),),
        ).fetchone()
    return dict(row) if row else None


def update_version(version_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    for k in ("exceptions", "config"):
        if k in fields:
            fields[k] = _dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as c:
        c.execute(f"UPDATE estimate_versions SET {cols} WHERE id=?",
                  [*fields.values(), str(version_id)])
        c.commit()
    return get_estimate_version(version_id)


def append_estimate_review(version_id: str, project_id: UUID, event: dict[str, Any]) -> None:
    with get_connection() as c:
        identity = _assert_version_project_identity(c, version_id, project_id)
        c.execute("INSERT INTO estimate_review_events (id,version_id,project_id,action,"
                  "previous_state,new_state,reviewer_id,notes,created_at,tenant_id,company_id) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (_new_id(), str(version_id), str(project_id), event["action"],
                   event.get("previous_state"), event.get("new_state"),
                   event.get("reviewer_id", "system"), event.get("notes"), _now(),
                   identity["tenant_id"], identity["company_id"]))
        c.commit()


# ---------------------------------------------------------------------------
# Snapshot assembly from a published cost-book version
# ---------------------------------------------------------------------------
def build_rate_tables(version_id: UUID) -> dict[str, Any]:
    """Assemble all rate tables for a cost-book version into snapshot dicts."""
    sources = {r["id"]: {"verified": bool(r["verified"]),
                         "effective_date": r["effective_date"],
                         "expiration_date": r["expiration_date"]}
               for r in list_inputs("cost_sources", version_id)}
    labor = {r["classification"]: {"loaded_rate": r["loaded_rate"], "source_id": r["source_id"],
                                   "expiration_date": r["expiration_date"]}
             for r in list_inputs("labor_rates", version_id)}
    crews = {r["crew_code"]: {"loaded_crew_hour_rate": r["loaded_crew_hour_rate"],
                              "members": _loads(r["members"])}
             for r in list_inputs("crews", version_id)}
    production = {r["production_code"]: {"basis": r["basis"], "value": r["value"],
                                         "crew_code": r["crew_code"], "source_id": r["source_id"],
                                         "expiration_date": r["expiration_date"]}
                 for r in list_inputs("production_rates", version_id)}
    material = {r["material_code"]: {"unit_cost": r["unit_cost"], "purchase_unit": r["purchase_unit"],
                                     "coverage_per_unit": r["coverage_per_unit"],
                                     "coverage_unit": r["coverage_unit"],
                                     "taxable": bool(r["taxable"]),
                                     "waste_included": bool(r["waste_included"]),
                                     "freight_included": bool(r["freight_included"]),
                                     "source_id": r["source_id"], "expiration_date": r["expiration_date"]}
                for r in list_inputs("material_rates", version_id)}
    equipment = {r["equipment_code"]: {"basis": r["basis"], "base_rate": r["base_rate"],
                                       "delivery": r["delivery"], "pickup": r["pickup"],
                                       "fuel": r["fuel"],
                                       "operator_included": bool(r["operator_included"]),
                                       "minimum_charge": r["minimum_charge"],
                                       "source_id": r["source_id"], "expiration_date": r["expiration_date"]}
                 for r in list_inputs("equipment_rates", version_id)}
    subcontract = {r["sub_code"]: {"base_amount": r["base_amount"],
                                   "leveling_adjustment": r["leveling_adjustment"],
                                   "verified": bool(r["verified"]), "source_id": r["source_id"]}
                   for r in list_inputs("subcontract_quotes", version_id)}
    other_direct = {r["odc_code"]: {"unit_rate": r["unit_rate"], "taxable": bool(r["taxable"]),
                                    "source_id": r["source_id"]}
                    for r in list_inputs("other_direct_costs", version_id)}
    assemblies = {}
    for asm in list_assemblies(version_id):
        assemblies[asm["assembly_code"]] = {
            "trade_code": asm["trade_code"], "scope_category": asm["scope_category"],
            "input_unit": asm["input_unit"],
            "required_trade_data": asm.get("required_trade_data", []),
            "components": [
                {"component_type": cc["component_type"], "cost_item_ref": cc["cost_item_ref"],
                 "quantity_factor": cc.get("quantity_factor", "1"),
                 "waste_factor": cc.get("waste_factor"), "production_ref": cc.get("production_ref"),
                 "crew_ref": cc.get("crew_ref"), "conversion_id": cc.get("conversion_id"),
                 "minimum_charge": cc.get("minimum_charge"),
                 "conditions": cc.get("conditions", {}), "sequence": cc.get("sequence", 0)}
                for cc in asm.get("components", [])
            ],
        }
    return {"sources": sources, "labor_rates": labor, "crews": crews,
            "production_rates": production, "material_rates": material,
            "equipment_rates": equipment, "subcontract": subcontract,
            "other_direct": other_direct, "assemblies": assemblies}
