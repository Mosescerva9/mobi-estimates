"""Canonical takeoff evidence persistence tests (Milestone 2, slice 2)."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from uuid import uuid4

import pytest

from app import database
from app.config import settings
from app.takeoff import (
    CanonicalEvidence,
    EvidenceClass,
    EvidenceReviewStatus,
    MeasurementMethod,
    MobiNativeTakeoffProvider,
    TakeoffContext,
    TakeoffProviderKind,
    deserialize_canonical_evidence,
    insert_canonical_evidence,
    list_canonical_evidence_by_project,
)


def _evidence(**over) -> CanonicalEvidence:
    data = dict(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        sheet_id=uuid4(),
        page_number=1,
        takeoff_provider=TakeoffProviderKind.MANUAL_IMPORT,
        provider_record_id="rec-1",
        evidence_class=EvidenceClass.MEASURED,
        measurement_method=MeasurementMethod.MANUAL_ENTRY,
        trade="painting",
        scope_category="interior_walls",
        description="Paint walls",
        quantity=Decimal("100"),
        unit="SF",
        confidence=Decimal("0.9"),
        extractor_version="1.0.0",
    )
    data.update(over)
    return CanonicalEvidence(**data)


def _init(tmp_path, monkeypatch, name: str) -> None:
    monkeypatch.setattr(settings, "db_path", tmp_path / name)
    database.init_db()


def _table_names() -> set[str]:
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
def test_local_migration_creates_table_and_indexes(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-migration.db")

    assert "canonical_takeoff_evidence" in _table_names()
    with database.get_connection() as conn:
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(canonical_takeoff_evidence)")
        }
    assert {
        "idx_canonical_evidence_tenant_company_project",
        "idx_canonical_evidence_project",
        "idx_canonical_evidence_document",
        "idx_canonical_evidence_sheet",
    } <= indexes


# ---------------------------------------------------------------------------
# Insert / round-trip
# ---------------------------------------------------------------------------
def test_insert_round_trips_valid_canonical_evidence(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-roundtrip.db")

    ev = _evidence(region_coordinates=(0.0, 0.0, 1.0, 1.0))
    insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(
        ev.project_id, str(ev.tenant_id), str(ev.company_id)
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["evidence_id"] == str(ev.evidence_id)
    assert row["tenant_id"] == str(ev.tenant_id)
    assert row["company_id"] == str(ev.company_id)
    assert row["quantity"] == "100"
    assert row["unit"] == "SF"

    # The normalized canonical JSON reconstructs an identical evidence object.
    restored = deserialize_canonical_evidence(row)
    assert restored == ev


def test_condition_and_scale_round_trip_through_store(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-condition-scale.db")

    ev = _evidence(condition="8ft interior walls", scale='1/4" = 1\'')
    insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(
        ev.project_id, str(ev.tenant_id), str(ev.company_id)
    )
    assert len(rows) == 1
    row = rows[0]
    # Flattened columns carry the values for querying/indexing...
    assert row["condition"] == "8ft interior walls"
    assert row["scale"] == '1/4" = 1\''
    # ...and the canonical object reconstructs them identically.
    restored = deserialize_canonical_evidence(row)
    assert restored == ev
    assert restored.condition == "8ft interior walls"
    assert restored.scale == '1/4" = 1\''


def test_condition_and_scale_default_null_in_store(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-condition-scale-null.db")

    ev = _evidence()
    insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(
        ev.project_id, str(ev.tenant_id), str(ev.company_id)
    )
    assert rows[0]["condition"] is None
    assert rows[0]["scale"] is None


def test_deserialize_rejects_raw_payload_identity_mismatch(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-raw-mismatch.db")

    ev = _evidence()
    row = insert_canonical_evidence(ev)
    tampered = dict(row)
    tampered["tenant_id"] = str(uuid4())

    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(tampered)


def test_db_constraint_rejects_raw_payload_identity_mismatch(tmp_path, monkeypatch):
    """The DB must not allow indexed identity columns to diverge from raw_payload."""
    _init(tmp_path, monkeypatch, "store-raw-check.db")

    from app.takeoff.store import serialize_canonical_evidence

    serialized = serialize_canonical_evidence(_evidence())
    serialized["tenant_id"] = str(uuid4())
    columns = ", ".join(serialized.keys())
    placeholders = ", ".join("?" for _ in serialized)
    with database.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO canonical_takeoff_evidence ({columns}) "
                f"VALUES ({placeholders})",
                list(serialized.values()),
            )
            conn.commit()


def test_db_constraint_rejects_raw_payload_missing_identity_key(tmp_path, monkeypatch):
    """SQLite CHECKs must fail on missing keys, not only wrong non-null values."""
    _init(tmp_path, monkeypatch, "store-raw-missing-key.db")

    from app.takeoff.store import serialize_canonical_evidence

    serialized = serialize_canonical_evidence(_evidence())
    raw_payload = json.loads(serialized["raw_payload"])
    del raw_payload["tenant_id"]
    serialized["raw_payload"] = json.dumps(raw_payload, sort_keys=True)
    columns = ", ".join(serialized.keys())
    placeholders = ", ".join("?" for _ in serialized)
    with database.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO canonical_takeoff_evidence ({columns}) "
                f"VALUES ({placeholders})",
                list(serialized.values()),
            )
            conn.commit()


def test_db_constraint_rejects_raw_payload_non_object(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-raw-non-object.db")

    from app.takeoff.store import serialize_canonical_evidence

    serialized = serialize_canonical_evidence(_evidence())
    serialized["raw_payload"] = json.dumps(["not", "an", "object"])
    columns = ", ".join(serialized.keys())
    placeholders = ", ".join("?" for _ in serialized)
    with database.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO canonical_takeoff_evidence ({columns}) "
                f"VALUES ({placeholders})",
                list(serialized.values()),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Tenant/company/project isolation
# ---------------------------------------------------------------------------
def test_list_filters_by_project_tenant_and_company(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-filter.db")

    tenant = uuid4()
    company = uuid4()
    project = uuid4()

    wanted = _evidence(
        tenant_id=tenant, company_id=company, project_id=project,
        provider_record_id="wanted",
    )
    # Same project + company, different tenant — must be excluded.
    other_tenant = _evidence(
        tenant_id=uuid4(), company_id=company, project_id=project,
        provider_record_id="other-tenant",
    )
    # Same project + tenant, different company — must be excluded.
    other_company = _evidence(
        tenant_id=tenant, company_id=uuid4(), project_id=project,
        provider_record_id="other-company",
    )
    # Same tenant + company, different project — must be excluded.
    other_project = _evidence(
        tenant_id=tenant, company_id=company, project_id=uuid4(),
        provider_record_id="other-project",
    )
    for ev in (wanted, other_tenant, other_company, other_project):
        insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(project, str(tenant), str(company))
    assert [r["provider_record_id"] for r in rows] == ["wanted"]


def test_list_requires_tenant_and_company(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-requires-identity.db")
    project = uuid4()
    with pytest.raises(ValueError, match="tenant_id and company_id are required"):
        list_canonical_evidence_by_project(project, "", str(uuid4()))
    with pytest.raises(ValueError, match="tenant_id and company_id are required"):
        list_canonical_evidence_by_project(project, str(uuid4()), "   ")


# ---------------------------------------------------------------------------
# Review provenance
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "evidence_class",
    [
        EvidenceClass.MODEL_CANDIDATE,
        EvidenceClass.TEST_FIXTURE,
        EvidenceClass.UNSUPPORTED,
    ],
)
def test_non_reviewed_classes_stored_but_not_human_reviewed(
    tmp_path, monkeypatch, evidence_class
):
    _init(tmp_path, monkeypatch, f"store-class-{evidence_class.value}.db")

    ev = _evidence(evidence_class=evidence_class)
    insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(
        ev.project_id, str(ev.tenant_id), str(ev.company_id)
    )
    assert len(rows) == 1
    row = rows[0]
    # Stored as valid evidence, but pending review with no reviewer.
    assert row["evidence_class"] == evidence_class.value
    assert row["review_status"] == EvidenceReviewStatus.PENDING.value
    assert row["reviewed_by"] is None
    assert deserialize_canonical_evidence(row).is_human_reviewed is False


def test_reviewed_by_approval_promotes_to_human_reviewed(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-approved.db")

    ev = _evidence(
        evidence_class=EvidenceClass.MODEL_CANDIDATE,
        review_status=EvidenceReviewStatus.APPROVED,
        reviewed_by="estimator-7",
    )
    insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(
        ev.project_id, str(ev.tenant_id), str(ev.company_id)
    )
    assert rows[0]["review_status"] == "approved"
    assert rows[0]["reviewed_by"] == "estimator-7"
    assert deserialize_canonical_evidence(rows[0]).is_human_reviewed is True


# ---------------------------------------------------------------------------
# Quarantine path never reaches the store
# ---------------------------------------------------------------------------
def test_unknown_payload_quarantines_and_is_not_inserted(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-quarantine.db")

    project = uuid4()
    tenant = uuid4()
    company = uuid4()
    ctx = TakeoffContext(
        tenant_id=tenant,
        company_id=company,
        project_id=project,
        document_id=uuid4(),
        sheet_id=uuid4(),
        extractor_version="1.0.0",
    )
    provider = MobiNativeTakeoffProvider()
    result = provider.normalize_batch(
        [
            dict(
                provider_record_id="good",
                page_number=1,
                trade="painting",
                scope_category="interior_walls",
                description="Paint walls",
                quantity=Decimal("100"),
                unit="SF",
            ),
            # "qty" is not a mapped canonical field — quarantined, never evidence.
            dict(
                provider_record_id="bad",
                page_number=1,
                trade="painting",
                scope_category="interior_walls",
                description="Paint walls",
                qty=5,
            ),
        ],
        context=ctx,
    )
    assert len(result.evidence) == 1
    assert len(result.quarantined) == 1

    # Only validated canonical evidence is ever stored.
    for ev in result.evidence:
        insert_canonical_evidence(ev)

    rows = list_canonical_evidence_by_project(project, str(tenant), str(company))
    assert [r["provider_record_id"] for r in rows] == ["good"]


def test_check_constraint_rejects_unknown_evidence_class(tmp_path, monkeypatch):
    """The DB CHECK is a second fail-closed boundary behind Pydantic validation."""
    _init(tmp_path, monkeypatch, "store-check.db")

    from app.takeoff.store import serialize_canonical_evidence

    serialized = serialize_canonical_evidence(_evidence())
    serialized["evidence_class"] = "totally_made_up"
    columns = ", ".join(serialized.keys())
    placeholders = ", ".join("?" for _ in serialized)
    with database.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO canonical_takeoff_evidence ({columns}) "
                f"VALUES ({placeholders})",
                list(serialized.values()),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Fail-closed raw-vs-flattened provenance (condition / scale)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("column", ["condition", "scale"])
def test_deserialize_rejects_flattened_provenance_divergence(tmp_path, monkeypatch, column):
    """A flattened condition/scale must never diverge from the canonical payload."""
    _init(tmp_path, monkeypatch, f"store-prov-diverge-{column}.db")

    ev = _evidence(condition="8ft interior walls", scale='1/4" = 1\'')
    row = insert_canonical_evidence(ev)

    # raw_payload still says the real value, but the flattened column was tampered.
    tampered = dict(row)
    tampered[column] = "tampered-value"
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(tampered)


@pytest.mark.parametrize("column", ["condition", "scale"])
def test_deserialize_rejects_flattened_present_when_raw_null(tmp_path, monkeypatch, column):
    """Null-safe: a flattened value set while the canonical value is null fails closed."""
    _init(tmp_path, monkeypatch, f"store-prov-present-{column}.db")

    ev = _evidence()  # condition/scale default to None in raw_payload
    row = insert_canonical_evidence(ev)

    tampered = dict(row)
    tampered[column] = "smuggled"
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(tampered)


@pytest.mark.parametrize("column", ["condition", "scale"])
def test_deserialize_rejects_flattened_null_when_raw_present(tmp_path, monkeypatch, column):
    """Null-safe: a flattened NULL while the canonical value is set fails closed."""
    _init(tmp_path, monkeypatch, f"store-prov-null-{column}.db")

    ev = _evidence(condition="8ft interior walls", scale='1/4" = 1\'')
    row = insert_canonical_evidence(ev)

    tampered = dict(row)
    tampered[column] = None
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(tampered)


@pytest.mark.parametrize("column", ["condition", "scale"])
def test_deserialize_accepts_matching_provenance(tmp_path, monkeypatch, column):
    """Both-null and both-equal provenance must round-trip without error."""
    _init(tmp_path, monkeypatch, f"store-prov-ok-{column}.db")

    # Both null.
    null_row = insert_canonical_evidence(_evidence())
    assert deserialize_canonical_evidence(null_row).model_dump()[column] is None

    # Both set and equal.
    set_row = insert_canonical_evidence(
        _evidence(condition="8ft interior walls", scale='1/4" = 1\'')
    )
    assert deserialize_canonical_evidence(set_row) is not None


@pytest.mark.parametrize("column", ["condition", "scale"])
def test_db_constraint_rejects_flattened_provenance_divergence(tmp_path, monkeypatch, column):
    """The DB CHECK is a second fail-closed boundary for condition/scale."""
    _init(tmp_path, monkeypatch, f"store-prov-check-{column}.db")

    from app.takeoff.store import serialize_canonical_evidence

    serialized = serialize_canonical_evidence(
        _evidence(condition="8ft interior walls", scale='1/4" = 1\'')
    )
    serialized[column] = "tampered-value"
    columns = ", ".join(serialized.keys())
    placeholders = ", ".join("?" for _ in serialized)
    with database.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO canonical_takeoff_evidence ({columns}) "
                f"VALUES ({placeholders})",
                list(serialized.values()),
            )
            conn.commit()


@pytest.mark.parametrize("column", ["condition", "scale"])
def test_db_constraint_rejects_flattened_provenance_present_when_raw_null(
    tmp_path, monkeypatch, column
):
    """DB CHECK is null-safe: flattened value set while raw payload is null fails."""
    _init(tmp_path, monkeypatch, f"store-prov-check-null-{column}.db")

    from app.takeoff.store import serialize_canonical_evidence

    serialized = serialize_canonical_evidence(_evidence())
    serialized[column] = "smuggled"
    columns = ", ".join(serialized.keys())
    placeholders = ", ".join("?" for _ in serialized)
    with database.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO canonical_takeoff_evidence ({columns}) "
                f"VALUES ({placeholders})",
                list(serialized.values()),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Raw JSON scalar types are checked BEFORE Pydantic can coerce them
#
# ``CanonicalEvidence`` is lenient at its edges: it parses "3" into an int
# ``page_number`` and renders a JSON number ``12.5`` back out as the Decimal
# string "12.5". Comparing the *validated* model against the flattened columns
# therefore lets raw JSON of the wrong scalar type manufacture agreement. The
# guard must read the original parsed JSON object instead.
# ---------------------------------------------------------------------------
_DROP = object()


def _retamper(row: dict, **raw_fields) -> dict:
    """Copy ``row`` with ``raw_payload`` keys replaced (or dropped via ``_DROP``)."""
    tampered = dict(row)
    payload = json.loads(tampered["raw_payload"])
    for key, value in raw_fields.items():
        if value is _DROP:
            payload.pop(key, None)
        else:
            payload[key] = value
    tampered["raw_payload"] = json.dumps(payload, sort_keys=True)
    return tampered


def test_deserialize_rejects_raw_page_number_as_string(tmp_path, monkeypatch):
    """Codex case 1: raw "3" would coerce to int 3 and match the indexed 3."""
    _init(tmp_path, monkeypatch, "store-raw-page-string.db")

    row = insert_canonical_evidence(_evidence(page_number=3))
    assert row["page_number"] == 3

    tampered = _retamper(row, page_number="3")
    # Proof the coercion path is real: Pydantic happily normalizes it to int 3,
    # so the post-validation comparison alone would have found no divergence.
    assert CanonicalEvidence.model_validate_json(
        tampered["raw_payload"]
    ).page_number == 3

    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(tampered)


def test_deserialize_rejects_raw_quantity_as_json_number(tmp_path, monkeypatch):
    """Codex case 2: raw 12.5 renders back as "12.5" and matches the indexed text."""
    _init(tmp_path, monkeypatch, "store-raw-qty-number.db")

    row = insert_canonical_evidence(_evidence(quantity=Decimal("12.5")))
    assert row["quantity"] == "12.5"

    tampered = _retamper(row, quantity=12.5)
    # Same proof: the validated model dumps back to the exact indexed string.
    assert CanonicalEvidence.model_validate_json(
        tampered["raw_payload"]
    ).model_dump(mode="json")["quantity"] == "12.5"

    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(tampered)


def test_deserialize_rejects_raw_confidence_as_json_number(tmp_path, monkeypatch):
    """The same Decimal-as-number coercion on the other Decimal field."""
    _init(tmp_path, monkeypatch, "store-raw-conf-number.db")

    row = insert_canonical_evidence(_evidence(confidence=Decimal("0.5")))
    assert row["confidence"] == "0.5"

    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(_retamper(row, confidence=0.5))


@pytest.mark.parametrize(
    "field, raw_value",
    [
        # Booleans are an ``int`` subclass, so a bare isinstance check would let
        # ``true`` stand in for the indexed page number 1.
        ("page_number", True),
        ("review_status", True),
        ("provider_record_id", False),
        ("trade", 0),
        ("scope_category", 1.5),
        ("evidence_class", ["measured"]),
        ("measurement_method", {"value": "manual_entry"}),
        ("tenant_id", 12345),
        ("page_number", 1.0),
    ],
)
def test_deserialize_rejects_wrong_raw_scalar_type(
    tmp_path, monkeypatch, field, raw_value
):
    """Every required mirrored field must carry its exact JSON scalar type."""
    _init(tmp_path, monkeypatch, "store-raw-wrong-type.db")

    row = insert_canonical_evidence(_evidence(page_number=1))
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(_retamper(row, **{field: raw_value}))


@pytest.mark.parametrize(
    "field",
    [
        "evidence_id", "schema_version", "tenant_id", "company_id", "project_id",
        "document_id", "sheet_id", "page_number", "review_status",
        "evidence_class", "measurement_method", "takeoff_provider",
        "provider_record_id", "trade", "scope_category",
    ],
)
def test_deserialize_rejects_missing_required_raw_key(tmp_path, monkeypatch, field):
    """A required mirrored key must be present in the raw object, not defaulted in."""
    _init(tmp_path, monkeypatch, "store-raw-missing-key.db")

    row = insert_canonical_evidence(_evidence())
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(_retamper(row, **{field: _DROP}))


@pytest.mark.parametrize(
    "field",
    ["page_number", "review_status", "trade", "tenant_id", "quantity", "unit",
     "confidence"],
)
def test_deserialize_rejects_raw_null_under_non_null_column(
    tmp_path, monkeypatch, field
):
    """JSON null can never hide behind a non-NULL indexed value."""
    _init(tmp_path, monkeypatch, "store-raw-null-under-value.db")

    row = insert_canonical_evidence(_evidence())
    assert row[field] is not None
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(_retamper(row, **{field: None}))


@pytest.mark.parametrize(
    "field, raw_value",
    [
        ("condition", "smuggled"),
        ("scale", '1/4" = 1\''),
        ("reviewed_by", "auditor@example.com"),
        ("condition", 0),
        ("scale", False),
        ("reviewed_by", ["auditor"]),
    ],
)
def test_deserialize_rejects_raw_value_under_null_column(
    tmp_path, monkeypatch, field, raw_value
):
    """A nullable indexed NULL must not carry any raw value at all."""
    _init(tmp_path, monkeypatch, "store-raw-value-under-null.db")

    row = insert_canonical_evidence(_evidence())  # condition/scale/reviewed_by NULL
    assert row[field] is None
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(_retamper(row, **{field: raw_value}))


@pytest.mark.parametrize(
    "field, raw_value",
    [
        ("review_status", "approved"),
        ("evidence_class", "model_candidate"),
        ("measurement_method", "model_inference"),
        ("takeoff_provider", "human_verified"),
        ("provider_record_id", "rec-other"),
        ("trade", "electrical"),
        ("scope_category", "exterior_walls"),
        ("page_number", 99),
        ("quantity", "999"),
        ("unit", "LF"),
    ],
)
def test_deserialize_rejects_raw_value_mismatch_with_correct_type(
    tmp_path, monkeypatch, field, raw_value
):
    """Right JSON type, wrong value: still a divergence from the indexed column."""
    _init(tmp_path, monkeypatch, "store-raw-value-mismatch.db")

    row = insert_canonical_evidence(_evidence())
    assert row[field] != raw_value
    with pytest.raises(ValueError, match="raw_payload identity does not match"):
        deserialize_canonical_evidence(_retamper(row, **{field: raw_value}))


@pytest.mark.parametrize(
    "raw_payload",
    ['["not", "an", "object"]', '"a string"', "42", "null", "true"],
)
def test_deserialize_rejects_non_object_raw_payload(tmp_path, monkeypatch, raw_payload):
    _init(tmp_path, monkeypatch, "store-raw-non-object-guard.db")

    row = dict(insert_canonical_evidence(_evidence()))
    row["raw_payload"] = raw_payload
    with pytest.raises(ValueError, match="raw_payload is not a JSON object"):
        deserialize_canonical_evidence(row)


def test_deserialize_rejects_unparseable_raw_payload(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch, "store-raw-invalid-json.db")

    row = dict(insert_canonical_evidence(_evidence()))
    row["raw_payload"] = "{not json"
    with pytest.raises(ValueError, match="raw_payload is not valid JSON"):
        deserialize_canonical_evidence(row)


def test_deserialize_accepts_absent_nullable_keys(tmp_path, monkeypatch):
    """Legitimate optional fields stay legitimate: absent == NULL, like the DB CHECK."""
    _init(tmp_path, monkeypatch, "store-raw-absent-nullable.db")

    row = insert_canonical_evidence(
        _evidence(quantity=None, unit=None, confidence=None)
    )
    for field in ("reviewed_by", "condition", "scale", "quantity", "unit", "confidence"):
        assert row[field] is None

    absent = _retamper(
        row,
        reviewed_by=_DROP, condition=_DROP, scale=_DROP,
        quantity=_DROP, unit=_DROP, confidence=_DROP,
    )
    restored = deserialize_canonical_evidence(absent)
    assert restored.quantity is None
    assert restored.condition is None
    assert restored.reviewed_by is None


def test_deserialize_preserves_decimal_and_timestamp_semantics(tmp_path, monkeypatch):
    """Exact Decimal digits and canonical timestamp strings survive the guard."""
    _init(tmp_path, monkeypatch, "store-raw-decimal-timestamp.db")

    ev = _evidence(
        quantity=Decimal("100.50"),
        confidence=Decimal("0.875"),
        reviewed_by="auditor@example.com",
        review_status=EvidenceReviewStatus.APPROVED,
        condition="8ft interior walls",
        scale='1/4" = 1\'',
    )
    row = insert_canonical_evidence(ev)
    # Trailing zero preserved, not normalized to "100.5".
    assert row["quantity"] == "100.50"
    assert row["confidence"] == "0.875"

    restored = deserialize_canonical_evidence(row)
    assert restored == ev
    assert restored.quantity == Decimal("100.50")
    assert str(restored.quantity) == "100.50"
    assert restored.created_at == ev.created_at
    assert restored.updated_at == ev.updated_at
    assert restored.is_human_reviewed is True


def test_raw_guard_covers_every_compared_flattened_column():
    """The raw-JSON guard must not fall behind the columns the row guard compares."""
    from app.takeoff import store as store_module

    compared = set(store_module._IDENTITY_COLUMNS) | set(
        store_module._PROVENANCE_COLUMNS
    )
    checked = set(store_module._RAW_CHECKED_FIELDS)
    assert checked == compared
    # And the groups must not overlap, or a field would be checked under two
    # contradictory JSON-type rules.
    assert len(store_module._RAW_CHECKED_FIELDS) == len(checked)
