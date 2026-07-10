"""Estimate readiness gate v1 tests."""

from __future__ import annotations

from tests.test_trade_census_api import _upload_process_and_verify


def _prepare_project(client) -> str:
    pid = _upload_process_and_verify(client)
    client.post(f"/api/v1/projects/{pid}/coverage/draft")
    client.post(f"/api/v1/projects/{pid}/coverage/generic-scope/draft")
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft")
    client.post(f"/api/v1/projects/{pid}/qa/findings/draft")
    return pid


def _resolve_quantities_and_pricing(client, pid: str) -> None:
    reqs = client.get(f"/api/v1/projects/{pid}/quantity-requirements").json()["items"]
    for req in reqs:
        client.post(
            f"/api/v1/projects/{pid}/quantity-requirements/{req['id']}/apply",
            json={"quantity": "10", "unit": req["suggested_unit"] or "EA", "source": "test_verified_quantity"},
        )
    scope_items = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"]
    for item in scope_items:
        detail = client.get(f"/api/v1/projects/{pid}/scope-items/{item['id']}").json()
        method = detail["trade_data"].get("pricing_method")
        if not method:
            continue
        client.post(
            f"/api/v1/projects/{pid}/pricing/generic-inputs/{item['id']}/apply",
            json={"pricing_method": method, "amount": "100", "source": "test_verified_pricing"},
        )
    client.post(f"/api/v1/projects/{pid}/qa/findings/draft")


