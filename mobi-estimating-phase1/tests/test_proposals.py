"""Proposal generation, lifecycle, exports, and confidentiality tests."""

from __future__ import annotations

from decimal import Decimal
import re

import pytest

from app.database import get_connection
from tests.conftest import TEST_TENANT_HEADERS, prepare_approved_estimate

# Internal cost/margin/rate/path terms that must NEVER appear in a client proposal.
_LEAK_TERMS = ["direct_cost", "labor_cost", "material_cost", "equipment_cost",
               "subcontract_cost", "other_direct_cost", "loaded_rate",
               "loaded_crew_hour_rate", "gross margin", "margin", "markup", "overhead",
               "profit", "rate", "source", "pricing_basis", "generic_pricing_basis",
               "reviewer", "readiness", "/home/", "api_key", "cost_book"]


@pytest.fixture(autouse=True)
def _simulate_future_owner_delivery_unlock(request, monkeypatch):
    """Keep legacy proposal mechanics tests focused while default tests prove P0 lock.

    The real code now fail-closes because there is no owner-approval persistence
    path. Tests not marked with ``uses_real_delivery_lock`` simulate a future fully
    approved delivery gate so confidentiality/allocation lifecycle behavior remains
    covered without weakening production defaults.
    """
    if request.node.get_closest_marker("uses_real_delivery_lock"):
        return
    monkeypatch.setattr(
        "app.proposals.service._enforce_customer_delivery_lock",
        lambda *args, **kwargs: None,
    )


def _contains_leak_term(text: str, term: str) -> bool:
    if " " in term or "_" in term or term.startswith("/"):
        return term in text
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _create(client, pid, eid, **kw):
    body = {"name": "Proposal", "estimate_id": eid, "client_name": "Acme", **kw}
    return client.post(f"/api/v1/projects/{pid}/proposals", json=body)


@pytest.mark.uses_real_delivery_lock
def test_customer_proposal_creation_locked_without_owner_delivery_approval(client):
    pid, eid, _evid, _final = prepare_approved_estimate(client)

    resp = _create(client, pid, eid, detail_level="trade")

    assert resp.status_code == 409
    assert "delivery gate" in resp.json()["error"]["message"]
    assert client.get(f"/api/v1/projects/{pid}/proposals").json()["items"] == []


@pytest.mark.uses_real_delivery_lock
def test_proposal_delivery_lock_tracks_expected_scope_lineage(client):
    from app import pricing_db
    from app.proposals import service

    _pid, _eid, evid, _final = prepare_approved_estimate(client)
    estimate_version = pricing_db.get_estimate_version(evid)
    assert estimate_version is not None
    line_items = pricing_db.get_line_items(evid)
    expected_scope_ids = sorted({str(line["scope_item_id"]) for line in line_items if line.get("scope_item_id")})

    lock = service._delivery_lock_for_estimate_version(estimate_version)

    assert lock["delivery_unlocked"] is False
    assert lock["expected_scope_item_count"] == len(line_items)
    assert lock["expected_scope_item_ids"] == expected_scope_ids
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert any("cover every expected scope item" in reason for reason in lock["reasons"])


def test_proposal_delivery_evidence_rejects_placeholder_review_metadata():
    from app.proposals import service

    assert service._line_items_have_complete_delivery_evidence([
        {
            "evidence": [{"metadata": {"reviewed": True}}],
        }
    ]) is False
    assert service._line_items_have_complete_delivery_evidence([
        {
            "evidence": [
                {
                    "source_artifact_ref": "customer_plan_sha256_2026",
                    "verified_sheet_number": "A-101",
                    "pdf_page_number": 1,
                    "evidence_type": "plan_note",
                }
            ],
        }
    ]) is True


