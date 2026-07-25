"""Tests for applying canonical takeoff evidence to a scope item.

Covers the previously-missing bridge between the OpenTakeoff worker (which
persists ``canonical_takeoff_evidence`` rows pending review) and scope
approval (which only trusts ``evidence_references``). All IDs are generated
fresh per test; the controlled-transaction IDs mentioned in the task are never
hardcoded here.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.database import get_connection
from app.takeoff.evidence import (
    EvidenceClass,
    EvidenceReviewStatus,
    MeasurementMethod,
    TakeoffProviderKind,
    CanonicalEvidence,
)
from app.takeoff.evidence_apply import (
    ALLOWED_EVIDENCE_REVIEW_STATUSES,
    MEASUREMENT_METHOD_QUANTITY_BASIS,
    REQUIRED_EVIDENCE_CLASS,
    _canonical_row_divergences,
    _require_row_matches_canonical,
)
from app.takeoff.store import (
    deserialize_canonical_evidence,
    insert_canonical_evidence,
    serialize_canonical_evidence,
)
from app.takeoff.worker_api import WorkerApiError
from tests.conftest import make_trade_pdf


def _headers(tenant_id: str, company_id: str, *, role: str | None = "estimator", actor_id: str = "staff-1") -> dict[str, str]:
    headers = {"X-Mobi-Tenant-Id": tenant_id, "X-Mobi-Company-Id": company_id}
    if role is not None:
        headers["X-Mobi-Actor-Role"] = role
    headers["X-Mobi-Actor-Id"] = actor_id
    return headers


def _prepare_verified_project(client, tenant_id: str, company_id: str) -> tuple[str, dict[str, str]]:
    headers = _headers(tenant_id, company_id)
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "Evidence Apply"},
        files={"plan": ("plans.pdf", make_trade_pdf(), "application/pdf")},
        headers=headers,
    ).json()["project_id"]
    client.post(f"/api/v1/projects/{pid}/process", headers=headers)
    sheets = client.get(f"/api/v1/projects/{pid}/sheets", headers=headers).json()["items"]
    sheet_ids = {}
    for sheet in sheets:
        number = "A-101" if sheet["pdf_page_number"] == 1 else "S-101"
        client.patch(
            f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
            json={"verified_sheet_number": number, "review_status": "verified"},
            headers=headers,
        )
        sheet_ids[sheet["pdf_page_number"]] = sheet["sheet_id"]
    return pid, sheet_ids


def _insert_blocked_scope_item(pid: str, *, tenant_id: str, company_id: str) -> str:
    item_id = str(uuid4())
    run_id = str(uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'general_trade', 'completed', 'test', 1, 't', 't', ?, ?)",
            (run_id, pid, tenant_id, company_id),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "review_status, conflict_status, blocking_issues, quantity_basis, trade_data, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'general_trade', 'test', 'test', 'customer_revision_rescope', "
            "'Accepted customer revision requires rescope.', 'blocked', 'blocking', ?, 'unknown', '{}', "
            "'t', 't', ?, ?)",
            (
                item_id, pid, run_id,
                json.dumps([{"code": "customer_revision_rescope_required"}]),
                tenant_id, company_id,
            ),
        )
        conn.commit()
    return item_id


def _make_evidence(
    *, tenant_id: str, company_id: str, project_id: str, sheet_id: str, page_number: int = 1,
    quantity: Decimal | None = Decimal("4"), unit: str | None = "EA",
    provider: str = TakeoffProviderKind.OPEN_TAKEOFF.value,
    method: str = MeasurementMethod.STAFF_MARKER_TALLY.value,
    evidence_class: str = EvidenceClass.MEASURED.value,
    review_status: str = EvidenceReviewStatus.PENDING.value,
) -> CanonicalEvidence:
    return CanonicalEvidence(
        tenant_id=tenant_id, company_id=company_id, project_id=project_id,
        document_id=project_id, sheet_id=sheet_id, page_number=page_number,
        takeoff_provider=provider, provider_record_id="marker-1",
        evidence_class=evidence_class, measurement_method=method,
        trade="general_trade", scope_category="customer_revision_rescope",
        description="4 EA counted on verified sheet",
        quantity=quantity, unit=unit, confidence=Decimal("0.9"),
        review_status=review_status, extractor_version="test-fixture-v1",
    )


def _apply_url(pid: str, item_id: str, evidence_id: str) -> str:
    return f"/api/v1/projects/{pid}/scope-items/{item_id}/takeoff-evidence/{evidence_id}/apply"


def _counts(pid: str, item_id: str, evidence_id: str) -> dict[str, int]:
    with get_connection() as conn:
        refs = conn.execute(
            "SELECT COUNT(*) FROM evidence_references WHERE scope_item_id=?", (item_id,)
        ).fetchone()[0]
        events = conn.execute(
            "SELECT COUNT(*) FROM review_events WHERE scope_item_id=? AND action='takeoff_evidence_applied'",
            (item_id,),
        ).fetchone()[0]
        links = conn.execute(
            "SELECT COUNT(*) FROM canonical_evidence_scope_links WHERE evidence_id=?", (evidence_id,)
        ).fetchone()[0]
    return {"evidence_references": refs, "review_events": events, "links": links}


@pytest.fixture()
def scenario(client):
    tenant_id, company_id = str(uuid4()), str(uuid4())
    pid, sheet_ids = _prepare_verified_project(client, tenant_id, company_id)
    item_id = _insert_blocked_scope_item(pid, tenant_id=tenant_id, company_id=company_id)
    return {
        "client": client, "tenant_id": tenant_id, "company_id": company_id,
        "pid": pid, "sheet_ids": sheet_ids, "item_id": item_id,
    }


def test_happy_path_applies_count_evidence_and_preserves_workflow_blocker(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={"reviewer_id": "estimator_bob", "reviewer_notes": "Applied count from A-101."},
        headers=_headers(scenario["tenant_id"], scenario["company_id"], actor_id="estimator_bob"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["applied"] is True
    assert body["idempotent"] is False
    assert body["evidence_review_status"] == "approved"
    scope_item = body["scope_item"]
    assert scope_item["quantity"] == "4"
    assert scope_item["unit"] == "EA"
    assert scope_item["quantity_basis"] == "drawing_count"
    assert scope_item["review_status"] == "blocked"
    codes = {issue["code"] for issue in scope_item["blocking_issues"]}
    assert "customer_revision_rescope_required" in codes
    assert body["provenance"]["verified_sheet_number"] == "A-101"
    assert body["provenance"]["page_number"] == 1
    assert body["provenance"]["measurement_method"] == "staff_marker_tally"

    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts == {"evidence_references": 1, "review_events": 1, "links": 1}

    with get_connection() as conn:
        row = conn.execute(
            "SELECT review_status, reviewed_by FROM canonical_takeoff_evidence WHERE evidence_id=?",
            (str(evidence.evidence_id),),
        ).fetchone()
    assert row["review_status"] == "approved"
    assert row["reviewed_by"] == "estimator_bob"

    readiness = client.get(
        f"/api/v1/projects/{pid}/estimate-readiness", headers=_headers(scenario["tenant_id"], scenario["company_id"])
    ).json()
    assert readiness["status"] == "blocked"


def test_digital_measurement_maps_to_explicit_plan_quantity(scenario):
    """The other half of MEASUREMENT_METHOD_QUANTITY_BASIS.

    A native digital line/polygon measurement is a value read directly off the
    verified drawing, so it must stamp ``explicit_plan_quantity`` -- NOT the
    ``drawing_count`` a staff marker tally produces. The mapping is derived from
    the stored evidence's measurement_method, never from client input.
    """
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
        method=MeasurementMethod.DIGITAL_MEASUREMENT.value,
        quantity=Decimal("128.5"), unit="LF",
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={"reviewer_id": "estimator_bob"},
        headers=_headers(scenario["tenant_id"], scenario["company_id"], actor_id="estimator_bob"),
    )
    assert resp.status_code == 200, resp.text
    scope_item = resp.json()["scope_item"]
    assert scope_item["quantity_basis"] == "explicit_plan_quantity"
    assert scope_item["quantity"] == "128.5"
    assert scope_item["unit"] == "LF"
    assert resp.json()["provenance"]["measurement_method"] == "digital_measurement"

    # The basis is persisted, not just reported.
    with get_connection() as conn:
        row = conn.execute(
            "SELECT quantity_basis, raw_quantity_inputs FROM scope_items WHERE id=?", (item_id,)
        ).fetchone()
    assert row["quantity_basis"] == "explicit_plan_quantity"
    assert json.loads(row["raw_quantity_inputs"])["measurement_method"] == "digital_measurement"

    # Applying a measured quantity still never unlocks the workflow blocker.
    codes = {issue["code"] for issue in scope_item["blocking_issues"]}
    assert "customer_revision_rescope_required" in codes
    assert scope_item["review_status"] == "blocked"


def test_idempotent_retry_creates_no_duplicates(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)
    headers = _headers(scenario["tenant_id"], scenario["company_id"], actor_id="estimator_bob")
    url = _apply_url(pid, item_id, str(evidence.evidence_id))

    first = client.post(url, json={"reviewer_id": "estimator_bob"}, headers=headers)
    assert first.status_code == 200
    second = client.post(url, json={"reviewer_id": "estimator_bob"}, headers=headers)
    assert second.status_code == 200
    assert second.json()["idempotent"] is True
    assert second.json()["evidence_reference_id"] == first.json()["evidence_reference_id"]

    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts == {"evidence_references": 1, "review_events": 1, "links": 1}


def test_same_evidence_to_different_scope_item_is_conflict(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    other_item_id = _insert_blocked_scope_item(pid, tenant_id=scenario["tenant_id"], company_id=scenario["company_id"])
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)
    headers = _headers(scenario["tenant_id"], scenario["company_id"])

    first = client.post(_apply_url(pid, item_id, str(evidence.evidence_id)), json={}, headers=headers)
    assert first.status_code == 200

    second = client.post(_apply_url(pid, other_item_id, str(evidence.evidence_id)), json={}, headers=headers)
    assert second.status_code == 409

    counts = _counts(pid, other_item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


def test_cross_project_evidence_is_denied(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    other_pid, other_sheets = _prepare_verified_project(client, scenario["tenant_id"], scenario["company_id"])
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=other_pid, sheet_id=other_sheets[1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(scenario["tenant_id"], scenario["company_id"]),
    )
    assert resp.status_code == 403
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


def test_cross_tenant_request_is_denied(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(str(uuid4()), str(uuid4())),
    )
    assert resp.status_code == 403
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


def test_customer_actor_is_denied(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(scenario["tenant_id"], scenario["company_id"], role="customer"),
    )
    assert resp.status_code == 403
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


def test_wrong_page_is_denied(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1], page_number=2,
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(scenario["tenant_id"], scenario["company_id"]),
    )
    assert resp.status_code == 422
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


def test_unverified_sheet_is_denied(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    unverified_sheet_id = str(uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "review_status, requires_review, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 99, 98, 'pending', 1, 't', 't', ?, ?)",
            (unverified_sheet_id, pid, scenario["tenant_id"], scenario["company_id"]),
        )
        conn.commit()
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=unverified_sheet_id, page_number=99,
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(scenario["tenant_id"], scenario["company_id"]),
    )
    assert resp.status_code == 422
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


def test_rejected_evidence_is_denied(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
        review_status=EvidenceReviewStatus.REJECTED.value,
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(scenario["tenant_id"], scenario["company_id"]),
    )
    assert resp.status_code == 422
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts["evidence_references"] == 0


@pytest.mark.parametrize(
    "overrides,expected_code",
    [
        ({"quantity": Decimal("0")}, "invalid_quantity"),
        ({"quantity": None}, "invalid_quantity"),
        ({"unit": None}, "invalid_unit"),
        ({"provider": TakeoffProviderKind.CUSTOMER_SUPPLIED.value}, "unsupported_provider"),
        ({"method": MeasurementMethod.MODEL_INFERENCE.value}, "unsupported_measurement_method"),
        ({"evidence_class": EvidenceClass.MODEL_CANDIDATE.value}, "unsupported_evidence_class"),
    ],
)
def test_invalid_evidence_denied_before_mutation(scenario, overrides, expected_code):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1], **overrides,
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={}, headers=_headers(scenario["tenant_id"], scenario["company_id"]),
    )
    assert resp.status_code == 422, resp.text
    assert expected_code in resp.json()["error"]["message"]
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts == {"evidence_references": 0, "review_events": 0, "links": 0}

    with get_connection() as conn:
        scope_row = conn.execute(
            "SELECT quantity, review_status FROM scope_items WHERE id=?", (item_id,)
        ).fetchone()
    assert scope_row["quantity"] is None
    assert scope_row["review_status"] == "blocked"


# ---------------------------------------------------------------------------
# Reviewer identity: the persisted reviewer is the authenticated actor, never
# a body field. A body ``reviewer_id`` naming anyone else is an impersonation
# attempt and is rejected outright.
# ---------------------------------------------------------------------------
def test_body_reviewer_id_cannot_impersonate_another_actor(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={"reviewer_id": "owner_moses", "reviewer_notes": "not mine to sign"},
        headers=_headers(scenario["tenant_id"], scenario["company_id"], actor_id="estimator_bob"),
    )
    assert resp.status_code == 403, resp.text
    assert "reviewer_identity_mismatch" in resp.text

    # Nothing was written, and the evidence is still unreviewed.
    counts = _counts(pid, item_id, str(evidence.evidence_id))
    assert counts == {"evidence_references": 0, "review_events": 0, "links": 0}
    with get_connection() as conn:
        row = conn.execute(
            "SELECT review_status, reviewed_by FROM canonical_takeoff_evidence WHERE evidence_id=?",
            (str(evidence.evidence_id),),
        ).fetchone()
    assert row["review_status"] == "pending"
    assert row["reviewed_by"] is None


def test_matching_body_reviewer_id_is_accepted_and_actor_is_the_authority(scenario):
    """A body reviewer_id equal to the actor is allowed (compat), and the
    persisted reviewer/applier identity is the authenticated actor either way."""
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={"reviewer_id": "estimator_bob"},
        headers=_headers(scenario["tenant_id"], scenario["company_id"], actor_id="estimator_bob"),
    )
    assert resp.status_code == 200, resp.text

    with get_connection() as conn:
        evidence_row = conn.execute(
            "SELECT reviewed_by, raw_payload FROM canonical_takeoff_evidence WHERE evidence_id=?",
            (str(evidence.evidence_id),),
        ).fetchone()
        link = conn.execute(
            "SELECT applied_by FROM canonical_evidence_scope_links WHERE evidence_id=?",
            (str(evidence.evidence_id),),
        ).fetchone()
        event = conn.execute(
            "SELECT reviewer_id FROM review_events WHERE scope_item_id=? AND action='takeoff_evidence_applied'",
            (item_id,),
        ).fetchone()
    assert evidence_row["reviewed_by"] == "estimator_bob"
    assert json.loads(evidence_row["raw_payload"])["reviewed_by"] == "estimator_bob"
    assert link["applied_by"] == "estimator_bob"
    assert event["reviewer_id"] == "estimator_bob"


def test_omitted_body_reviewer_id_defaults_to_the_authenticated_actor(scenario):
    client = scenario["client"]
    pid, item_id = scenario["pid"], scenario["item_id"]
    evidence = _make_evidence(
        tenant_id=scenario["tenant_id"], company_id=scenario["company_id"],
        project_id=pid, sheet_id=scenario["sheet_ids"][1],
    )
    insert_canonical_evidence(evidence)

    resp = client.post(
        _apply_url(pid, item_id, str(evidence.evidence_id)),
        json={},
        headers=_headers(scenario["tenant_id"], scenario["company_id"], actor_id="estimator_ann"),
    )
    assert resp.status_code == 200, resp.text
    with get_connection() as conn:
        row = conn.execute(
            "SELECT reviewed_by FROM canonical_takeoff_evidence WHERE evidence_id=?",
            (str(evidence.evidence_id),),
        ).fetchone()
    assert row["reviewed_by"] == "estimator_ann"


# ---------------------------------------------------------------------------
# Raw/indexed canonical-evidence divergence: a flattened column that disagrees
# with raw_payload must fail closed in EVERY security-relevant field family.
# ---------------------------------------------------------------------------
def _canonical_row(*, condition=None, scale=None, reviewed_by=None, **over) -> tuple[dict, CanonicalEvidence]:
    """A serialized canonical row plus its canonical model, ready to be skewed."""
    evidence = _make_evidence(
        tenant_id=str(uuid4()), company_id=str(uuid4()), project_id=str(uuid4()),
        sheet_id=str(uuid4()), **over,
    )
    evidence = evidence.model_copy(
        update={"condition": condition, "scale": scale, "reviewed_by": reviewed_by}
    )
    return serialize_canonical_evidence(evidence), evidence


@pytest.mark.parametrize(
    "column, tampered_value",
    [
        # Review/authorization family.
        ("review_status", EvidenceReviewStatus.APPROVED.value),
        ("reviewed_by", "owner_moses"),
        # Class / measurement-method family (drives the QuantityBasis mapping).
        ("evidence_class", EvidenceClass.MEASURED.value),
        ("measurement_method", MeasurementMethod.STAFF_MARKER_TALLY.value),
        # Provider identity family.
        ("takeoff_provider", TakeoffProviderKind.MOBI_NATIVE.value),
        ("provider_record_id", "marker-999"),
        # Quantity-mapping family.
        ("quantity", "9999"),
        ("unit", "LF"),
        ("confidence", "0.1"),
        # Page / document identity family.
        ("page_number", 99),
        ("sheet_id", "00000000-0000-4000-8000-00000000dead"),
        ("document_id", "00000000-0000-4000-8000-00000000beef"),
        # Scope family.
        ("trade", "electrical"),
        ("scope_category", "other"),
        # Measurement-provenance family.
        ("condition", "tampered condition"),
        ("scale", '1/8" = 1\''),
    ],
)
def test_flattened_column_divergence_fails_closed(column, tampered_value):
    row, evidence = _canonical_row(
        review_status=EvidenceReviewStatus.REJECTED.value,
        evidence_class=EvidenceClass.MODEL_CANDIDATE.value,
        method=MeasurementMethod.MODEL_INFERENCE.value,
        provider=TakeoffProviderKind.CUSTOMER_SUPPLIED.value,
    )
    row[column] = tampered_value

    divergent = _canonical_row_divergences(row, evidence.model_dump(mode="json"))
    assert any(name.endswith(f".{column}") for name in divergent), divergent
    with pytest.raises(WorkerApiError) as excinfo:
        _require_row_matches_canonical(row, evidence)
    assert excinfo.value.code == "evidence_corrupt"
    # The store-level loader rejects the same row.
    with pytest.raises(ValueError):
        deserialize_canonical_evidence(row)


def test_rejected_raw_review_status_behind_approved_column_fails_closed():
    """The exact escalation: raw says REJECTED, the indexed column says APPROVED.

    Without a raw-vs-flattened check the apply gate would read the column, see an
    allowed status, and apply evidence a reviewer explicitly rejected.
    """
    row, evidence = _canonical_row(review_status=EvidenceReviewStatus.REJECTED.value)
    row["review_status"] = EvidenceReviewStatus.APPROVED.value

    assert evidence.review_status == EvidenceReviewStatus.REJECTED.value
    assert row["review_status"] in ALLOWED_EVIDENCE_REVIEW_STATUSES
    with pytest.raises(WorkerApiError) as excinfo:
        _require_row_matches_canonical(row, evidence)
    assert excinfo.value.http_status == 500
    assert excinfo.value.code == "evidence_corrupt"


def test_non_measurement_raw_class_and_method_behind_measured_columns_fails_closed():
    """Raw is a model inference / model candidate; the columns claim a measured
    staff marker tally, which would both authorize the apply and pick
    ``drawing_count`` as the QuantityBasis."""
    row, evidence = _canonical_row(
        evidence_class=EvidenceClass.MODEL_CANDIDATE.value,
        method=MeasurementMethod.MODEL_INFERENCE.value,
    )
    row["evidence_class"] = EvidenceClass.MEASURED.value
    row["measurement_method"] = MeasurementMethod.STAFF_MARKER_TALLY.value

    assert row["evidence_class"] == REQUIRED_EVIDENCE_CLASS
    assert row["measurement_method"] in MEASUREMENT_METHOD_QUANTITY_BASIS
    divergent = _canonical_row_divergences(row, evidence.model_dump(mode="json"))
    assert {"class_and_method.evidence_class", "class_and_method.measurement_method"} <= set(divergent)
    with pytest.raises(WorkerApiError):
        _require_row_matches_canonical(row, evidence)


@pytest.mark.parametrize(
    "column, tampered_value",
    [
        ("condition", None),            # canonical set, column NULL
        ("scale", None),
        ("reviewed_by", None),
        ("quantity", None),
        ("unit", None),
        ("confidence", None),
    ],
)
def test_null_flattened_value_against_a_set_canonical_value_fails_closed(column, tampered_value):
    # Every compared column carries a value, so nulling any one of them is a
    # real divergence rather than a no-op.
    row, evidence = _canonical_row(
        condition="8ft interior walls", scale='1/4" = 1\'', reviewed_by="estimator_bob",
    )
    assert row[column] is not None
    row[column] = tampered_value

    with pytest.raises(WorkerApiError):
        _require_row_matches_canonical(row, evidence)


@pytest.mark.parametrize(
    "column",
    ["review_status", "evidence_class", "measurement_method", "takeoff_provider",
     "provider_record_id", "quantity", "unit", "page_number"],
)
def test_missing_flattened_column_fails_closed(column):
    """A column absent from the row must not read as 'equal'."""
    row, evidence = _canonical_row()
    row.pop(column)

    with pytest.raises(WorkerApiError):
        _require_row_matches_canonical(row, evidence)


def test_type_punned_flattened_value_fails_closed():
    """A text "1" standing in for an integer 1 must not compare equal.

    The comparison is type-strict precisely so a coerced/stringified column can
    never satisfy a canonical integer (or vice versa).
    """
    row, evidence = _canonical_row(page_number=1)
    assert row["page_number"] == 1
    row["page_number"] = "1"

    divergent = _canonical_row_divergences(row, evidence.model_dump(mode="json"))
    assert "page_identity.page_number" in divergent
    with pytest.raises(WorkerApiError):
        _require_row_matches_canonical(row, evidence)


def test_faithful_row_passes_the_divergence_check():
    row, evidence = _canonical_row(condition="8ft interior walls", scale='1/4" = 1\'')
    assert _canonical_row_divergences(row, evidence.model_dump(mode="json")) == []
    _require_row_matches_canonical(row, evidence)  # must not raise
    assert deserialize_canonical_evidence(row) == evidence
