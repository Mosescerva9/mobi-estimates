"""Proposal generation, lifecycle, exports, and confidentiality tests."""

from __future__ import annotations

from decimal import Decimal
import re

import pytest

from tests.conftest import prepare_approved_estimate

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
    for fmt in ("json", "md", "html"):
        assert client.get(f"{base}/export.{fmt}").status_code == 409

    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", lambda *args, **kwargs: None)
    issued = client.post(f"{base}/issue")
    assert issued.status_code == 200
    monkeypatch.setattr(service, "_enforce_customer_delivery_lock", real_enforcer)
    assert client.post(f"{base}/accept", json={"notes": "locked"}).status_code == 409
    assert client.post(f"{base}/decline", json={"reason": "locked"}).status_code == 409


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
    snap = get_snapshot(vid)
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
