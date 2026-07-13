"""Generic estimate draft bridge tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from tests.test_generic_pricing_prep_api import _prepare_generic_scope

_LEAK_TERMS = [
    "direct_cost",
    "labor_cost",
    "material_cost",
    "equipment_cost",
    "subcontract_cost",
    "other_direct_cost",
    "gross margin",
    "margin",
    "markup",
    "overhead",
    "profit",
    "loaded_rate",
    "cost_book",
    "source",
    "pricing_basis",
    "generic_pricing_basis",
    "reviewer",
    "readiness",
    "/home/",
    "api_key",
]


def _allow_customer_delivery_trade(monkeypatch, trade_code: str = "electrical") -> None:
    monkeypatch.setattr(
        "app.capability_registry.SUPPORTED_CUSTOMER_DELIVERY_TRADES",
        frozenset({trade_code}),
    )


def _apply_quantity_and_pricing_for_trade(
    client,
    pid: str,
    trade_code: str,
    amount: str = "125.50",
    cost_components: dict | None = None,
) -> str:
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})
    reqs = client.post(f"/api/v1/projects/{pid}/quantity-requirements/draft").json()["items"]
    req = next(row for row in reqs if row["trade_code"] == trade_code)
    client.post(
        f"/api/v1/projects/{pid}/quantity-requirements/{req['id']}/apply",
        json={"quantity": "4", "unit": "EA", "source": "staff_verified_takeoff"},
    )
    scope_item_id = req["scope_item_id"]
    payload: dict[str, object] = {
        "pricing_method": "unit_rate_needed",
        "amount": amount,
        "source": "verified_internal_unit_rate",
        "actor": "estimator-1",
        "note": "Verified unit rate for bridge fixture.",
    }
    if cost_components is not None:
        payload["cost_components"] = cost_components
    resp = client.post(
        f"/api/v1/projects/{pid}/pricing/generic-inputs/{scope_item_id}/apply",
        json=payload,
    )
    assert resp.status_code == 200
    return scope_item_id


def test_generic_estimate_bridge_creates_internal_draft_for_ready_scope(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")

    resp = client.post(
        f"/api/v1/projects/{pid}/estimates/generic-draft",
        json={"name": "Bridge Draft"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 1
    assert body["summary"]["blocked_scope_item_count"] > 0
    assert body["summary"]["line_item_count"] == 1
    assert body["summary"]["customer_delivery_ready"] is False
    assert body["summary"]["final_estimate_approved"] is False
    assert body["summary"]["external_messages"] is False
    assert body["summary"]["payments"] is False
    assert body["estimate"]["name"] == "Bridge Draft"
    assert body["version"]["status"] == "draft"
    assert body["version"]["approved_at"] is None
    assert body["version"]["config"]["source"] == "generic_estimate_bridge_v1"
    assert body["version"]["config"]["customer_delivery_ready"] is False
    assert body["version"]["config"]["customer_delivery_lock"]["delivery_unlocked"] is False
    assert body["version"]["config"]["customer_delivery_lock"]["requirements"]["owner_approval_present"] is False
    assert body["summary"]["customer_delivery_lock"]["delivery_unlocked"] is False
    assert body["summary"]["customer_delivery_lock"]["expected_scope_item_ids"] == [ready_scope_item_id]
    assert body["line_items"][0]["scope_item_id"] == ready_scope_item_id
    assert body["line_items"][0]["status"] == "generic_pricing_basis"
    assert Decimal(body["line_items"][0]["direct_cost_total"]) == Decimal("502.00")
    assert Decimal(body["line_items"][0]["other_direct_cost"]) == Decimal("502.00")
    assert body["line_items"][0]["subcontract_cost"] == "0.00"
    component = body["line_items"][0]["components"][0]
    assert component["source"] == "verified_internal_unit_rate"
    assert component["schema_version"] == "generic_cost_components_v1"
    assert component["direct_costs"] == {
        "labor": "0.00",
        "material": "0.00",
        "equipment": "0.00",
        "subcontract": "0.00",
        "other_direct": "125.50",
    }
    assert component["indirect_costs"] == {
        "overhead": "0.00",
        "profit": "0.00",
        "contingency": "0.00",
        "markup": "0.00",
    }
    assert component["customer_ready"] is False
    plumbing_blocked = next(row for row in body["blocked_scope_items"] if row["trade_code"] == "plumbing")
    blocked_codes = {b["code"] for b in plumbing_blocked["blockers"]}
    assert {"missing_quantity", "missing_unit_rate"} <= blocked_codes

    estimates = client.get(f"/api/v1/projects/{pid}/estimates").json()["items"]
    assert any(row["id"] == body["estimate"]["id"] for row in estimates)


def test_generic_estimate_bridge_uses_explicit_all_trade_cost_components(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(
        client,
        pid,
        "electrical",
        amount="125.50",
        cost_components={
            "basis_type": "unit_rate",
            "component_source": "verified_component_record",
            "direct_costs": {
                "labor": "50.00",
                "material": "40.00",
                "equipment": "10.00",
                "subcontract": "20.00",
                "other_direct": "5.50",
            },
            "indirect_costs": {
                "overhead": "10.00",
                "profit": "12.00",
                "contingency": "5.00",
                "markup": "0.00",
            },
        },
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    line = resp.json()["line_items"][0]
    assert line["scope_item_id"] == ready_scope_item_id
    # Unit-rate component buckets are multiplied by the verified quantity (4 EA).
    assert Decimal(line["labor_cost"]) == Decimal("200.00")
    assert Decimal(line["material_cost"]) == Decimal("160.00")
    assert Decimal(line["equipment_cost"]) == Decimal("40.00")
    assert Decimal(line["subcontract_cost"]) == Decimal("80.00")
    assert Decimal(line["other_direct_cost"]) == Decimal("22.00")
    assert Decimal(line["direct_cost_total"]) == Decimal("502.00")
    component = line["components"][0]
    assert component["component_type"] == "generic_cost_components"
    assert component["direct_costs"]["labor"] == "50.00"
    assert component["indirect_costs"] == {
        "overhead": "10.00",
        "profit": "12.00",
        "contingency": "5.00",
        "markup": "0.00",
    }
    assert component["component_source"] == "verified_component_record"
    assert component["customer_ready"] is False


def test_generic_estimate_bridge_delivery_lock_blocks_duplicate_ready_scope_ids(monkeypatch):
    """Draft-level lock must catch whole-draft lineage bugs per-item checks miss."""
    from app.generic_estimate_bridge import _delivery_lock_for_ready_items

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8d",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "duplicate ready scope",
        "quantity": "4",
        "unit": "EA",
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }

    lock = _delivery_lock_for_ready_items([item, {**item, "description": "duplicate ready scope copy"}])

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["supported_scope"] is False
    assert lock["expected_scope_item_ids_valid"] is False
    assert lock["duplicate_expected_scope_item_ids"] == [item["id"]]
    assert "Expected scope item IDs are missing, malformed, or duplicated" in " ".join(lock["reasons"])


def test_generic_estimate_bridge_delivery_lock_requires_actual_verified_evidence(monkeypatch):
    """Draft-level lock evidence_complete must mean evidence rows, not just ready items."""
    from app import generic_estimate_bridge as bridge

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8e",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "ready scope without evidence",
        "quantity": "4",
        "unit": "EA",
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }
    monkeypatch.setattr(bridge, "list_evidence", lambda scope_item_id: [])

    lock = bridge._delivery_lock_for_ready_items([item])

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["evidence_complete"] is False
    assert "Complete verified evidence is not present for all scope." in lock["reasons"]

    monkeypatch.setattr(
        bridge,
        "list_evidence",
        lambda scope_item_id: [
            {
                "source_artifact_ref": "customer_plan_sha256_2026",
                "verified_sheet_number": "A1.0",
                "pdf_page_number": 1,
                "evidence_type": "plan_region",
                "description": "verified scope reference",
            }
        ],
    )
    lock_with_evidence = bridge._delivery_lock_for_ready_items([item])
    assert lock_with_evidence["requirements"]["evidence_complete"] is True
    assert lock_with_evidence["delivery_unlocked"] is False  # reviews/owner/capability gates still lock it.


def test_generic_estimate_bridge_line_items_preserve_evidence_artifact_provenance(monkeypatch):
    """Draft lines must not drop evidence refs used by downstream delivery locks."""
    from app import generic_estimate_bridge as bridge

    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a91",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "ready scope with evidence provenance",
        "quantity": "4",
        "unit": "EA",
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }
    monkeypatch.setattr(
        bridge,
        "list_evidence",
        lambda scope_item_id: [
            {
                "source_artifact_ref": "artifact://customer-plan/a101-region-1",
                "verified_sheet_number": "A1.0",
                "pdf_page_number": 1,
                "evidence_type": "plan_region",
                "description": "verified scope reference",
                "extracted_text_quote": "Fixture mark E-1",
                "text_block_coords": {"x": 1, "y": 2},
                "page_region_coords": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
                "provider_confidence": 0.98,
                "requires_human_verification": True,
            }
        ],
    )

    line = bridge._line_from_item(item)

    assert line["evidence"] == [
        {
            "source_artifact_ref": "artifact://customer-plan/a101-region-1",
            "verified_sheet_number": "A1.0",
            "pdf_page_number": 1,
            "evidence_type": "plan_region",
            "description": "verified scope reference",
            "extracted_text_quote": "Fixture mark E-1",
            "text_block_coords": {"x": 1, "y": 2},
            "page_region_coords": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
            "provider_confidence": 0.98,
            "requires_human_verification": True,
        }
    ]


def test_generic_estimate_bridge_delivery_lock_rejects_malformed_evidence_rows(monkeypatch):
    from app import generic_estimate_bridge as bridge

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8f",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "ready scope with malformed evidence",
        "quantity": "4",
        "unit": "EA",
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }
    monkeypatch.setattr(
        bridge,
        "list_evidence",
        lambda scope_item_id: [
            {"verified_sheet_number": "", "pdf_page_number": 1, "evidence_type": "plan_region"},
            {"verified_sheet_number": "A1.0", "pdf_page_number": 0, "evidence_type": "plan_region"},
            {"verified_sheet_number": "A1.0", "pdf_page_number": True, "evidence_type": "plan_region"},
            {"verified_sheet_number": "A1.0", "pdf_page_number": 1, "evidence_type": ""},
        ],
    )

    lock = bridge._delivery_lock_for_ready_items([item])

    assert lock["requirements"]["evidence_complete"] is False
    assert lock["delivery_unlocked"] is False


def test_generic_estimate_bridge_delivery_lock_rejects_test_only_evidence_rows(monkeypatch):
    from app import generic_estimate_bridge as bridge

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a90",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "ready scope with fixture evidence",
        "quantity": "4",
        "unit": "EA",
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }
    monkeypatch.setattr(
        bridge,
        "list_evidence",
        lambda scope_item_id: [
            {
                "verified_sheet_number": "A1.0",
                "pdf_page_number": 1,
                "evidence_type": "plan_region",
                "description": "fixture sheet region",
                "source_artifact_ref": "harness_test_only_region",
            },
            {
                "verified_sheet_number": "A2.0",
                "pdf_page_number": 2,
                "evidence_type": "plan_region",
                "description": "nested fixture sheet region",
                "metadata": {"provenance_metadata": {"internal_testing_only": True}},
            },
        ],
    )

    lock = bridge._delivery_lock_for_ready_items([item])

    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["evidence_complete"] is False
    assert lock["delivery_unlocked"] is False
    assert "Complete verified evidence is not present for all scope." in lock["reasons"]


def test_generic_estimate_bridge_blocks_unscoped_real_sources_before_line_generation(monkeypatch):
    """Internal draft generation must not turn real-looking orphan sources into lines."""
    from app.generic_estimate_bridge import _missing_blockers

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": None,
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "priced scope missing durable id",
        "quantity": "4",
        "unit": "EA",
        "blocking_issues": [],
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }

    blockers = _missing_blockers(item)

    assert {blocker["code"] for blocker in blockers} == {
        "unscoped_delivery_sources",
        "unsupported_customer_delivery_scope",
    }


def test_generic_estimate_bridge_blocks_malformed_ready_pricing_basis_without_error(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app.extraction_db import update_scope_item

    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    update_scope_item(
        UUID(scope_item_id),
        trade_data={
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {},
        },
        blocking_issues=[],
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    malformed = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == scope_item_id)
    assert {blocker["code"] for blocker in malformed["blockers"]} == {"test_only_delivery_sources"}
    assert body["version"]["status"] == "draft"
    assert body["summary"]["customer_delivery_ready"] is False


def test_generic_estimate_bridge_blocks_non_object_cost_components(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app.extraction_db import update_scope_item

    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    update_scope_item(
        UUID(scope_item_id),
        trade_data={
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {
                "amount": "125.50",
                "source": "malformed_component_record",
                "cost_components": [],
            },
        },
        blocking_issues=[],
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {
        "invalid_cost_components",
        "test_only_delivery_sources",
    }
    assert body["summary"]["customer_delivery_ready"] is False
    assert body["summary"]["external_messages"] is False


def test_generic_estimate_bridge_blocks_nested_non_object_cost_component_buckets(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app.extraction_db import update_scope_item

    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    update_scope_item(
        UUID(scope_item_id),
        trade_data={
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {
                "amount": "125.50",
                "source": "verified_internal_unit_rate",
                "cost_components": {
                    "component_source": "verified_component_record",
                    "direct_costs": {"other_direct": "125.50"},
                    "indirect_costs": ["markup", "profit"],
                },
            },
        },
        blocking_issues=[],
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"invalid_cost_components"}
    assert body["summary"]["customer_delivery_ready"] is False


def test_generic_estimate_bridge_blocks_unquantizable_money_without_crashing(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app.extraction_db import update_scope_item

    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    update_scope_item(
        UUID(scope_item_id),
        trade_data={
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": {
                "amount": "1e1000000",
                "source": "verified_internal_unit_rate",
                "cost_components": {
                    "component_source": "verified_component_record",
                    "direct_costs": {"other_direct": "1e1000000"},
                },
            },
        },
        blocking_issues=[],
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"invalid_amount"}
    assert body["summary"]["customer_delivery_ready"] is False


def test_generic_estimate_bridge_blocks_cost_component_total_mismatch(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(
        client,
        pid,
        "electrical",
        amount="125.50",
        cost_components={
            "component_source": "verified_component_record",
            "direct_costs": {
                "labor": "10.00",
                "material": "0.00",
                "equipment": "0.00",
                "subcontract": "0.00",
                "other_direct": "0.00",
            }
        },
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"cost_component_total_mismatch"}
    assert body["summary"]["final_estimate_approved"] is False


def test_generic_estimate_bridge_abstains_from_unsupported_scope_even_when_priced(client):
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    assert body["summary"]["customer_delivery_ready"] is False
    assert body["line_items"] == []
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == ready_scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"unsupported_customer_delivery_scope"}


def test_generic_estimate_bridge_blocks_test_only_sources_for_supported_trade(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(
        client,
        pid,
        "electrical",
        amount="125.50",
    )
    from app.extraction_db import get_scope_item, update_scope_item

    item = get_scope_item(UUID(pid), UUID(ready_scope_item_id))
    assert item is not None
    raw_quantity_inputs = item["raw_quantity_inputs"]
    raw_quantity_inputs["verified_quantity_input_v1"]["source"] = "test_quantity_fixture"
    trade_data = item["trade_data"]
    trade_data["pricing_basis"]["source"] = "mock_pricing_fixture"
    update_scope_item(UUID(ready_scope_item_id), raw_quantity_inputs=raw_quantity_inputs, trade_data=trade_data)

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == ready_scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"test_only_delivery_sources"}


def test_generic_estimate_bridge_blocks_missing_sources_for_supported_trade(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    from app.extraction_db import get_scope_item, update_scope_item

    item = get_scope_item(UUID(pid), UUID(ready_scope_item_id))
    assert item is not None
    raw_quantity_inputs = item["raw_quantity_inputs"]
    raw_quantity_inputs["verified_quantity_input_v1"].pop("source", None)
    trade_data = item["trade_data"]
    trade_data["pricing_basis"].pop("source", None)
    update_scope_item(UUID(ready_scope_item_id), raw_quantity_inputs=raw_quantity_inputs, trade_data=trade_data)

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == ready_scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"test_only_delivery_sources"}


def test_generic_estimate_bridge_preserves_test_only_metadata_flags(client, monkeypatch):
    """Real-looking source labels must still abstain when metadata marks them test-only."""
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(
        client,
        pid,
        "electrical",
        cost_components={
            "basis_type": "unit_rate",
            "component_source": "verified_component_record",
            "direct_costs": {
                "labor": "0.00",
                "material": "0.00",
                "equipment": "0.00",
                "subcontract": "0.00",
                "other_direct": "125.50",
            },
        },
    )
    from app.extraction_db import get_scope_item, update_scope_item

    item = get_scope_item(UUID(pid), UUID(ready_scope_item_id))
    assert item is not None
    raw_quantity_inputs = item["raw_quantity_inputs"]
    raw_quantity_inputs["verified_quantity_input_v1"]["source"] = "staff_verified_takeoff"
    raw_quantity_inputs["verified_quantity_input_v1"]["internal_testing_only"] = True
    trade_data = item["trade_data"]
    trade_data["pricing_basis"]["source"] = "verified_internal_unit_rate"
    trade_data["pricing_basis"]["test_only"] = True
    trade_data["pricing_basis"]["cost_components"]["component_source"] = "verified_component_record"
    trade_data["pricing_basis"]["cost_components"]["synthetic_only"] = True
    update_scope_item(UUID(ready_scope_item_id), raw_quantity_inputs=raw_quantity_inputs, trade_data=trade_data)

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    assert body["line_items"] == []
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == ready_scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"test_only_delivery_sources"}
    assert body["summary"]["customer_delivery_ready"] is False


def test_generic_estimate_bridge_preserves_nested_test_only_metadata_envelopes(client, monkeypatch):
    """Fixture provenance hidden in metadata envelopes must block line generation."""
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(
        client,
        pid,
        "electrical",
        cost_components={
            "basis_type": "unit_rate",
            "component_source": "verified_component_record",
            "direct_costs": {
                "labor": "0.00",
                "material": "0.00",
                "equipment": "0.00",
                "subcontract": "0.00",
                "other_direct": "125.50",
            },
        },
    )
    from app.extraction_db import get_scope_item, update_scope_item

    item = get_scope_item(UUID(pid), UUID(ready_scope_item_id))
    assert item is not None
    raw_quantity_inputs = item["raw_quantity_inputs"]
    raw_quantity_inputs["verified_quantity_input_v1"]["source"] = "staff_verified_takeoff"
    raw_quantity_inputs["verified_quantity_input_v1"]["provenance_metadata"] = {
        "internal_testing_only": True,
    }
    trade_data = item["trade_data"]
    trade_data["pricing_basis"]["source"] = "verified_internal_unit_rate"
    trade_data["pricing_basis"]["metadata"] = {"test_only": True}
    trade_data["pricing_basis"]["cost_components"]["component_source"] = "verified_component_record"
    trade_data["pricing_basis"]["cost_components"]["audit_metadata"] = {
        "synthetic_only": True,
    }
    update_scope_item(UUID(ready_scope_item_id), raw_quantity_inputs=raw_quantity_inputs, trade_data=trade_data)

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["line_item_count"] == 0
    assert body["line_items"] == []
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == ready_scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"test_only_delivery_sources"}
    assert body["summary"]["customer_delivery_ready"] is False


def test_generic_estimate_bridge_fails_closed_on_malformed_source_containers(monkeypatch):
    """Malformed quantity/pricing containers must block, not crash or unlock lines."""
    from app.generic_estimate_bridge import _missing_blockers

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8d",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "priced scope with malformed evidence metadata",
        "quantity": "4",
        "unit": "EA",
        "blocking_issues": [],
        "raw_quantity_inputs": ["staff_verified_takeoff"],
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": ["verified_internal_unit_rate"],
        },
    }

    blockers = _missing_blockers(item)

    assert {blocker["code"] for blocker in blockers} == {
        "missing_unit_rate",
        "test_only_delivery_sources",
    }


def test_generic_estimate_bridge_fails_closed_on_malformed_trade_data(monkeypatch):
    """A non-object trade_data payload is not valid readiness evidence."""
    from app.generic_estimate_bridge import _missing_blockers

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8d",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "priced scope with malformed trade data",
        "quantity": "4",
        "unit": "EA",
        "blocking_issues": [],
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": ["unit_rate_needed", "verified_internal_unit_rate"],
    }

    blockers = _missing_blockers(item)

    assert {blocker["code"] for blocker in blockers} == {
        "missing_pricing_method",
        "missing_unit_rate",
        "test_only_delivery_sources",
    }


def test_generic_estimate_bridge_fails_closed_on_malformed_pricing_basis(monkeypatch):
    """Malformed pricing/evidence containers must be reported as unverified provenance."""
    from app.generic_estimate_bridge import _missing_blockers

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8d",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "priced scope with malformed pricing basis",
        "quantity": "4",
        "unit": "EA",
        "blocking_issues": [],
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unit_rate_needed",
            "pricing_ready": True,
            "pricing_basis": ["verified_internal_unit_rate"],
        },
    }

    blockers = _missing_blockers(item)

    assert {blocker["code"] for blocker in blockers} == {
        "missing_unit_rate",
        "test_only_delivery_sources",
    }


def test_generic_estimate_bridge_blocks_unknown_pricing_method(monkeypatch):
    """Unknown methods must not fall through as single-quantity lump-sum lines."""
    from app.generic_estimate_bridge import _missing_blockers

    _allow_customer_delivery_trade(monkeypatch)
    item = {
        "id": "4c35d0dc-3132-446c-b191-0dafc9168a8d",
        "trade_code": "electrical",
        "category_code": "generic_scope",
        "description": "priced scope with unsupported pricing method",
        "quantity": "4",
        "unit": "EA",
        "blocking_issues": [],
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {"source": "staff_verified_takeoff"},
        },
        "trade_data": {
            "pricing_method": "unsupported_custom_formula",
            "pricing_ready": True,
            "pricing_basis": {"amount": "125.50", "source": "verified_internal_unit_rate"},
        },
    }

    blockers = _missing_blockers(item)

    assert {blocker["code"] for blocker in blockers} == {"invalid_pricing_method"}


def test_generic_estimate_bridge_blocks_test_only_component_source(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    ready_scope_item_id = _apply_quantity_and_pricing_for_trade(
        client,
        pid,
        "electrical",
        cost_components={
            "basis_type": "unit_rate",
            "component_source": "component_fixture",
            "direct_costs": {
                "labor": "0.00",
                "material": "0.00",
                "equipment": "0.00",
                "subcontract": "0.00",
                "other_direct": "125.50",
            },
        },
    )

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["line_item_count"] == 0
    blocked = next(row for row in body["blocked_scope_items"] if row["scope_item_id"] == ready_scope_item_id)
    assert {blocker["code"] for blocker in blocked["blockers"]} == {"test_only_delivery_sources"}


def test_generic_estimate_bridge_all_unready_creates_empty_safe_draft(client):
    pid = _prepare_generic_scope(client)
    client.post(f"/api/v1/projects/{pid}/pricing/generic-methods/draft", json={})

    resp = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={})

    assert resp.status_code == 201
    body = resp.json()
    assert body["summary"]["ready_scope_item_count"] == 0
    assert body["summary"]["blocked_scope_item_count"] > 0
    assert body["summary"]["line_item_count"] == 0
    assert body["summary"]["customer_delivery_ready"] is False
    assert body["line_items"] == []
    assert body["version"]["status"] == "draft"
    assert body["version"]["approved_at"] is None
    assert all(row["blockers"] for row in body["blocked_scope_items"])


def test_generic_draft_proposal_preview_is_customer_safe_and_read_only(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={"name": "Preview Draft"}).json()
    estimate_id = draft["estimate"]["id"]
    version_id = draft["version"]["id"]

    resp = client.get(f"/api/v1/projects/{pid}/estimates/{estimate_id}/versions/{version_id}/proposal-preview")

    assert resp.status_code == 200
    body = resp.json()
    preview = body["customer_safe_preview"]
    assert preview["title"] == "Preview Draft"
    assert preview["status"] == "internal_preview_only"
    assert preview["summary"] == {
        "scope_line_count": 1,
        "blocked_scope_item_count": draft["summary"]["blocked_scope_item_count"],
        "quantity_abstained_count": 0,
        "unsupported_scope_count": 0,
        "customer_delivery_ready": False,
        "final_estimate_approved": False,
        "external_messages": False,
        "payments": False,
    }
    assert preview["safety_flags"] == {
        "preview_only": True,
        "customer_delivery_ready": False,
        "final_estimate_approved": False,
        "external_messages": False,
        "payments": False,
        "proposal_created": False,
        "proposal_issued": False,
    }
    assert preview["line_items"][0]["description"]
    assert preview["line_items"][0]["quantity"] == "4"
    assert preview["line_items"][0]["unit"] == "EA"
    assert preview["clarifications"]
    assert client.get(f"/api/v1/projects/{pid}/proposals").json()["items"] == []

    rendered = str(preview).lower()
    for term in _LEAK_TERMS:
        assert term not in rendered, f"preview leaked {term!r}"


def test_generic_draft_proposal_preview_abstains_test_only_quantity_source(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app import pricing_db

    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={"name": "Preview Draft"}).json()
    line = pricing_db.get_line_items(draft["version"]["id"])[0]
    pricing_db.update_line_item(
        UUID(line["id"]),
        {"overrides": [{"quantity_source": "test_fixture_takeoff"}]},
    )

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 200
    preview = resp.json()["customer_safe_preview"]
    assert preview["summary"]["scope_line_count"] == 1
    assert preview["summary"]["quantity_abstained_count"] == 1
    assert preview["line_items"][0]["quantity"] == ""
    assert preview["line_items"][0]["unit"] == ""
    assert preview["line_items"][0]["scope_note"] == "Quantity is pending validation and is withheld from this preview."
    assert "4" not in str(preview["line_items"][0])
    assert any("withheld" in note for note in preview["clarifications"])


def test_generic_draft_proposal_preview_abstains_unsupported_scope_quantity(client, monkeypatch):
    """Preview read path must re-check supported scope for stale/manual draft lines."""
    from app import pricing_db

    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={"name": "Preview Draft"}).json()
    line = pricing_db.get_line_items(draft["version"]["id"])[0]
    pricing_db.update_line_item(
        UUID(line["id"]),
        {"overrides": [{"quantity_source": "staff_verified_takeoff"}]},
    )
    monkeypatch.setattr(
        "app.capability_registry.SUPPORTED_CUSTOMER_DELIVERY_TRADES",
        frozenset(),
    )

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 200
    preview = resp.json()["customer_safe_preview"]
    assert preview["summary"]["scope_line_count"] == 1
    assert preview["summary"]["quantity_abstained_count"] == 1
    assert preview["summary"]["unsupported_scope_count"] == 1
    assert preview["line_items"][0]["quantity"] == ""
    assert preview["line_items"][0]["unit"] == ""
    assert preview["line_items"][0]["scope_note"] == (
        "Unsupported scope is withheld from this preview until its trade/project lane is accuracy-validated."
    )
    assert "4" not in str(preview["line_items"][0])
    assert any("not accuracy-validated" in note for note in preview["clarifications"])


def test_generic_draft_proposal_preview_abstains_duplicate_scope_id_rows(client, monkeypatch):
    """A supported duplicate must not mask a later unsupported duplicate row."""
    from app import pricing_db

    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={"name": "Preview Draft"}).json()
    line = pricing_db.get_line_items(draft["version"]["id"])[0]
    supported_line = {
        **line,
        "quantity_source": "staff_verified_takeoff",
        "overrides": [{"quantity_source": "staff_verified_takeoff"}],
    }
    unsupported_duplicate = {
        **supported_line,
        "trade_code": "unsupported_manual_trade",
        "description": "unsupported duplicate must abstain",
    }
    pricing_db.replace_line_items(
        draft["version"]["id"],
        UUID(pid),
        [supported_line, unsupported_duplicate],
    )

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 200
    preview = resp.json()["customer_safe_preview"]
    assert preview["summary"]["scope_line_count"] == 2
    assert preview["summary"]["quantity_abstained_count"] == 2
    assert preview["summary"]["unsupported_scope_count"] == 2
    assert all(item["quantity"] == "" for item in preview["line_items"])
    assert all(item["unit"] == "" for item in preview["line_items"])
    assert "4" not in str(preview["line_items"])


def test_generic_draft_proposal_preview_abstains_missing_quantity_source(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app import pricing_db

    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={"name": "Preview Draft"}).json()
    line = pricing_db.get_line_items(draft["version"]["id"])[0]
    pricing_db.update_line_item(
        UUID(line["id"]),
        {"overrides": [{"quantity_source": None}]},
    )

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 200
    preview = resp.json()["customer_safe_preview"]
    assert preview["summary"]["quantity_abstained_count"] == 1
    assert preview["line_items"][0]["quantity"] == ""
    assert preview["line_items"][0]["unit"] == ""
    assert "4" not in str(preview["line_items"][0])


def test_generic_draft_proposal_preview_abstains_nested_test_only_quantity_metadata(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app import pricing_db

    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={"name": "Preview Draft"}).json()
    line = pricing_db.get_line_items(draft["version"]["id"])[0]
    pricing_db.update_line_item(
        UUID(line["id"]),
        {
            "overrides": [
                {
                    "quantity_source": "staff_verified_takeoff",
                    "metadata": {"provenance_metadata": {"test_only": True}},
                }
            ]
        },
    )

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 200
    preview = resp.json()["customer_safe_preview"]
    assert preview["summary"]["quantity_abstained_count"] == 1
    assert preview["line_items"][0]["quantity"] == ""
    assert preview["line_items"][0]["unit"] == ""
    assert "4" not in str(preview["line_items"][0])


def test_generic_draft_proposal_preview_sanitizes_source_terms_in_title_and_unit(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app.extraction_db import update_scope_item

    pid = _prepare_generic_scope(client)
    scope_item_id = _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    update_scope_item(
        UUID(scope_item_id),
        description="source loaded_rate scope should be replaced",
        location="cost_book source room",
        unit="source_loaded_rate_unit",
    )
    draft = client.post(
        f"/api/v1/projects/{pid}/estimates/generic-draft",
        json={"name": "Source Cost Book Draft"},
    ).json()

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 200
    preview = resp.json()["customer_safe_preview"]
    assert preview["title"] == "Draft Estimate Preview"
    assert preview["line_items"][0]["description"] == "Scope item pending final wording."
    assert "location" not in preview["line_items"][0]
    assert preview["line_items"][0]["unit"] == ""
    rendered = str(preview).lower()
    for term in _LEAK_TERMS:
        assert term not in rendered, f"preview leaked {term!r}"


def test_generic_draft_proposal_preview_ownership_and_unknown_version(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={}).json()
    other_pid = _prepare_generic_scope(client)

    assert client.get(
        f"/api/v1/projects/{other_pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    ).status_code == 404
    assert client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/00000000-0000-0000-0000-000000000000/proposal-preview"
    ).status_code == 404


def test_generic_draft_proposal_preview_locks_non_draft_versions(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app import pricing_db

    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={}).json()
    pricing_db.update_version(draft["version"]["id"], {"status": "approved"})

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "http_423"
    assert "final customer delivery requires the full P0 approval gate" in resp.json()["error"]["message"]


def test_generic_draft_proposal_preview_locks_delivery_ready_config(client, monkeypatch):
    _allow_customer_delivery_trade(monkeypatch)
    from app import pricing_db

    pid = _prepare_generic_scope(client)
    _apply_quantity_and_pricing_for_trade(client, pid, "electrical")
    draft = client.post(f"/api/v1/projects/{pid}/estimates/generic-draft", json={}).json()
    config = dict(draft["version"]["config"])
    config["customer_delivery_ready"] = True
    config["customer_delivery_lock"] = {"delivery_unlocked": True}
    pricing_db.update_version(draft["version"]["id"], {"config": config})

    resp = client.get(
        f"/api/v1/projects/{pid}/estimates/{draft['estimate']['id']}/versions/{draft['version']['id']}/proposal-preview"
    )

    assert resp.status_code == 423
    assert resp.json()["error"]["code"] == "http_423"
    assert "explicit final-delivery workflow" in resp.json()["error"]["message"]


def test_generic_estimate_bridge_unknown_project_404(client):
    resp = client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/estimates/generic-draft", json={})
    assert resp.status_code == 404
