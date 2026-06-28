"""Sheet listing, detail, verification, and artifact-serving endpoint tests."""

from __future__ import annotations

from tests.conftest import make_sheet_pdf, upload_and_process


def _five_page_pdf():
    return make_sheet_pdf(
        [{"number": f"A-10{i}", "title": "PLAN"} for i in range(1, 6)]
    )


def test_sheet_listing_order(client):
    pid, _ = upload_and_process(client, _five_page_pdf())
    items = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    assert [s["pdf_page_number"] for s in items] == [1, 2, 3, 4, 5]


def test_sheet_pagination(client):
    pid, _ = upload_and_process(client, _five_page_pdf())
    page1 = client.get(f"/api/v1/projects/{pid}/sheets?limit=2&offset=0").json()
    page2 = client.get(f"/api/v1/projects/{pid}/sheets?limit=2&offset=2").json()
    assert page1["total"] == 5
    assert [s["pdf_page_number"] for s in page1["items"]] == [1, 2]
    assert [s["pdf_page_number"] for s in page2["items"]] == [3, 4]


def test_sheet_detail_endpoint(client):
    pid, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "FLOOR PLAN"}])
    )
    sid = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]["sheet_id"]
    detail = client.get(f"/api/v1/projects/{pid}/sheets/{sid}").json()
    assert detail["sheet_id"] == sid
    assert detail["pdf_page_number"] == 1
    assert "artifacts" in detail
    # Raw filesystem paths must never be exposed.
    assert "full_image_path" not in detail
    assert "/data/" not in str(detail.get("artifacts"))


def test_sheet_ownership_validation(client):
    pid_a, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "PLAN"}]),
        project_name="A",
    )
    pid_b, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "B-101", "title": "PLAN"}]),
        project_name="B",
    )
    sheet_b = client.get(f"/api/v1/projects/{pid_b}/sheets").json()["items"][0]
    # Requesting project B's sheet under project A must 404.
    resp = client.get(f"/api/v1/projects/{pid_a}/sheets/{sheet_b['sheet_id']}")
    assert resp.status_code == 404


def test_unknown_sheet_returns_404(client):
    pid, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "PLAN"}])
    )
    resp = client.get(
        f"/api/v1/projects/{pid}/sheets/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def test_human_verification_update(client):
    pid, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "FLOOR PLAN"}])
    )
    sid = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]["sheet_id"]
    resp = client.patch(
        f"/api/v1/projects/{pid}/sheets/{sid}/verification",
        json={
            "verified_sheet_number": "A-101",
            "verified_sheet_title": "FIRST FLOOR PLAN",
            "review_notes": "Confirmed against title block",
            "review_status": "verified",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified_sheet_number"] == "A-101"
    assert body["verified_sheet_title"] == "FIRST FLOOR PLAN"
    assert body["review_status"] == "verified"
    assert body["requires_review"] is False
    assert body["verified_at"] is not None


def test_detected_metadata_preserved_after_verification(client):
    # Detector finds A-101; reviewer overrides the verified value to A-102.
    pid, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "FLOOR PLAN"}])
    )
    sid = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]["sheet_id"]
    detected_before = client.get(
        f"/api/v1/projects/{pid}/sheets/{sid}"
    ).json()["detected_sheet_number"]
    resp = client.patch(
        f"/api/v1/projects/{pid}/sheets/{sid}/verification",
        json={"verified_sheet_number": "A-102", "review_status": "verified"},
    ).json()
    # Detected value is preserved; verified value is the corrected one.
    assert resp["detected_sheet_number"] == detected_before == "A-101"
    assert resp["verified_sheet_number"] == "A-102"


def test_verification_ownership_validation(client):
    pid_a, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "PLAN"}]),
        project_name="A",
    )
    pid_b, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "B-101", "title": "PLAN"}]),
        project_name="B",
    )
    sheet_b = client.get(f"/api/v1/projects/{pid_b}/sheets").json()["items"][0]
    resp = client.patch(
        f"/api/v1/projects/{pid_a}/sheets/{sheet_b['sheet_id']}/verification",
        json={"verified_sheet_number": "X", "review_status": "verified"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Artifact serving safety
# ---------------------------------------------------------------------------
def test_missing_artifact_response(client):
    # A blank page still produces image/thumbnail artifacts, but a *failed* page
    # would not. Here we delete the thumbnail file and expect a clean 404.
    from app.services import storage
    from uuid import UUID

    pid, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "PLAN"}])
    )
    sid = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]["sheet_id"]
    thumb = storage.page_dir(UUID(pid), 1) / "thumbnail.png"
    thumb.unlink()
    resp = client.get(f"/api/v1/projects/{pid}/sheets/{sid}/thumbnail")
    assert resp.status_code == 404


def test_unsafe_artifact_path_rejected(client):
    # Inject a traversal path into the DB and confirm the resolver rejects it.
    from uuid import UUID
    from app.database import get_connection

    pid, _ = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "PLAN"}])
    )
    sid = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]["sheet_id"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE sheets SET thumbnail_path = ? WHERE id = ?",
            ("../../../../etc/passwd", sid),
        )
        conn.commit()
    resp = client.get(f"/api/v1/projects/{pid}/sheets/{sid}/thumbnail")
    assert resp.status_code == 400
    assert resp.json()["error"]["message"] == "Unsafe artifact path"
