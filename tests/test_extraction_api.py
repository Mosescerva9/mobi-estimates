"""Phase 3 API surface tests (trades, scope-item listing/detail, errors)."""

from __future__ import annotations

import json

from tests.conftest import prepare_verified_project


def test_list_trades(client):
    body = client.get("/api/v1/trades").json()
    codes = {t["trade_code"] for t in body["trades"]}
    assert {"painting", "demo_concrete"} <= codes
    painting = next(t for t in body["trades"] if t["trade_code"] == "painting")
    assert painting["enabled"] is True
    assert "interior_walls" in painting["supported_categories"]


def test_trade_detail(client):
    body = client.get("/api/v1/trades/painting").json()
    assert body["trade_code"] == "painting"
    assert body["schema_version"] == "1.0"
    assert "SF" in body["supported_units"]


def test_unknown_trade_detail_404(client):
    assert client.get("/api/v1/trades/unobtanium").status_code == 404


def test_scope_item_filters_across_trades(client):
    pid = prepare_verified_project(client)
    client.post(f"/api/v1/projects/{pid}/trades/painting/extractions", json={})
    client.post(f"/api/v1/projects/{pid}/trades/demo_concrete/extractions", json={})

    painting = client.get(f"/api/v1/projects/{pid}/scope-items?trade_code=painting").json()
    concrete = client.get(f"/api/v1/projects/{pid}/scope-items?trade_code=demo_concrete").json()
    all_items = client.get(f"/api/v1/projects/{pid}/scope-items").json()
    assert painting["total"] == 2
    assert concrete["total"] == 1
    assert all_items["total"] == 3


def test_scope_item_category_filter(client):
    pid = prepare_verified_project(client)
    client.post(f"/api/v1/projects/{pid}/trades/painting/extractions", json={})
    filtered = client.get(
        f"/api/v1/projects/{pid}/scope-items?category=door_frames"
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["category_code"] == "door_frames"


def test_scope_item_pagination(client):
    pid = prepare_verified_project(client)
    client.post(f"/api/v1/projects/{pid}/trades/painting/extractions", json={})
    page = client.get(f"/api/v1/projects/{pid}/scope-items?limit=1&offset=0").json()
    assert page["total"] == 2
    assert len(page["items"]) == 1


def test_scope_item_detail_has_no_filesystem_paths(client):
    pid = prepare_verified_project(client)
    client.post(f"/api/v1/projects/{pid}/trades/painting/extractions", json={})
    item = client.get(f"/api/v1/projects/{pid}/scope-items?trade_code=painting").json()["items"][0]
    detail = client.get(f"/api/v1/projects/{pid}/scope-items/{item['id']}")
    raw = detail.text
    # No absolute paths or data-root leakage.
    assert "/home/" not in raw
    assert "/uploads/" not in raw
    assert "original.pdf" not in raw
    body = detail.json()
    assert body["evidence"][0]["verified_sheet_number"] == "A-101"


def test_structured_error_on_unknown_project(client):
    resp = client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/scope-items"
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_invalid_uuid_returns_422(client):
    assert client.get("/api/v1/projects/not-a-uuid/scope-items").status_code == 422


def test_unknown_run_404(client):
    pid = prepare_verified_project(client)
    resp = client.get(
        f"/api/v1/projects/{pid}/trades/painting/extractions/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


def test_unknown_scope_item_404(client):
    pid = prepare_verified_project(client)
    resp = client.get(
        f"/api/v1/projects/{pid}/scope-items/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


def test_painting_prompts_contain_safety_instructions(client):
    """Every painting production prompt must keep its critical safety rules."""
    from app.trades.painting.definition import PaintingTradeModule

    module = PaintingTradeModule()
    required = [
        "Do NOT calculate prices",
        "Do NOT calculate derived quantities",
        "Do NOT infer",
        "Cite every scope item",
        "Return null when information is absent",
    ]
    for task in ("sheet_classifier", "schedule_extractor", "notes_extractor",
                 "scope_extractor"):
        prompt = module.get_prompt(task)
        for phrase in required:
            assert phrase in prompt, f"{task} missing: {phrase}"
