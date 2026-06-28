"""Cost-book versioning, immutability, and CSV-import API tests."""

from __future__ import annotations


def _book(client):
    return client.post("/api/v1/cost-books", json={"name": "Book"}).json()["id"]


def _draft(client, cbid):
    return client.post(f"/api/v1/cost-books/{cbid}/versions", json={
        "version_label": "v1", "effective_date": "2026-01-01",
        "pricing_date": "2026-06-01"}).json()["id"]


def test_create_cost_book_and_version(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    v = client.get(f"/api/v1/cost-books/{cbid}/versions/{vid}").json()
    assert v["status"] == "draft"


def test_edit_draft_then_publish_immutable(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    base = f"/api/v1/cost-books/{cbid}/versions/{vid}"
    src = client.post(f"{base}/sources", json={"source_type": "contractor_rate",
        "source_name": "F", "effective_date": "2026-01-01", "verified": True}).json()
    client.post(f"{base}/assemblies", json={"trade_code": "painting",
        "assembly_code": "A", "name": "a", "scope_category": "interior_walls",
        "input_unit": "SF", "components": [{"component_type": "other_direct",
        "cost_item_ref": "O", "quantity_factor": "1"}]})
    pub = client.post(f"{base}/publish")
    assert pub.status_code == 200 and pub.json()["status"] == "published"
    # Mutating a published version is rejected.
    blocked = client.post(f"{base}/labor-rates", json={"classification": "X",
        "trade_code": "painting", "rate_type": "manual_all_in",
        "manual_all_in_rate": "10", "effective_date": "2026-01-01", "source_id": src["id"]})
    assert blocked.status_code == 409


def test_publish_rejected_with_invalid_assembly(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    base = f"/api/v1/cost-books/{cbid}/versions/{vid}"
    # Assembly with no components → publish validation error.
    client.post(f"{base}/assemblies", json={"trade_code": "painting",
        "assembly_code": "EMPTY", "name": "e", "scope_category": "interior_walls",
        "input_unit": "SF", "components": []})
    resp = client.post(f"{base}/publish")
    assert resp.status_code == 409


def test_new_draft_from_published_book(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    base = f"/api/v1/cost-books/{cbid}/versions/{vid}"
    client.post(f"{base}/assemblies", json={"trade_code": "painting",
        "assembly_code": "A", "name": "a", "scope_category": "interior_walls",
        "input_unit": "SF", "components": [{"component_type": "other_direct",
        "cost_item_ref": "O", "quantity_factor": "1"}]})
    client.post(f"{base}/publish")
    # A new draft version can still be created on the same book.
    v2 = client.post(f"/api/v1/cost-books/{cbid}/versions", json={
        "version_label": "v2", "effective_date": "2026-01-01",
        "pricing_date": "2026-06-01"})
    assert v2.status_code == 201 and v2.json()["status"] == "draft"


def test_archive_version(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    resp = client.post(f"/api/v1/cost-books/{cbid}/versions/{vid}/archive")
    assert resp.json()["status"] == "archived"


def test_unknown_cost_book_404(client):
    assert client.get(
        "/api/v1/cost-books/00000000-0000-0000-0000-000000000000").status_code == 404


# ---- CSV import ----------------------------------------------------------
def test_csv_preview_valid(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    csv = ("classification,trade_code,loaded_rate,effective_date,source_id\n"
           "PAINTER,painting,50.00,2026-01-01,src-1\n")
    resp = client.post(
        f"/api/v1/cost-books/{cbid}/versions/{vid}/imports/labor_rates/preview", content=csv)
    body = resp.json()
    assert body["valid"] is True and body["row_count"] == 1


def test_csv_preview_invalid_decimal_and_duplicate(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    csv = ("classification,trade_code,loaded_rate,effective_date,source_id\n"
           "PAINTER,painting,NOTANUM,2026-01-01,s\n"
           "PAINTER,painting,40.00,2026-01-01,s\n")  # invalid decimal + duplicate id
    body = client.post(
        f"/api/v1/cost-books/{cbid}/versions/{vid}/imports/labor_rates/preview",
        content=csv).json()
    assert body["valid"] is False
    assert len(body["errors"]) >= 2


def test_csv_unknown_column_rejected(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    csv = ("classification,trade_code,loaded_rate,effective_date,source_id,evil\n"
           "PAINTER,painting,50.00,2026-01-01,s,x\n")
    body = client.post(
        f"/api/v1/cost-books/{cbid}/versions/{vid}/imports/labor_rates/preview",
        content=csv).json()
    assert body["valid"] is False


def test_csv_atomic_commit(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    csv = ("classification,trade_code,loaded_rate,effective_date,source_id\n"
           "PAINTER,painting,50.00,2026-01-01,s\nGLAZIER,painting,55.00,2026-01-01,s\n")
    resp = client.post(
        f"/api/v1/cost-books/{cbid}/versions/{vid}/imports/labor_rates/commit", content=csv)
    assert resp.status_code == 200 and resp.json()["imported"] == 2
    listed = client.get(f"/api/v1/cost-books/{cbid}/versions/{vid}/labor-rates").json()
    assert len(listed["items"]) == 2


def test_csv_invalid_file_imports_nothing(client):
    cbid = _book(client)
    vid = _draft(client, cbid)
    csv = ("classification,trade_code,loaded_rate,effective_date,source_id\n"
           "PAINTER,painting,BAD,2026-01-01,s\n")
    resp = client.post(
        f"/api/v1/cost-books/{cbid}/versions/{vid}/imports/labor_rates/commit", content=csv)
    assert resp.status_code == 422
    listed = client.get(f"/api/v1/cost-books/{cbid}/versions/{vid}/labor-rates").json()
    assert listed["items"] == []  # nothing imported
