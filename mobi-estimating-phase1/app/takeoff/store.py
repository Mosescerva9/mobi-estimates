"""Narrow, additive persistence for canonical takeoff evidence (Milestone 2).

This module is the only writer/reader of the ``canonical_takeoff_evidence``
table (see migration ``_0037``). It deliberately stays thin:

* It serializes a *validated* :class:`~app.takeoff.evidence.CanonicalEvidence`
  into DB row fields and keeps the normalized canonical JSON in ``raw_payload``
  so a row round-trips back into the model without lossy re-mapping.
* It never accepts or stores unknown/unmapped provider payloads. Those are
  quarantined upstream by the provider layer (``app.takeoff.providers``) and
  never become evidence, so they can never reach this store.
* Every read is tenant/company scoped and fails closed on missing identity: a
  list query must name a tenant and company and will never return a row whose
  ``tenant_id``/``company_id`` do not match.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping
from uuid import UUID

from app import database
from app.takeoff.evidence import CanonicalEvidence

CANONICAL_EVIDENCE_TABLE = "canonical_takeoff_evidence"

# Column order used for inserts and for reconstructing rows. ``raw_payload`` holds
# the normalized canonical JSON; the flattened columns exist for querying/indexing.
_COLUMNS: tuple[str, ...] = (
    "evidence_id",
    "schema_version",
    "tenant_id",
    "company_id",
    "project_id",
    "document_id",
    "sheet_id",
    "page_number",
    "region_coordinates",
    "takeoff_provider",
    "provider_record_id",
    "evidence_class",
    "measurement_method",
    "trade",
    "scope_category",
    "description",
    "quantity",
    "unit",
    "confidence",
    "condition",
    "scale",
    "review_status",
    "reviewed_by",
    "extractor_version",
    "raw_payload",
    "created_at",
    "updated_at",
)


def serialize_canonical_evidence(evidence: CanonicalEvidence) -> dict[str, Any]:
    """Flatten a validated ``CanonicalEvidence`` into ``canonical_takeoff_evidence`` fields.

    Uses Pydantic JSON-mode dumping so UUIDs, ``Decimal`` quantities/confidence,
    datetimes, and controlled enum values are all rendered as their stable string
    forms. ``region_coordinates`` is stored as a JSON array (or NULL); the full
    normalized canonical object is preserved in ``raw_payload``.
    """
    payload = evidence.model_dump(mode="json")
    region = payload.get("region_coordinates")
    row: dict[str, Any] = {
        "evidence_id": payload["evidence_id"],
        "schema_version": payload["schema_version"],
        "tenant_id": payload["tenant_id"],
        "company_id": payload["company_id"],
        "project_id": payload["project_id"],
        "document_id": payload["document_id"],
        "sheet_id": payload["sheet_id"],
        "page_number": payload["page_number"],
        "region_coordinates": json.dumps(region) if region is not None else None,
        "takeoff_provider": payload["takeoff_provider"],
        "provider_record_id": payload["provider_record_id"],
        "evidence_class": payload["evidence_class"],
        "measurement_method": payload["measurement_method"],
        "trade": payload["trade"],
        "scope_category": payload["scope_category"],
        "description": payload["description"],
        "quantity": payload["quantity"],
        "unit": payload["unit"],
        "confidence": payload["confidence"],
        "condition": payload["condition"],
        "scale": payload["scale"],
        "review_status": payload["review_status"],
        "reviewed_by": payload["reviewed_by"],
        "extractor_version": payload["extractor_version"],
        "raw_payload": json.dumps(payload, sort_keys=True),
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }
    return row


_IDENTITY_COLUMNS: tuple[str, ...] = (
    "evidence_id",
    "schema_version",
    "tenant_id",
    "company_id",
    "project_id",
    "document_id",
    "sheet_id",
)

# Flattened provenance columns that must match the canonical ``raw_payload``.
# Unlike the identity columns these are optional (nullable), so the comparison is
# null-safe: absent-on-both is fine, but a set-vs-null or set-vs-different value
# means the flattened column diverged from the canonical payload and must fail
# closed (mirrors the DB raw-vs-flattened CHECK constraints).
_PROVENANCE_COLUMNS: tuple[str, ...] = (
    "condition",
    "scale",
)


def _values_diverge(row_value: Any, payload_value: Any) -> bool:
    """Null-safe inequality: both-None is equal; otherwise compare string forms."""
    if row_value is None or payload_value is None:
        return row_value is not payload_value
    return str(row_value) != str(payload_value)


def deserialize_canonical_evidence(row: Mapping[str, Any]) -> CanonicalEvidence:
    """Reconstruct ``CanonicalEvidence`` and verify flattened columns.

    The flattened tenant/company/project columns are what query filters and RLS
    policies use, and the flattened ``condition``/``scale`` provenance columns are
    what downstream reads see without parsing ``raw_payload``. ``raw_payload`` is
    retained for canonical round-trip fidelity, but it must never be allowed to
    smuggle a different identity or provenance than the flattened columns. Any
    mismatch means the row is corrupt or tampered and must fail closed.

    Provenance comparison is null-safe: a NULL flattened value must line up with
    a NULL canonical value, but a value present on only one side (or differing on
    both) is a divergence.
    """
    evidence = CanonicalEvidence.model_validate_json(row["raw_payload"])
    payload = evidence.model_dump(mode="json")
    mismatched = [
        column for column in _IDENTITY_COLUMNS
        if str(row[column]) != str(payload[column])
    ]
    mismatched += [
        column for column in _PROVENANCE_COLUMNS
        if _values_diverge(row.get(column), payload.get(column))
    ]
    if mismatched:
        raise ValueError(
            "canonical evidence raw_payload identity does not match row columns: "
            + ", ".join(mismatched)
        )
    return evidence


def insert_canonical_evidence(
    evidence: CanonicalEvidence, *, conn: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Insert one canonical evidence row, preserving tenant/company/project scope.

    Returns the serialized row that was written. When ``conn`` is provided the
    caller owns the transaction; otherwise a connection is opened and committed.
    """
    row = serialize_canonical_evidence(evidence)
    placeholders = ", ".join("?" for _ in _COLUMNS)
    columns = ", ".join(_COLUMNS)
    sql = (
        f"INSERT INTO {CANONICAL_EVIDENCE_TABLE} ({columns}) VALUES ({placeholders})"
    )
    values = [row[column] for column in _COLUMNS]

    if conn is not None:
        conn.execute(sql, values)
        return row

    with database.get_connection() as owned:
        owned.execute(sql, values)
        owned.commit()
    return row


def list_canonical_evidence_by_project(
    project_id: UUID | str,
    tenant_id: str,
    company_id: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """List canonical evidence for a project within one tenant/company scope.

    Fails closed on missing tenant/company identity and never returns a row whose
    tenant/company do not match the caller's scope.
    """
    if not str(tenant_id).strip() or not str(company_id).strip():
        raise ValueError("tenant_id and company_id are required to list evidence")

    sql = (
        f"SELECT * FROM {CANONICAL_EVIDENCE_TABLE} "
        "WHERE project_id = ? AND tenant_id = ? AND company_id = ? "
        "ORDER BY created_at, evidence_id"
    )
    params = (str(project_id), str(tenant_id), str(company_id))

    if conn is not None:
        rows = conn.execute(sql, params).fetchall()
    else:
        with database.get_connection() as owned:
            rows = owned.execute(sql, params).fetchall()

    return [dict(row) for row in rows]