def test_proposal_delivery_evidence_must_match_line_scope_item_id():
    from app.proposals import service

    evidence = {
        "scope_item_id": "scope-1",
        "source_artifact_ref": "customer_plan_sha256_2026",
        "verified_sheet_number": "A-101",
        "pdf_page_number": 1,
        "evidence_type": "plan_note",
    }
    assert service._line_items_have_complete_delivery_evidence([
        {"scope_item_id": "scope-1", "evidence": [evidence]}
    ]) is True
    assert service._line_items_have_complete_delivery_evidence([
        {"scope_item_id": "scope-2", "evidence": [evidence]}
    ]) is False
    assert service._line_items_have_complete_delivery_evidence([
        {
            "scope_item_id": "scope-1",
            "evidence": [{key: value for key, value in evidence.items() if key != "scope_item_id"}],
        }
    ]) is False


@pytest.mark.uses_real_delivery_lock
def test_proposal_delivery_lock_preserves_test_only_component_metadata(monkeypatch):
    from app.proposals import service

    scope_id = "11111111-1111-4111-8111-111111111111"
    monkeypatch.setattr(
        service.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "components": [
                    {
                        "source": "verified_cost_component",
                        "component_source": "verified_cost_component",
                        "internal_testing_only": True,
                    }
                ],
                "evidence": [{"source": "reviewed_sheet_region"}],
            }
        ],
    )

    lock = service._delivery_lock_for_estimate_version({"id": "version-1", "status": "approved"})

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 1
    assert lock["source_check"]["test_only_sources"] == [
        {
            "scope_item_id": scope_id,
            "kind": "estimate_line_component_source",
            "source": "verified_cost_component",
            "reason": "Source metadata marks this row as test-only scaffolding.",
        }
    ]


@pytest.mark.uses_real_delivery_lock
def test_proposal_delivery_lock_preserves_nested_test_only_metadata(monkeypatch):
    from app.proposals import service

    scope_id = "11111111-1111-4111-8111-111111111112"
    monkeypatch.setattr(
        service.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "source_metadata": {"fixture_only": True},
                "components": [
                    {
                        "source": "verified_cost_component",
                        "component_source": "verified_cost_component",
                        "metadata": {"internal_testing_only": True},
                    }
                ],
                "evidence": [{"source": "reviewed_sheet_region"}],
            }
        ],
    )

    lock = service._delivery_lock_for_estimate_version({"id": "version-1", "status": "approved"})

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 2
    assert {row["source"] for row in lock["source_check"]["test_only_sources"]} == {
        "verified_cost_component",
        "staff_verified_takeoff",
    }


@pytest.mark.uses_real_delivery_lock
@pytest.mark.parametrize(
    ("component_alias", "line_alias"),
    [
        ("is_test_only", "is_fixture"),
        ("is_testing_only", "is_test_only"),
    ],
)
def test_proposal_delivery_lock_preserves_flat_test_only_aliases(monkeypatch, component_alias, line_alias):
    from app.proposals import service

    scope_id = "11111111-1111-4111-8111-111111111118"
    monkeypatch.setattr(
        service.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                line_alias: True,
                "components": [
                    {
                        "source": "supplier_quote_2026",
                        "component_source": "supplier_quote_2026",
                        component_alias: True,
                    }
                ],
                "evidence": [{"source": "reviewed_sheet_region"}],
            }
        ],
    )

    lock = service._delivery_lock_for_estimate_version({"id": "version-1", "status": "approved"})

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 2
    assert {row["source"] for row in lock["source_check"]["test_only_sources"]} == {
        "supplier_quote_2026",
        "staff_verified_takeoff",
    }


@pytest.mark.uses_real_delivery_lock
def test_proposal_delivery_lock_rejects_test_only_evidence_rows(monkeypatch):
    from app.proposals import service

    scope_id = "11111111-1111-4111-8111-111111111113"
    monkeypatch.setattr(
        service.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "components": [{"source": "verified_cost_component"}],
                "evidence": [
                    {
                        "source": "reviewed_sheet_region",
                        "metadata": {"internal_testing_only": True},
                    }
                ],
            }
        ],
    )

    lock = service._delivery_lock_for_estimate_version({"id": "version-1", "status": "approved"})

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["evidence_complete"] is False
    assert any("Complete verified evidence" in reason for reason in lock["reasons"])