def test_estimate_readiness_blocked_with_open_requirements(client):
    pid = _prepare_project(client)
    resp = client.get(f"/api/v1/projects/{pid}/estimate-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["ready_for_owner_review"] is False
    assert body["customer_delivery_ready"] is False
    codes = {row["code"] for row in body["blockers"]}
    assert "open_quantity_requirements" in codes
    assert "critical_qa_findings" in codes


def test_estimate_readiness_ready_after_quantity_and_pricing_inputs(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    resp = client.get(f"/api/v1/projects/{pid}/estimate-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready_for_owner_review"
    assert body["ready_for_owner_review"] is True
    assert body["customer_delivery_ready"] is False
    assert body["summary"]["open_quantity_requirement_count"] == 0
    assert body["summary"]["missing_pricing_input_count"] == 0
    assert body["summary"]["items_missing_trusted_evidence_count"] == 0
    assert body["summary"]["low_confidence_item_count"] == 0
    assert body["summary"]["quantity_basis_unclear_count"] == 0
    assert body["summary"]["critical_qa_finding_count"] == 0
    assert "assumptions_register" in body["details"]
    assert body["summary"]["register_blocking_entry_count"] == 0
    assert body["summary"]["assumption_count"] >= 0
    assert body["summary"]["exclusion_count"] >= 0
    assert body["summary"]["open_question_count"] >= 0


def test_estimate_readiness_exposes_truthful_capability_registry(client):
    pid = _prepare_project(client)
    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()

    registry = body["capability_registry"]
    assert registry["schema_version"] == "capability_registry_v1"
    # No capability may be labeled delivery-grade in this internal Phase-0 engine.
    assert registry["all_required_delivery_grade"] is False
    for name, entry in registry["capabilities"].items():
        assert entry["stage"] in registry["stages"], name
        assert entry["delivery_grade"] is False, name
    assert registry["capabilities"]["final_customer_delivery"]["stage"] == "planned"


def test_customer_delivery_lock_fail_closed_when_blocked(client):
    pid = _prepare_project(client)
    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()

    lock = body["customer_delivery_lock"]
    assert body["customer_delivery_ready"] is False
    assert lock["fail_closed"] is True
    assert lock["delivery_unlocked"] is False
    assert lock["state"] == "locked"
    # Capabilities are not production/accuracy-validated and owner approval is absent.
    assert lock["requirements"]["capabilities_delivery_grade"] is False
    assert lock["requirements"]["owner_approval_present"] is False
    assert lock["capability_gaps"]
    assert any("not production" in reason for reason in lock["reasons"])


def test_customer_delivery_lock_stays_locked_even_when_ready_for_owner_review(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()

    # Internal owner-review readiness is reached, but final delivery stays locked.
    assert body["status"] == "ready_for_owner_review"
    assert body["ready_for_owner_review"] is True
    assert body["customer_delivery_ready"] is False
    lock = body["customer_delivery_lock"]
    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["capabilities_delivery_grade"] is False
    assert lock["requirements"]["owner_approval_present"] is False


def test_customer_delivery_lock_flags_test_only_sources(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()

    # The ready flow verifies quantities/pricing with test-only sources; these can
    # never count as real customer-delivery evidence.
    source_check = body["customer_delivery_lock"]["source_check"]
    assert source_check["test_only_source_count"] > 0
    assert source_check["no_test_only_delivery_evidence"] is False
    assert body["customer_delivery_lock"]["requirements"]["no_test_only_delivery_evidence"] is False
    flagged_sources = {row["source"] for row in source_check["test_only_sources"]}
    assert {"test_verified_quantity", "test_verified_pricing"} & flagged_sources


def test_estimate_readiness_unknown_project_404(client):
    pid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/projects/{pid}/estimate-readiness").status_code == 404


def test_estimate_readiness_blocks_missing_extraction_provenance(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    item = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"][0]

    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("DELETE FROM evidence_references WHERE scope_item_id=?", (item["id"],))
        conn.commit()

    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    codes = {row["code"] for row in body["blockers"]}
    assert body["status"] == "blocked"
    assert "missing_extraction_provenance" in codes
    assert body["summary"]["items_missing_trusted_evidence_count"] == 1
    detail = body["details"]["provenance_confidence"]
    assert detail["missing_extraction_provenance"][0]["scope_item_id"] == item["id"]
    assert body["customer_delivery_ready"] is False


def test_estimate_readiness_blocks_assumptions_register_entries(monkeypatch):
    from uuid import uuid4

    from app import estimate_readiness

    pid = uuid4()
    scope_item = {
        "id": "scope-clean",
        "project_id": str(pid),
        "trade_code": "general_trade",
        "category_code": "generic_scope",
        "description": "clean scope",
        "blocking_issues": [],
        "trade_data": {"pricing_ready": True},
        "quantity": "1",
        "quantity_basis": "verified_plan_reference",
    }
    register = {
        "register_type": "assumptions_exclusions_open_questions_v1",
        "customer_delivery_ready": False,
        "summary": {
            "assumption_count": 1,
            "exclusion_count": 0,
            "open_question_count": 1,
            "blocking_entry_count": 1,
            "critical_entry_count": 1,
        },
        "open_questions": [
            {
                "kind": "open_question",
                "code": "scope_clarification_needed",
                "message": "Confirm whether this allowance belongs in base scope.",
                "blocks_delivery": True,
            }
        ],
    }

    monkeypatch.setattr(
        estimate_readiness,
        "list_scope_items",
        lambda project_id, *, filters, limit, offset: ([scope_item], 1),
    )
    monkeypatch.setattr(estimate_readiness, "validate_coverage", lambda project_id: {"complete": True, "findings": []})
    monkeypatch.setattr(estimate_readiness, "list_qa_findings", lambda project_id: [])
    monkeypatch.setattr(estimate_readiness, "list_quantity_requirements", lambda project_id: [])
    monkeypatch.setattr(estimate_readiness, "draft_boe", lambda project_id: {"status": "draft", "assumptions_register": register})
    monkeypatch.setattr(
        estimate_readiness,
        "summarize_scope_provenance",
        lambda items: {
            "items_with_trusted_evidence_count": 1,
            "items_missing_trusted_evidence_count": 0,
            "low_confidence_item_count": 0,
            "quantity_basis_unclear_count": 0,
            "trusted_evidence_coverage_rate": 1,
            "missing_extraction_provenance": [],
            "low_extraction_confidence": [],
            "quantity_basis_unclear": [],
            "items_with_trusted_evidence": [],
            "low_confidence_threshold": 0.55,
        },
    )

    body = estimate_readiness.evaluate_estimate_readiness(pid)

    assert body["status"] == "blocked"
    assert body["ready_for_owner_review"] is False
    assert body["customer_delivery_ready"] is False
    assert body["summary"]["assumption_count"] == 1
    assert body["summary"]["open_question_count"] == 1
    assert body["summary"]["register_blocking_entry_count"] == 1
    assert body["summary"]["register_critical_entry_count"] == 1
    assert body["details"]["assumptions_register"] == register
    assert any(
        blocker["code"] == "assumptions_register_blocking_entries" and blocker["count"] == 1
        for blocker in body["blockers"]
    )


def test_estimate_readiness_does_not_block_plain_assumptions_and_exclusions(monkeypatch):
    from uuid import uuid4

    from app import estimate_readiness

    pid = uuid4()
    scope_item = {
        "id": "scope-assumed",
        "project_id": str(pid),
        "trade_code": "general_trade",
        "category_code": "generic_scope",
        "description": "assumed but otherwise ready scope",
        "blocking_issues": [],
        "trade_data": {"pricing_ready": True},
        "quantity": "1",
        "quantity_basis": "verified_plan_reference",
    }
    register = {
        "register_type": "assumptions_exclusions_open_questions_v1",
        "customer_delivery_ready": False,
        "summary": {
            "assumption_count": 1,
            "exclusion_count": 1,
            "open_question_count": 0,
            "blocking_entry_count": 0,
            "critical_entry_count": 0,
        },
        "assumptions": [
            {
                "kind": "assumption",
                "code": "scope_item_assumption",
                "message": "Existing wall framing remains in place.",
                "blocks_delivery": False,
            }
        ],
        "exclusions": [
            {
                "kind": "exclusion",
                "code": "scope_item_exclusion",
                "message": "Permit fees excluded.",
                "blocks_delivery": False,
            }
        ],
        "open_questions": [],
    }

    monkeypatch.setattr(
        estimate_readiness,
        "list_scope_items",
        lambda project_id, *, filters, limit, offset: ([scope_item], 1),
    )
    monkeypatch.setattr(estimate_readiness, "validate_coverage", lambda project_id: {"complete": True, "findings": []})
    monkeypatch.setattr(estimate_readiness, "list_qa_findings", lambda project_id: [])
    monkeypatch.setattr(estimate_readiness, "list_quantity_requirements", lambda project_id: [])
    monkeypatch.setattr(estimate_readiness, "draft_boe", lambda project_id: {"status": "draft", "assumptions_register": register})
    monkeypatch.setattr(
        estimate_readiness,
        "summarize_scope_provenance",
        lambda items: {
            "items_with_trusted_evidence_count": 1,
            "items_missing_trusted_evidence_count": 0,
            "low_confidence_item_count": 0,
            "quantity_basis_unclear_count": 0,
            "trusted_evidence_coverage_rate": 1,
            "missing_extraction_provenance": [],
            "low_extraction_confidence": [],
            "quantity_basis_unclear": [],
            "items_with_trusted_evidence": [],
            "low_confidence_threshold": 0.55,
        },
    )

    body = estimate_readiness.evaluate_estimate_readiness(pid)

    assert body["status"] == "ready_for_owner_review"
    assert body["ready_for_owner_review"] is True
    assert body["customer_delivery_ready"] is False
    assert body["summary"]["assumption_count"] == 1
    assert body["summary"]["exclusion_count"] == 1
    assert body["summary"]["register_blocking_entry_count"] == 0
    assert not any(blocker["code"] == "assumptions_register_blocking_entries" for blocker in body["blockers"])


def test_estimate_readiness_blocks_low_confidence_items(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    item = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"][0]

    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE scope_items SET extraction_confidence=? WHERE id=?", (0.1, item["id"]))
        conn.commit()

    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    codes = {row["code"] for row in body["blockers"]}
    assert body["status"] == "blocked"
    assert "low_extraction_confidence" in codes
    assert body["summary"]["low_confidence_item_count"] == 1
    detail = body["details"]["provenance_confidence"]
    assert detail["low_extraction_confidence"][0]["scope_item_id"] == item["id"]
    assert body["customer_delivery_ready"] is False


def test_estimate_readiness_blocks_unclear_quantity_basis(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    item = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"][0]

    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE scope_items SET quantity_basis='unknown' WHERE id=?", (item["id"],))
        conn.commit()

    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    codes = {row["code"] for row in body["blockers"]}
    assert body["status"] == "blocked"
    assert "quantity_basis_unclear" in codes
    assert body["summary"]["quantity_basis_unclear_count"] == 1
    detail = body["details"]["provenance_confidence"]
    assert detail["quantity_basis_unclear"][0]["scope_item_id"] == item["id"]
    assert body["customer_delivery_ready"] is False


def test_estimate_readiness_pages_scope_items_past_first_batch(monkeypatch):
    from uuid import uuid4

    from app import estimate_readiness

    pid = uuid4()
    first_page = [
        {
            "id": f"scope-{idx}",
            "project_id": str(pid),
            "trade_code": "general_trade",
            "category_code": "generic_scope",
            "description": "clean scope",
            "blocking_issues": [],
            "trade_data": {"pricing_ready": True},
            "quantity": "1",
            "quantity_basis": "manual_reviewer_entry",
        }
        for idx in range(estimate_readiness._list_all_scope_items.__kwdefaults__["page_size"])
    ]
    late_item = {
        "id": "late-low-confidence",
        "project_id": str(pid),
        "trade_code": "general_trade",
        "category_code": "generic_scope",
        "description": "late item",
        "blocking_issues": [],
        "trade_data": {"pricing_ready": True},
        "quantity": "1",
        "quantity_basis": "manual_reviewer_entry",
    }
    calls = []

    def fake_list_scope_items(project_id, *, filters, limit, offset):
        calls.append(offset)
        if offset == 0:
            return first_page, len(first_page) + 1
        return [late_item], len(first_page) + 1

    def fake_provenance(items):
        low = []
        if any(item["id"] == "late-low-confidence" for item in items):
            low = [{"scope_item_id": "late-low-confidence", "code": "low_extraction_confidence"}]
        return {
            "items_with_trusted_evidence_count": len(items),
            "items_missing_trusted_evidence_count": 0,
            "low_confidence_item_count": len(low),
            "quantity_basis_unclear_count": 0,
            "trusted_evidence_coverage_rate": 1,
            "missing_extraction_provenance": [],
            "low_extraction_confidence": low,
            "quantity_basis_unclear": [],
            "items_with_trusted_evidence": [],
            "low_confidence_threshold": 0.55,
        }

    monkeypatch.setattr(estimate_readiness, "list_scope_items", fake_list_scope_items)
    monkeypatch.setattr(estimate_readiness, "summarize_scope_provenance", fake_provenance)
    monkeypatch.setattr(estimate_readiness, "validate_coverage", lambda project_id: {"complete": True, "findings": []})
    monkeypatch.setattr(estimate_readiness, "list_qa_findings", lambda project_id: [])
    monkeypatch.setattr(estimate_readiness, "list_quantity_requirements", lambda project_id: [])
    monkeypatch.setattr(estimate_readiness, "draft_boe", lambda project_id: {"status": "ready"})

    body = estimate_readiness.evaluate_estimate_readiness(pid)

    assert calls == [0, len(first_page)]
    assert body["summary"]["scope_item_count"] == len(first_page) + 1
    assert body["status"] == "blocked"
    assert any(blocker["code"] == "low_extraction_confidence" for blocker in body["blockers"])


def test_estimate_readiness_blocks_missing_confidence_score(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    item = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"][0]

    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE scope_items SET extraction_confidence=NULL WHERE id=?", (item["id"],))
        conn.commit()

    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    codes = {row["code"] for row in body["blockers"]}
    assert body["status"] == "blocked"
    assert "low_extraction_confidence" in codes
    assert body["summary"]["low_confidence_item_count"] == 1
    assert body["customer_delivery_ready"] is False


def test_estimate_readiness_requires_evidence_sheet_to_be_verified(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    item = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"][0]

    from app.database import get_connection

    with get_connection() as conn:
        evidence = conn.execute(
            "SELECT sheet_id FROM evidence_references WHERE scope_item_id=? LIMIT 1",
            (item["id"],),
        ).fetchone()
        assert evidence is not None
        conn.execute("UPDATE sheets SET review_status='needs_review' WHERE id=?", (evidence["sheet_id"],))
        conn.commit()

    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    codes = {row["code"] for row in body["blockers"]}
    assert body["status"] == "blocked"
    assert "missing_extraction_provenance" in codes
    assert body["summary"]["items_missing_trusted_evidence_count"] >= 1
    missing = body["details"]["provenance_confidence"]["missing_extraction_provenance"]
    assert any(row["scope_item_id"] == item["id"] for row in missing)
    assert body["customer_delivery_ready"] is False


def test_estimate_readiness_blocks_nonnumeric_confidence_score(client):
    pid = _prepare_project(client)
    _resolve_quantities_and_pricing(client, pid)
    item = client.get(f"/api/v1/projects/{pid}/scope-items?limit=200").json()["items"][0]

    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("UPDATE scope_items SET extraction_confidence=? WHERE id=?", ("not-a-number", item["id"]))
        conn.commit()

    body = client.get(f"/api/v1/projects/{pid}/estimate-readiness").json()
    codes = {row["code"] for row in body["blockers"]}
    assert body["status"] == "blocked"
    assert "low_extraction_confidence" in codes
    detail = body["details"]["provenance_confidence"]
    assert detail["low_extraction_confidence"][0]["message"] == "Extraction confidence score is not numeric."
    assert body["customer_delivery_ready"] is False
