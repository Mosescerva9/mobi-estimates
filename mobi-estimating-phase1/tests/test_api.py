"""HTTP-level tests for the FastAPI application."""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.services import storage
from tests.conftest import TEST_TENANT_HEADERS, upload


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------
def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": settings.app_version}


def test_health_endpoint_versioned(client):
    assert client.get("/api/v1/health").status_code == 200


def test_readiness_endpoint(client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["database"] is True
    assert body["checks"]["upload_dir"] is True


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------
def test_valid_pdf_upload(client, valid_pdf_bytes):
    resp = upload(client, valid_pdf_bytes)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "uploaded"
    assert body["page_count"] == 1
    assert body["original_file_name"] == "plans.pdf"
    assert len(body["file_sha256"]) == 64
    assert body["file_size_bytes"] == len(valid_pdf_bytes)


def test_multipage_pdf_upload(client, multipage_pdf_bytes):
    resp = upload(client, multipage_pdf_bytes)
    assert resp.status_code == 201
    assert resp.json()["page_count"] == 3


def test_uploaded_file_is_stored_on_disk(client, valid_pdf_bytes):
    resp = upload(client, valid_pdf_bytes)
    project_id = resp.json()["project_id"]
    stored = storage.project_dir(
        project_id,
        tenant_id=TEST_TENANT_HEADERS["X-Mobi-Tenant-Id"],
        company_id=TEST_TENANT_HEADERS["X-Mobi-Company-Id"],
    ) / "original.pdf"
    assert stored.exists()
    assert stored.read_bytes() == valid_pdf_bytes


def test_sqlite_record_created(client, valid_pdf_bytes):
    import sqlite3

    resp = upload(client, valid_pdf_bytes)
    project_id = resp.json()["project_id"]
    conn = sqlite3.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT id, status, page_count FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[1] == "uploaded"
    assert row[2] == 1


def test_invalid_file_extension(client):
    resp = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "X"},
        files={"plan": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_media_type"


def test_invalid_mime_type(client, valid_pdf_bytes):
    # Correct .pdf extension but a clearly non-PDF content type.
    resp = client.post(
        "/api/v1/projects/upload",
        data={"project_name": "X"},
        files={"plan": ("plans.pdf", valid_pdf_bytes, "image/png")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_media_type"


def test_corrupted_pdf(client, corrupted_pdf_bytes):
    resp = upload(client, corrupted_pdf_bytes)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_empty_pdf(client):
    resp = upload(client, b"")
    assert resp.status_code == 400
    assert "empty" in resp.json()["error"]["message"].lower()


def test_non_pdf_signature(client):
    # .pdf extension and an accepted octet-stream type, but wrong magic bytes.
    resp = upload(client, b"NOTAPDFcontent", content_type="application/octet-stream")
    assert resp.status_code == 400
    assert "signature" in resp.json()["error"]["message"].lower()


def test_encrypted_pdf_rejected(client, encrypted_pdf_bytes):
    resp = upload(client, encrypted_pdf_bytes)
    assert resp.status_code == 400
    assert "password" in resp.json()["error"]["message"].lower()


def test_oversized_file(client, valid_pdf_bytes):
    original = settings.max_upload_bytes
    settings.max_upload_bytes = 10  # bytes
    try:
        resp = upload(client, valid_pdf_bytes)
    finally:
        settings.max_upload_bytes = original
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


def test_missing_project_name(client, valid_pdf_bytes):
    resp = client.post(
        "/api/v1/projects/upload",
        files={"plan": ("plans.pdf", valid_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_duplicate_file_detection(client, valid_pdf_bytes):
    first = upload(client, valid_pdf_bytes)
    assert first.status_code == 201
    second = upload(client, valid_pdf_bytes, project_name="Another")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------
def test_project_status_response(client, valid_pdf_bytes):
    project_id = upload(client, valid_pdf_bytes).json()["project_id"]
    resp = client.get(f"/api/v1/projects/{project_id}/status", headers=TEST_TENANT_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {
        "project_id", "name", "status", "original_file_name", "page_count",
        "file_sha256", "file_size_bytes", "created_at", "updated_at",
        "error_message",
    }
    assert expected_keys <= set(body.keys())
    assert body["project_id"] == project_id


def test_unknown_project_id(client):
    resp = client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/status"
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_malformed_project_id(client):
    resp = client.get("/api/v1/projects/not-a-uuid/status")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
def test_valid_status_transition(client, valid_pdf_bytes):
    project_id = upload(client, valid_pdf_bytes).json()["project_id"]
    resp = client.patch(
        f"/api/v1/projects/{project_id}/status",
        data={"new_status": "processing"},
        headers=TEST_TENANT_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"


def test_invalid_status_transition(client, valid_pdf_bytes):
    project_id = upload(client, valid_pdf_bytes).json()["project_id"]
    # uploaded -> complete is not allowed.
    resp = client.patch(
        f"/api/v1/projects/{project_id}/status",
        data={"new_status": "complete"},
        headers=TEST_TENANT_HEADERS,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_transition_unknown_project(client):
    resp = client.patch(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/status",
        data={"new_status": "processing"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def test_record_persists_across_clients(client, valid_pdf_bytes, tmp_path: Path):
    project_id = upload(client, valid_pdf_bytes).json()["project_id"]
    # Re-open a fresh client against the same db/upload paths.
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client2:
        resp = client2.get(f"/api/v1/projects/{project_id}/status", headers=TEST_TENANT_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["project_id"] == project_id