@pytest.mark.uses_real_delivery_lock
def test_proposal_delivery_lock_rejects_evidence_without_source(monkeypatch):
    from app.proposals import service

    scope_id = "11111111-1111-4111-8111-111111111114"
    monkeypatch.setattr(
        service.pricing_db,
        "get_line_items",
        lambda version_id: [
            {
                "scope_item_id": scope_id,
                "trade_code": "painting",
                "category_code": "walls",
                "quantity": "10",
                "quantity_basis": "staff_verified_takeoff",
                "quantity_source": "staff_verified_takeoff",
                "components": [{"source": "verified_cost_component"}],
                "evidence": [{"metadata": {"reviewed": True}}],
            }
        ],
    )

    lock = service._delivery_lock_for_estimate_version({"id": "version-1", "status": "approved"})

    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["evidence_complete"] is False


@pytest.mark.uses_real_delivery_lock
def test_existing_proposal_issue_view_and_exports_locked_by_delivery_gate(client, monkeypatch):
    from app.proposals import service

    pid, eid, _evid, _final = prepare_approved_estimate(client)
    real_enforcer = service._enforce_customer_delivery_lock
    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", lambda *args, **kwargs: None)
    body = _create(client, pid, eid, detail_level="line").json()
    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", real_enforcer)
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    base = f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}"

    assert client.get(f"/api/v1/projects/{pid}/proposals").status_code == 409
    issue = client.post(f"{base}/issue")
    assert issue.status_code == 409
    assert "delivery gate" in issue.json()["error"]["message"]
    assert client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}").status_code == 409
    assert client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions").status_code == 409
    assert client.get(base).status_code == 409
    assert client.get(f"{base}/review-events").status_code == 409
    regen = client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/regenerate")
    assert regen.status_code == 409
    assert "delivery gate" in regen.json()["error"]["message"]
    for fmt in ("json", "md", "html"):
        assert client.get(f"{base}/export.{fmt}").status_code == 409

    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", lambda *args, **kwargs: None)
    issued = client.post(f"{base}/issue")
    assert issued.status_code == 200
    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", real_enforcer)
    assert client.post(f"{base}/accept", json={"notes": "locked"}).status_code == 409
    assert client.post(f"{base}/decline", json={"reason": "locked"}).status_code == 409


@pytest.mark.uses_real_delivery_lock
def test_orphaned_proposal_views_fail_closed_without_exportable_version(client, monkeypatch):
    from app.database import get_connection
    from app.proposals import service

    pid, eid, _evid, _final = prepare_approved_estimate(client)
    real_enforcer = service._enforce_customer_delivery_lock
    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", lambda *args, **kwargs: None)
    body = _create(client, pid, eid, detail_level="line").json()
    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", real_enforcer)
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]

    # Simulate a stale/orphaned customer-facing proposal shell whose version row
    # is no longer readable. The API must not expose proposal metadata as a
    # harmless empty collection; it remains a final-estimate delivery surface.
    with get_connection() as conn:
        conn.execute("DELETE FROM proposal_line_items WHERE version_id=?", (vid,))
        conn.execute("DELETE FROM proposal_review_events WHERE version_id=?", (vid,))
        conn.execute("DELETE FROM proposal_snapshots WHERE version_id=?", (vid,))
        conn.execute("DELETE FROM proposal_versions WHERE id=?", (vid,))
        conn.execute("UPDATE proposals SET current_version_id=NULL WHERE id=?", (prop_id,))
        conn.commit()

    detail = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}")
    versions = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions")

    assert detail.status_code == 409
    assert versions.status_code == 409
    assert "no exportable proposal version exists" in detail.text
    assert "no exportable proposal version exists" in versions.text


