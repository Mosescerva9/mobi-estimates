"""Processing pipeline and endpoint tests."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.services import storage
from tests.conftest import TEST_TENANT_HEADERS, make_sheet_pdf, upload_and_process


# ---------------------------------------------------------------------------
# Happy path: single + multi-page
# ---------------------------------------------------------------------------
def test_process_single_page(client):
    pid, resp = upload_and_process(
        client, make_sheet_pdf([{"number": "A-101", "title": "FLOOR PLAN"}])
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_status"] == "succeeded"
    assert body["project_status"] == "ready_for_review"


def test_process_multipage(client, sheet_pdf_bytes):
    pid, resp = upload_and_process(client, sheet_pdf_bytes)
    status = client.get(f"/api/v1/projects/{pid}/processing-status").json()
    assert status["pages_discovered"] == 2
    assert status["pages_completed"] == 2
    assert status["pages_failed"] == 0


def test_each_page_has_db_record(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    sheets = client.get(f"/api/v1/projects/{pid}/sheets").json()
    assert sheets["total"] == 2
    assert [s["pdf_page_number"] for s in sheets["items"]] == [1, 2]


def test_artifacts_created_on_disk(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    sheets = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    for s in sheets:
        detail = client.get(
            f"/api/v1/projects/{pid}/sheets/{s['sheet_id']}"
        ).json()
        # Raw filesystem paths are never exposed; artifacts are reachable only
        # through the controlled endpoints.
        assert "full_image_path" not in detail
        assert detail["artifacts"]["image_available"] is True
        assert detail["artifacts"]["thumbnail_available"] is True
        assert detail["artifacts"]["text_available"] is True


def test_text_extraction_and_artifact(client):
    pid, _ = upload_and_process(
        client,
        make_sheet_pdf(
            [{"number": "A-101", "title": "FLOOR PLAN",
              "body": "ROOM FINISH SCHEDULE\nPaint all gypsum walls."}]
        ),
    )
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    assert sheet["text_layer_quality"] in {
        "low_information_text_layer",
        "usable_text_layer",
    }
    assert "text_extraction" in sheet["recommended_extraction_routes"] or "vision" in sheet["recommended_extraction_routes"]
    detail = client.get(
        f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}"
    ).json()
    assert detail["text_layer_quality"] == sheet["text_layer_quality"]
    assert detail["recommended_extraction_routes"] == sheet["recommended_extraction_routes"]
    assert detail["text_char_count"] > 0
    # The on-disk text artifact contains the embedded text.
    text_file = storage.resolve_within_data_root(
        storage.relative_to_data_root(
            storage.page_dir(
                _uuid(pid),
                1,
                tenant_id=TEST_TENANT_HEADERS["X-Mobi-Tenant-Id"],
                company_id=TEST_TENANT_HEADERS["X-Mobi-Company-Id"],
            ) / "text.txt"
        )
    )
    assert "FINISH SCHEDULE" in text_file.read_text(encoding="utf-8")


def test_full_and_thumbnail_images(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    sid = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]["sheet_id"]
    img = client.get(f"/api/v1/projects/{pid}/sheets/{sid}/image")
    thumb = client.get(f"/api/v1/projects/{pid}/sheets/{sid}/thumbnail")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/png"
    assert img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(thumb.content) < len(img.content)


def test_manifest_created(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    manifest_path = storage.processed_dir(
        _uuid(pid),
        tenant_id=TEST_TENANT_HEADERS["X-Mobi-Tenant-Id"],
        company_id=TEST_TENANT_HEADERS["X-Mobi-Company-Id"],
    ) / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["project_id"] == pid
    assert len(manifest["sheets"]) == 2
    # No machine-specific absolute paths in the manifest.
    raw = manifest_path.read_text(encoding="utf-8")
    assert str(settings.data_root) not in raw


def test_page_dimensions_and_rotation(client):
    pid, _ = upload_and_process(
        client,
        make_sheet_pdf(
            [
                {"number": "A-101", "title": "PLAN", "width": 612, "height": 792},
                {"number": "A-102", "title": "PLAN", "rotation": 90},
            ]
        ),
    )
    sheets = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    d1 = client.get(f"/api/v1/projects/{pid}/sheets/{sheets[0]['sheet_id']}").json()
    d2 = client.get(f"/api/v1/projects/{pid}/sheets/{sheets[1]['sheet_id']}").json()
    assert round(d1["page_width_points"]) == 612
    assert round(d1["page_height_points"]) == 792
    assert d2["rotation"] == 90


def test_mixed_page_sizes(client):
    pid, _ = upload_and_process(
        client,
        make_sheet_pdf(
            [
                {"number": "A-101", "title": "PLAN", "width": 612, "height": 792},
                {"number": "A-102", "title": "PLAN", "width": 2448, "height": 1584},
            ]
        ),
    )
    sheets = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    widths = {
        round(
            client.get(
                f"/api/v1/projects/{pid}/sheets/{s['sheet_id']}"
            ).json()["page_width_points"]
        )
        for s in sheets
    }
    assert widths == {612, 2448}


def test_blank_page_requires_ocr(client):
    pid, _ = upload_and_process(client, make_sheet_pdf([{"blank": True}]))
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    assert sheet["requires_ocr"] is True
    assert sheet["requires_review"] is True


def test_image_only_page_requires_ocr(client):
    pid, _ = upload_and_process(client, make_sheet_pdf([{"image_only": True}]))
    sheet = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"][0]
    assert sheet["requires_ocr"] is True


def test_duplicate_page_detection(client):
    # Two identical pages -> the second is flagged as a duplicate of the first.
    spec = {"number": "A-101", "title": "FLOOR PLAN",
            "body": "IDENTICAL CONTENT"}
    pid, _ = upload_and_process(client, make_sheet_pdf([dict(spec), dict(spec)]))
    sheets = client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    assert sheets[0]["is_duplicate"] is False
    assert sheets[1]["is_duplicate"] is True
    assert sheets[1]["duplicate_of_sheet_id"] == sheets[0]["sheet_id"]


def test_page_checksum_stable_across_reprocess(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    before = {
        s["pdf_page_number"]: client.get(
            f"/api/v1/projects/{pid}/sheets/{s['sheet_id']}"
        ).json()["page_sha256"]
        for s in client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    }
    client.post(f"/api/v1/projects/{pid}/process", json={"force": True})
    after = {
        s["pdf_page_number"]: client.get(
            f"/api/v1/projects/{pid}/sheets/{s['sheet_id']}"
        ).json()["page_sha256"]
        for s in client.get(f"/api/v1/projects/{pid}/sheets").json()["items"]
    }
    assert before == after


# ---------------------------------------------------------------------------
# Status / lifecycle
# ---------------------------------------------------------------------------
def test_processing_status_progress(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    status = client.get(f"/api/v1/projects/{pid}/processing-status").json()
    assert status["project_status"] == "ready_for_review"
    assert status["job_status"] == "succeeded"
    assert status["started_at"] is not None
    assert status["completed_at"] is not None
    assert status["duration_ms"] is not None


def test_invalid_project_id_process(client):
    resp = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/process"
    )
    assert resp.status_code == 404


def test_missing_original_pdf(client, sheet_pdf_bytes):
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "X"},
        files={"plan": ("plans.pdf", sheet_pdf_bytes, "application/pdf")},
    ).json()["project_id"]
    # Remove the stored original PDF before processing.
    (storage.project_dir(
        _uuid(pid),
        tenant_id=TEST_TENANT_HEADERS["X-Mobi-Tenant-Id"],
        company_id=TEST_TENANT_HEADERS["X-Mobi-Company-Id"],
    ) / "original.pdf").unlink()
    resp = client.post(f"/api/v1/projects/{pid}/process")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_duplicate_processing_request_rejected(client, sheet_pdf_bytes):
    pid, first = upload_and_process(client, sheet_pdf_bytes)
    assert first.status_code == 202
    # Already processed; a second non-forced request is rejected.
    second = client.post(f"/api/v1/projects/{pid}/process")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_forced_reprocessing_succeeds(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    resp = client.post(f"/api/v1/projects/{pid}/process", json={"force": True})
    assert resp.status_code == 202
    assert resp.json()["job_status"] == "succeeded"


def test_idempotent_reprocessing_no_duplicate_sheets(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    for _ in range(3):
        client.post(f"/api/v1/projects/{pid}/process", json={"force": True})
    total = client.get(f"/api/v1/projects/{pid}/sheets").json()["total"]
    assert total == 2  # never doubles


def test_persistence_across_restart(client, sheet_pdf_bytes):
    pid, _ = upload_and_process(client, sheet_pdf_bytes)
    from tests.conftest import TEST_TENANT_HEADERS
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client2:
        sheets = client2.get(f"/api/v1/projects/{pid}/sheets", headers=TEST_TENANT_HEADERS).json()
    assert sheets["total"] == 2


def _uuid(value: str):
    from uuid import UUID

    return UUID(value)
