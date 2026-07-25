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

# Flattened columns that authorization gates, quantity mapping, page identity, or
# provider provenance are decided from WITHOUT parsing ``raw_payload``. Every one
# of them must reproduce the canonical payload exactly or the row is corrupt /
# tampered and must fail closed. Unlike the identity columns several of these are
# nullable, so the comparison is null-safe AND type-strict: absent-on-both is
# fine, but a set-vs-null, a differing value, or a differing *type* (a text "5"
# standing in for an integer 5) is a divergence.
#
# Ordering mirrors the security families the apply path depends on:
#   review status -> evidence class -> measurement method -> provider identity
#   -> quantity mapping -> page identity -> measurement provenance.
_PROVENANCE_COLUMNS: tuple[str, ...] = (
    "review_status",
    "reviewed_by",
    "evidence_class",
    "measurement_method",
    "takeoff_provider",
    "provider_record_id",
    "quantity",
    "unit",
    "confidence",
    "page_number",
    "trade",
    "scope_category",
    "condition",
    "scale",
)


def _values_diverge(row_value: Any, payload_value: Any) -> bool:
    """Null-safe, type-strict inequality.

    Both-None is equal. Otherwise the two values must have the same Python type
    AND compare equal: no truthiness, no ``str()`` coercion, no int/text
    equivalence. A missing key on either side surfaces as ``None`` and therefore
    diverges from any set value.
    """
    if row_value is None or payload_value is None:
        return not (row_value is None and payload_value is None)
    if type(row_value) is not type(payload_value):
        return True
    return row_value != payload_value


# The same columns, regrouped by the JSON scalar type the ORIGINAL ``raw_payload``
# object must carry for them. These groups mirror the v45 CHECK families in
# ``app.migrations`` one-for-one, because the raw JSON is what the DB constrains
# and what a tamperer controls -- not the Pydantic-normalized dump.
#
# ``CanonicalEvidence`` is deliberately lenient at its edges (it coerces "3" into
# ``page_number`` 3 and renders a JSON number ``12.5`` back out as the string
# "12.5"), so comparing the *dumped* model to the flattened columns can be made
# to agree from raw JSON of the wrong scalar type. Checking the parsed JSON
# object first closes that path: the raw value must already be the right JSON
# type before any coercion runs.
_RAW_REQUIRED_STRING_FIELDS: tuple[str, ...] = _IDENTITY_COLUMNS + (
    "review_status",
    "evidence_class",
    "measurement_method",
    "takeoff_provider",
    "provider_record_id",
    "trade",
    "scope_category",
)

# Nullable indexed columns. A NULL column must line up with a JSON null (or, for
# rows written before the key existed, an absent key); a set column must line up
# with a JSON *string* of the same value. ``quantity``/``confidence`` are
# canonically ``Decimal`` rendered as JSON strings, so a JSON *number* here is a
# divergence even when it stringifies to the same digits.
_RAW_NULLABLE_STRING_FIELDS: tuple[str, ...] = (
    "reviewed_by",
    "quantity",
    "unit",
    "confidence",
    "condition",
    "scale",
)

# Integer columns: the canonical value must be a JSON integer, never a numeric
# string and never a JSON boolean (which is an ``int`` subclass in Python).
_RAW_REQUIRED_INTEGER_FIELDS: tuple[str, ...] = ("page_number",)

# Every field the raw-payload guard covers, in one place so tests can assert it
# stays in lockstep with the flattened columns the comparison guards.
_RAW_CHECKED_FIELDS: tuple[str, ...] = (
    _RAW_REQUIRED_STRING_FIELDS
    + _RAW_NULLABLE_STRING_FIELDS
    + _RAW_REQUIRED_INTEGER_FIELDS
)

# Distinguishes "key absent" from "key present and JSON null"; only nullable
# fields may be absent, and only when the flattened column is NULL too.
_RAW_MISSING = object()


def _raw_payload_divergences(
    row: Mapping[str, Any], document: Mapping[str, Any]
) -> list[str]:
    """Compare the ORIGINAL parsed ``raw_payload`` object to the flattened columns.

    Runs before ``CanonicalEvidence`` validation, so nothing here can have been
    normalized: key presence, JSON scalar type, nullability, and value are all
    checked as they were stored. ``type(...) is`` is used rather than
    ``isinstance`` so a JSON boolean cannot pass as an integer.
    """
    diverged: list[str] = []

    for field in _RAW_REQUIRED_STRING_FIELDS:
        raw = document.get(field, _RAW_MISSING)
        if type(raw) is not str or _values_diverge(row.get(field), raw):
            diverged.append(field)

    for field in _RAW_REQUIRED_INTEGER_FIELDS:
        raw = document.get(field, _RAW_MISSING)
        if type(raw) is not int or _values_diverge(row.get(field), raw):
            diverged.append(field)

    for field in _RAW_NULLABLE_STRING_FIELDS:
        raw = document.get(field, _RAW_MISSING)
        row_value = row.get(field)
        if row_value is None:
            # Absent or JSON null are both a legitimate "no value"; anything else
            # is a value the flattened column does not carry.
            if raw is not _RAW_MISSING and raw is not None:
                diverged.append(field)
            continue
        if type(raw) is not str or _values_diverge(row_value, raw):
            diverged.append(field)

    return diverged


def deserialize_canonical_evidence(row: Mapping[str, Any]) -> CanonicalEvidence:
    """Reconstruct ``CanonicalEvidence`` and verify flattened columns.

    The flattened tenant/company/project columns are what query filters and RLS
    policies use, and the flattened review/class/method/provider/quantity/page
    columns are what authorization gates and quantity mapping read without
    parsing ``raw_payload``. ``raw_payload`` is retained for canonical round-trip
    fidelity, but it must never be allowed to smuggle a different identity,
    review state, or measurement than the flattened columns — a rejected raw
    review status behind an approved flattened one, or a non-measurement raw
    class behind a measured flattened one, would otherwise authorize an
    application the canonical record does not support. Any mismatch means the row
    is corrupt or tampered and must fail closed.

    Comparison is null-safe and type-strict: a NULL flattened value must line up
    with a NULL canonical value, and a value present on only one side, differing
    in value, or differing in type is a divergence.

    The comparison runs against the ORIGINAL parsed JSON object *before* the
    payload reaches ``CanonicalEvidence``. Validating first would let the model's
    own lenient coercion manufacture agreement: raw ``"page_number": "3"``
    normalizes to the integer 3 and would then match an indexed ``3``, and a raw
    JSON number ``"quantity": 12.5`` renders back out as the string "12.5" and
    would then match an indexed ``'12.5'``. Both are wrong JSON scalar types that
    the v45 DB CHECKs reject, so the in-process guard must reject them too rather
    than deserializing a payload the database would never have accepted. The
    post-validation comparison is kept as a second pass so canonical
    normalization (UUID/enum/timestamp rendering) still has to agree as well.
    """
    raw_payload = row["raw_payload"]
    try:
        document = json.loads(raw_payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical evidence raw_payload is not valid JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("canonical evidence raw_payload is not a JSON object")

    raw_mismatched = _raw_payload_divergences(row, document)
    if raw_mismatched:
        raise ValueError(
            "canonical evidence raw_payload identity does not match row columns: "
            + ", ".join(raw_mismatched)
        )

    evidence = CanonicalEvidence.model_validate_json(raw_payload)
    payload = evidence.model_dump(mode="json")
    mismatched = [
        column for column in _IDENTITY_COLUMNS
        if _values_diverge(row.get(column), payload.get(column))
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