def test_create_from_approved_estimate_trade_detail(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    resp = _create(client, pid, eid, detail_level="trade")
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"]["total_sell_price"] == final
    lines = client.get(
        f"/api/v1/projects/{pid}/proposals/{body['proposal']['id']}"
        f"/versions/{body['version']['id']}").json()["line_items"]
    # Trade-level: one line per trade, sells reconcile to the estimate final sell.
    assert sum(Decimal(li["sell_price"]) for li in lines) == Decimal(final)
    assert {li["trade_code"] for li in lines} == {"painting", "demo_concrete"}


def test_line_detail_reconciles(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid, detail_level="line").json()
    lines = client.get(
        f"/api/v1/projects/{pid}/proposals/{body['proposal']['id']}"
        f"/versions/{body['version']['id']}").json()["line_items"]
    assert sum(Decimal(li["sell_price"]) for li in lines) == Decimal(final)
    assert len(lines) >= 2


def test_summary_detail_single_line(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid, detail_level="summary").json()
    lines = client.get(
        f"/api/v1/projects/{pid}/proposals/{body['proposal']['id']}"
        f"/versions/{body['version']['id']}").json()["line_items"]
    assert len(lines) == 1
    assert lines[0]["sell_price"] == final


def test_proposal_from_unapproved_estimate_rejected(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    vid = client.get(f"/api/v1/projects/{pid}/estimates").json()["items"]
    # Create a second, unapproved estimate.
    cbv = client.get(f"/api/v1/projects/{pid}/estimates/{eid}").json()
    est2 = client.post(f"/api/v1/projects/{pid}/estimates", json={
        "name": "Unapproved",
        "cost_book_version_id": client.get(
            f"/api/v1/projects/{pid}/estimates/{eid}/versions").json()["items"][0]["cost_book_version_id"],
    }).json()
    resp = _create(client, pid, est2["estimate"]["id"])
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_issue_makes_immutable_with_snapshot(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    issued = client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue").json()
    assert issued["status"] == "issued"
    assert issued["proposal_number"]
    assert len(issued["snapshot_hash"]) == 64
    # Re-issuing an issued version is rejected.
    again = client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    assert again.status_code == 409


def test_proposal_artifacts_carry_tenant_identity_through_issue(client):
    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]

    issued = client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    assert issued.status_code == 200

    with get_connection() as conn:
        proposal = conn.execute("SELECT tenant_id, company_id FROM proposals WHERE id=?", (prop_id,)).fetchone()
        version = conn.execute("SELECT tenant_id, company_id FROM proposal_versions WHERE id=?", (vid,)).fetchone()
        lines = conn.execute("SELECT tenant_id, company_id FROM proposal_line_items WHERE version_id=?", (vid,)).fetchall()
        snapshot = conn.execute("SELECT tenant_id, company_id FROM proposal_snapshots WHERE version_id=?", (vid,)).fetchone()
        events = conn.execute("SELECT tenant_id, company_id FROM proposal_review_events WHERE version_id=?", (vid,)).fetchall()

    expected = (TEST_TENANT_HEADERS["X-Mobi-Tenant-Id"], TEST_TENANT_HEADERS["X-Mobi-Company-Id"])
    assert (proposal["tenant_id"], proposal["company_id"]) == expected
    assert (version["tenant_id"], version["company_id"]) == expected
    assert lines and all((row["tenant_id"], row["company_id"]) == expected for row in lines)
    assert (snapshot["tenant_id"], snapshot["company_id"]) == expected
    assert events and all((row["tenant_id"], row["company_id"]) == expected for row in events)


def test_proposal_listing_ignores_mismatched_tenant_artifact_rows(client):
    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id = body["proposal"]["id"]

    with get_connection() as conn:
        conn.execute(
            "UPDATE proposals SET tenant_id=?, company_id=? WHERE id=?",
            ("other_tenant", "other_company", prop_id),
        )
        conn.commit()

    listed = client.get(f"/api/v1/projects/{pid}/proposals")
    assert listed.status_code == 200
    assert listed.json()["items"] == []


def test_proposal_version_view_fails_closed_on_mismatched_version_identity(client):
    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]

    with get_connection() as conn:
        conn.execute(
            "UPDATE proposal_versions SET tenant_id=?, company_id=? WHERE id=?",
            ("other_tenant", "other_company", vid),
        )
        conn.commit()

    versions = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions")
    assert versions.status_code == 409
    assert "no exportable proposal version exists" in versions.text
    view = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}")
    assert view.status_code == 404


