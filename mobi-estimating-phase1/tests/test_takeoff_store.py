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