def test_proposal_version_reads_fail_closed_when_proposal_and_version_share_stale_identity(client):
    from app import proposals_db

    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]

    with get_connection() as conn:
        conn.execute(
            "UPDATE proposals SET tenant_id=?, company_id=? WHERE id=?",
            ("other_tenant", "other_company", prop_id),
        )
        conn.execute(
            "UPDATE proposal_versions SET tenant_id=?, company_id=? WHERE id=?",
            ("other_tenant", "other_company", vid),
        )
        conn.commit()

    assert proposals_db.get_version(pid, prop_id, vid) is None
    assert proposals_db.list_versions(prop_id) == []
    assert client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions").status_code == 404
    assert client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}").status_code == 404


def test_proposal_child_reads_filter_mismatched_line_items_and_review_events(client):
    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    assert client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue").status_code == 200

    with get_connection() as conn:
        conn.execute(
            "UPDATE proposal_line_items SET tenant_id=?, company_id=? WHERE version_id=?",
            ("other_tenant", "other_company", vid),
        )
        conn.execute(
            "UPDATE proposal_review_events SET tenant_id=?, company_id=? WHERE version_id=?",
            ("other_tenant", "other_company", vid),
        )
        conn.commit()

    view = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}")
    assert view.status_code == 200
    assert view.json()["line_items"] == []
    events = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/review-events")
    assert events.status_code == 200
    assert events.json()["items"] == []


def test_proposal_review_events_filter_mismatched_project_even_with_matching_tenant(client):
    from app import proposals_db

    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    assert client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue").status_code == 200

    with get_connection() as conn:
        conn.execute(
            "UPDATE proposal_review_events SET project_id=? WHERE version_id=?",
            ("00000000-0000-0000-0000-000000000999", vid),
        )
        conn.commit()

    assert proposals_db.list_review_events(pid, prop_id, vid) == []
    events = client.get(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/review-events")
    assert events.status_code == 200
    assert events.json()["items"] == []


def test_proposal_snapshot_replace_does_not_delete_mismatched_tenant_snapshot(client):
    from app import proposals_db

    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    assert client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue").status_code == 200

    with get_connection() as conn:
        conn.execute(
            "UPDATE proposal_snapshots SET tenant_id=?, company_id=? WHERE version_id=?",
            ("other_tenant", "other_company", vid),
        )
        conn.commit()

    proposals_db.save_snapshot(pid, prop_id, vid, '{"replacement": true}', "0" * 64)

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tenant_id, company_id FROM proposal_snapshots WHERE version_id=? ORDER BY created_at",
            (vid,),
        ).fetchall()

    assert {row["tenant_id"] for row in rows} == {"other_tenant", TEST_TENANT_HEADERS["X-Mobi-Tenant-Id"]}

def test_proposal_artifact_dal_requires_parent_scope_and_blocks_mismatched_parent(client):
    from app import proposals_db

    pid, eid, _evid, _final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    assert client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue").status_code == 200
    wrong_project = "00000000-0000-0000-0000-000000000999"
    wrong_proposal = "00000000-0000-0000-0000-000000000998"

    # Child/version artifact helpers intentionally cannot be called with only a
    # guessed child version ID; the trusted parent route/request scope is required.
    with pytest.raises(TypeError):
        proposals_db.get_version(vid)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        proposals_db.get_line_items(vid)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        proposals_db.get_snapshot(vid)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        proposals_db.list_review_events(vid)  # type: ignore[call-arg]

    assert proposals_db.get_version(wrong_project, prop_id, vid) is None
    assert proposals_db.get_version(pid, wrong_proposal, vid) is None
    assert proposals_db.get_line_items(wrong_project, prop_id, vid) == []
    assert proposals_db.get_snapshot(pid, wrong_proposal, vid) is None
    assert proposals_db.list_review_events(wrong_project, prop_id, vid) == []
    with pytest.raises(PermissionError):
        proposals_db.update_version(wrong_project, prop_id, vid, {"cover_notes": "blocked"})
    with pytest.raises(PermissionError):
        proposals_db.save_snapshot(pid, wrong_proposal, vid, "{}", "0" * 64)



def test_accept_requires_issued(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    # Draft cannot be accepted.
    assert client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/accept").status_code == 409
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    acc = client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/accept",
        json={"notes": "client approved"})
    assert acc.status_code == 200 and acc.json()["status"] == "accepted"


def test_decline_requires_reason(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    assert client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/decline",
        json={}).status_code == 422
    ok = client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/decline",
        json={"reason": "budget"})
    assert ok.status_code == 200 and ok.json()["status"] == "declined"
    assert ok.json()["decline_reason"] == "budget"


def test_regenerate_supersedes_prior_draft(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    regen = client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/regenerate").json()
    assert regen["version"]["version_number"] == 2
    prior = client.get(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}").json()
    assert prior["status"] == "superseded"


def test_regenerate_preserves_accepted_prior(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/accept")
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/regenerate")
    prior = client.get(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}").json()
    assert prior["status"] == "accepted"  # accepted versions are not superseded


def test_exports_have_no_cost_leak(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid, detail_level="line").json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    base = f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}"
    for fmt, ctype in [("json", "application/json"), ("md", "text/markdown"),
                       ("html", "text/html")]:
        resp = client.get(f"{base}/export.{fmt}")
        assert resp.status_code == 200
        assert ctype in resp.headers["content-type"]
        text = resp.text.lower()
        if fmt == "html":
            # Ignore renderer CSS tokens such as the CSS property `margin`; leak checks
            # target customer-visible proposal content and JSON keys.
            text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.S)
        for term in _LEAK_TERMS:
            assert not _contains_leak_term(text, term), f"{fmt} leaked '{term}'"
        # The client-facing total sell price IS present (raw or comma-formatted).
        formatted = f"{Decimal(final):,.2f}"
        assert final in resp.text or formatted in resp.text


def test_snapshot_reproducible(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    issued = client.post(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue").json()
    from app.proposals_db import get_snapshot
    import hashlib
    snap = get_snapshot(pid, prop_id, vid)
    assert snap is not None
    assert hashlib.sha256(snap["snapshot_json"].encode()).hexdigest() == snap["snapshot_hash"]
    assert issued["snapshot_hash"] == snap["snapshot_hash"]


def test_review_history_append_only(client):
    pid, eid, evid, final = prepare_approved_estimate(client)
    body = _create(client, pid, eid).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/issue")
    client.post(f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/accept")
    events = client.get(
        f"/api/v1/projects/{pid}/proposals/{prop_id}/versions/{vid}/review-events").json()["items"]
    actions = [e["action"] for e in events]
    assert "issue" in actions and "accepted" in actions


def test_ownership_enforced(client):
    pid_a, eid_a, _, _ = prepare_approved_estimate(client)
    body = _create(client, pid_a, eid_a).json()
    prop_id, vid = body["proposal"]["id"], body["version"]["id"]
    pid_b, _, _, _ = prepare_approved_estimate(client)
    # Project B cannot see project A's proposal version.
    assert client.get(
        f"/api/v1/projects/{pid_b}/proposals/{prop_id}/versions/{vid}").status_code == 404


def test_unknown_project_404(client):
    assert client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/proposals").status_code == 404
