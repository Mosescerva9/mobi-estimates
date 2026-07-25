"""Selected-sheet OpenTakeoff execution over a >max_pages joined packet.

The accepted authoritative packet can exceed the pinned OpenTakeoff MCP's
``max_pages`` (250) — the sheets/verification pipeline still tracks a real
per-page sheet register for the whole packet, but a full-document measurement
would be rejected by the runtime's whole-document safety cap before any
provider work. These tests cover the fix: at measurement time, the worker
extracts a bounded, verified single-page PDF for JUST the confirmed
scale_sheet_id/scale_page_number and runs the real MCP against that, while
canonical evidence keeps the ORIGINAL engine project/document, sheet_id, and
packet page number — never the temp extract's own (page 1) identity.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID, uuid4

import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient

from app import database
from app.config import settings
from app.main import create_app
from app.services import storage
from app.takeoff.mcp_runtime import OpenTakeoffRuntimeConfig
from app.takeoff.worker_api import (
    OpenTakeoffWorkerApiService,
    WorkerApiError,
    extract_scale_page_pdf,
)
import app.routers_opentakeoff_worker as worker_router

API_KEY = "test-worker-api-key"

# Beyond the pinned MCP's max_pages=250, so a whole-document measurement of this
# packet is exactly the controlled failure this fix resolves.
LARGE_PACKET_PAGES = 302
SELECTED_PAGE = 282


def _headers(tenant_id: str, company_id: str, *, role: str = "estimator") -> dict[str, str]:
    return {
        "X-API-Key": API_KEY,
        "X-Mobi-Tenant-Id": tenant_id,
        "X-Mobi-Company-Id": company_id,
        "X-Mobi-Actor-Role": role,
        "X-Mobi-Actor-Id": "staff-user-1",
    }


def _build_synthetic_packet(path: Path, num_pages: int) -> None:
    """Build a deterministic multi-page PDF. measure_line/measure_polygon compute
    purely from the caller's points and the sheet's confirmed units-per-px (see
    opentakeoff-mcp Session.measureLine/measurePolygon) — never from a page's own
    vector content — so a blank synthetic page measures identically to a real one.
    """
    doc = fitz.open()
    try:
        for _ in range(num_pages):
            doc.new_page(width=612, height=792)
        doc.save(path)
    finally:
        doc.close()


@pytest.fixture()
def worker_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "worker-api.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "api_key", API_KEY)
    database.init_db()
    service = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", service)
    client = TestClient(create_app())
    yield client, service, tmp_path


def _seed_large_packet_project(*, tenant_id: str, company_id: str, num_pages: int = LARGE_PACKET_PAGES) -> UUID:
    project_id = uuid4()
    dest = storage.project_dir(project_id, tenant_id=tenant_id, company_id=company_id) / "joined_packet.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _build_synthetic_packet(dest, num_pages)
    stored_file_path = storage.relative_to_data_root(dest)
    database.create_project(
        project_id=project_id,
        name="Joined packet fixture",
        contractor_name="Mobi test",
        original_file_name=dest.name,
        stored_file_path=stored_file_path,
        status="uploaded",
        page_count=num_pages,
        file_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        file_size_bytes=dest.stat().st_size,
        tenant_id=tenant_id,
        company_id=company_id,
    )
    return project_id


def _seed_sheet(project_id: UUID, *, page_number: int, tenant_id: str, company_id: str) -> UUID:
    sheet_id = uuid4()
    database.insert_sheet(
        {
            "id": str(sheet_id),
            "project_id": str(project_id),
            "job_id": None,
            "pdf_page_number": page_number,
            "page_index": page_number - 1,
            "detected_sheet_number": f"A{page_number:03d}",
            "verified_sheet_number": "A101" if page_number == SELECTED_PAGE else None,
            "detected_sheet_title": "Joined packet sheet",
            "verified_sheet_title": None,
            "detection_confidence": 1.0,
            "requires_review": 0,
            "requires_ocr": 0,
            "text_char_count": 0,
            "page_width_points": None,
            "page_height_points": None,
            "rotation": 0,
            "page_sha256": None,
            "duplicate_of_sheet_id": None,
            "full_image_path": None,
            "thumbnail_path": None,
            "text_path": None,
            "processing_status": "completed",
            "processing_error": None,
            "review_status": "verified",
            "review_notes": None,
            "verified_at": None,
        }
    )
    return sheet_id


def _create_line_job(client: TestClient, tenant_id: str, company_id: str, project_id: UUID, *, idem: str):
    return client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_line",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "condition": "RUNTIME-LINE",
            "default_description": "Verified sheet A101 conduit run",
            "idempotency_key": idem,
            "requested_by": "staff-user-1",
        },
    )


def _confirm_scale(
    client: TestClient, tenant_id: str, company_id: str, job_id: str, sheet_id: UUID, *, page_number: int
):
    return client.post(
        f"/internal/takeoff/jobs/{job_id}/confirm-scale",
        headers=_headers(tenant_id, company_id),
        json={
            "sheet_id": str(sheet_id),
            "page_number": page_number,
            "scale_source": "printed dimension",
            "scale_label": "calibrated",
            "units_per_px": 0.1,
        },
    )


def _measure_line(client: TestClient, tenant_id: str, company_id: str, job_id: str):
    # 100px line at units_per_px=0.1 -> a deterministic 10.0 LF, independent of
    # the (blank) synthetic page's own content.
    return client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[0, 0], [100, 0]]}, "condition": "RUNTIME-LINE"},
    )


def _no_leftover_extraction_temp_dirs(temp_root: Path) -> bool:
    return not any(p.name.startswith("mobi-opentakeoff-page-") for p in temp_root.iterdir())


# ---------------------------------------------------------------------------
# B1: 302-page source + selected page 282 (verified A101) succeeds.
# ---------------------------------------------------------------------------
def test_selected_page_of_large_packet_measures_successfully(worker_client):
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="a101-282")
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]

    scale = _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE)
    assert scale.status_code == 200, scale.text

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 200, measured.text
    job = measured.json()["job"]
    assert job["status"] == "awaiting_review"
    assert "[]" not in job["evidence_ids"]


# ---------------------------------------------------------------------------
# B2: original page/sheet/document provenance is preserved (not temp page 1).
# ---------------------------------------------------------------------------
def test_evidence_and_metadata_preserve_original_provenance_not_temp_page_one(worker_client):
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="a101-provenance")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 200, measured.text

    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM canonical_takeoff_evidence WHERE project_id=? AND tenant_id=? AND company_id=?",
            (str(project_id), tenant_id, company_id),
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["document_id"] == str(project_id)
    assert row["sheet_id"] == str(sheet_id)
    # The canonical page number must be the ORIGINAL packet page (282), never
    # the temp single-page extract's own page (1).
    assert row["page_number"] == SELECTED_PAGE
    assert float(row["quantity"]) == 10.0
    assert row["unit"] == "LF"

    artifacts = client.get(
        f"/internal/takeoff/jobs/{job_id}/artifacts", headers=_headers(tenant_id, company_id)
    )
    assert artifacts.status_code == 200, artifacts.text
    returned = artifacts.json()["artifacts"]
    assert {a["artifact_type"] for a in returned} >= {
        "opentakeoff_export", "canonical_evidence", "marked_region_metadata", "worker_metadata",
    }
    # No artifact response ever carries a filesystem path (temp or otherwise).
    for artifact in returned:
        assert artifact["signed_url"] is None
        assert "storage_key" not in artifact
        assert "mobi-opentakeoff-page-" not in str(artifact)
        assert "tmp" not in str(artifact)


# ---------------------------------------------------------------------------
# B3: mismatch/out-of-range/unverified sheet rejection before provider work.
# ---------------------------------------------------------------------------
def test_wrong_project_sheet_rejected_at_measure_time(worker_client):
    """A sheet reassigned to a different project between confirm-scale and
    measure must fail closed (before any provider work / status change)."""
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    other_project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id, num_pages=5)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="wrong-project-race")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    # Simulate the sheet being reassigned to a different project after scale
    # confirmation (a race / stale reference), bypassing the ORM boundary on
    # purpose to prove the server-side re-check catches it.
    with database.get_connection() as conn:
        conn.execute("UPDATE sheets SET project_id = ? WHERE id = ?", (str(other_project_id), str(sheet_id)))
        conn.commit()

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 422, measured.text
    assert "sheet_not_found" in measured.text

    with database.get_connection() as conn:
        job_row = conn.execute(
            "SELECT status FROM opentakeoff_worker_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM canonical_takeoff_evidence WHERE project_id=?", (str(project_id),)
        ).fetchone()[0]
    assert job_row["status"] == "awaiting_geometry"
    assert evidence_count == 0


def test_wrong_page_sheet_rejected_at_measure_time(worker_client):
    """A sheet whose recorded page changes after confirm-scale must fail closed."""
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="wrong-page-race")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    with database.get_connection() as conn:
        conn.execute("UPDATE sheets SET pdf_page_number = ? WHERE id = ?", (SELECTED_PAGE + 1, str(sheet_id)))
        conn.commit()

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 422, measured.text
    assert "sheet_page_mismatch" in measured.text

    with database.get_connection() as conn:
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM canonical_takeoff_evidence WHERE project_id=?", (str(project_id),)
        ).fetchone()[0]
    assert evidence_count == 0


def test_unverified_deleted_sheet_rejected_at_measure_time(worker_client):
    """A sheet deleted after confirm-scale (no longer verifiable) fails closed."""
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="deleted-sheet-race")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    with database.get_connection() as conn:
        conn.execute("DELETE FROM sheets WHERE id = ?", (str(sheet_id),))
        conn.commit()

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 422, measured.text
    assert "sheet_not_found" in measured.text


def test_unverified_sheet_rejected_at_scale_confirmation(worker_client):
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)
    with database.get_connection() as conn:
        conn.execute("UPDATE sheets SET review_status = 'pending' WHERE id = ?", (str(sheet_id),))
        conn.commit()

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="unverified-at-confirm")
    job_id = created.json()["job"]["job_id"]
    confirmed = _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE)
    assert confirmed.status_code == 422, confirmed.text
    assert "sheet_not_verified" in confirmed.text


def test_sheet_that_loses_verified_status_is_rejected_at_measure_time(worker_client):
    """A sheet moved out of verified status after scale confirmation must fail
    closed before provider work or evidence persistence."""
    client, _service, _tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="unverified-sheet-race")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    with database.get_connection() as conn:
        conn.execute("UPDATE sheets SET review_status = 'pending' WHERE id = ?", (str(sheet_id),))
        conn.commit()

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 422, measured.text
    assert "sheet_not_verified" in measured.text

    with database.get_connection() as conn:
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM canonical_takeoff_evidence WHERE project_id=?", (str(project_id),)
        ).fetchone()[0]
    assert evidence_count == 0


def test_extract_scale_page_pdf_rejects_out_of_range_and_invalid_pages(tmp_path):
    pdf_path = tmp_path / "small.pdf"
    _build_synthetic_packet(pdf_path, 5)

    with pytest.raises(WorkerApiError) as too_high:
        extract_scale_page_pdf(pdf_path, 6, temp_root=tmp_path)
    assert too_high.value.code == "sheet_page_out_of_range"

    with pytest.raises(WorkerApiError) as too_low:
        extract_scale_page_pdf(pdf_path, 0, temp_root=tmp_path)
    assert too_low.value.code == "sheet_page_out_of_range"

    # No orphaned temp directories from either rejected extraction.
    assert _no_leftover_extraction_temp_dirs(tmp_path)


# ---------------------------------------------------------------------------
# B6/B7: temp cleanup after success and provider failure; safety caps unchanged.
# ---------------------------------------------------------------------------
def test_temp_extraction_cleaned_up_after_success(worker_client):
    client, _service, tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="cleanup-success")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 200, measured.text
    assert _no_leftover_extraction_temp_dirs(tmp_path)


def test_temp_extraction_cleaned_up_after_provider_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_path", tmp_path / "failure-worker.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "api_key", API_KEY)
    database.init_db()
    # An unreachable tool timeout forces a provider failure on the very first
    # MCP call, exercising the cleanup path on the except branch.
    service = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", service)
    client = TestClient(create_app())

    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    created = _create_line_job(client, tenant_id, company_id, project_id, idem="cleanup-failure")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id, page_number=SELECTED_PAGE).status_code == 200

    measured = _measure_line(client, tenant_id, company_id, job_id)
    assert measured.status_code == 500, measured.text

    with database.get_connection() as conn:
        job_row = conn.execute(
            "SELECT status FROM opentakeoff_worker_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    assert job_row["status"] == "failed"
    assert _no_leftover_extraction_temp_dirs(tmp_path)


def test_whole_document_load_of_large_packet_still_hits_the_unweakened_safety_cap(worker_client):
    """Loading the FULL 302-page packet directly must still be rejected by the
    runtime's whole-document page cap — the fix never raises max_pages/
    max_pdf_bytes, it only ever runs the provider against a bounded extract."""
    from app.takeoff.mcp_runtime import OpenTakeoffMCPClient, OpenTakeoffRuntimeError

    client, service, tmp_path = worker_client
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)

    assert service._runtime_config.max_pages == 250
    assert service._runtime_config.max_pdf_bytes == 75 * 1024 * 1024

    full_doc = storage.project_dir(project_id, tenant_id=tenant_id, company_id=company_id) / "joined_packet.pdf"
    runtime = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(temp_root=tmp_path))
    try:
        with pytest.raises(OpenTakeoffRuntimeError) as exc_info:
            runtime.load_plan(full_doc)
        assert exc_info.value.category.value == "resource_limit"
    finally:
        runtime.close()


# ---------------------------------------------------------------------------
# B9: retry lineage/immutability runs through the fixed selected-sheet path.
# ---------------------------------------------------------------------------
def test_retry_of_resource_limit_style_failure_runs_through_fixed_path(monkeypatch, tmp_path):
    """A linked retry of a failed job can run the fixed selected-sheet path to
    success while the original failed job stays immutable — proving the fix
    integrates with the existing idempotent retry lineage, not around it."""
    monkeypatch.setattr(settings, "db_path", tmp_path / "retry-worker.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "api_key", API_KEY)
    database.init_db()

    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_large_packet_project(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id, page_number=SELECTED_PAGE, tenant_id=tenant_id, company_id=company_id)

    failing = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_path)
    )
    healthy = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path)
    )

    monkeypatch.setattr(worker_router, "worker_api_service", failing)
    client = TestClient(create_app())
    created = _create_line_job(client, tenant_id, company_id, project_id, idem="retry-a101")
    failed_job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(
        client, tenant_id, company_id, failed_job_id, sheet_id, page_number=SELECTED_PAGE
    ).status_code == 200
    failed = _measure_line(client, tenant_id, company_id, failed_job_id)
    assert failed.status_code == 500, failed.text

    with database.get_connection() as conn:
        original_error = conn.execute(
            "SELECT safe_error_message FROM opentakeoff_worker_jobs WHERE job_id=?", (failed_job_id,)
        ).fetchone()["safe_error_message"]
    assert original_error

    monkeypatch.setattr(worker_router, "worker_api_service", healthy)
    client = TestClient(create_app())
    retry = client.post(
        f"/internal/takeoff/jobs/{failed_job_id}/retry", headers=_headers(tenant_id, company_id), json={}
    )
    assert retry.status_code == 201, retry.text
    retry_job_id = retry.json()["job"]["job_id"]
    assert retry_job_id != failed_job_id

    assert _confirm_scale(
        client, tenant_id, company_id, retry_job_id, sheet_id, page_number=SELECTED_PAGE
    ).status_code == 200
    measured = _measure_line(client, tenant_id, company_id, retry_job_id)
    assert measured.status_code == 200, measured.text
    assert measured.json()["job"]["status"] == "awaiting_review"

    # The original failed job and its error remain untouched.
    with database.get_connection() as conn:
        failed_row = conn.execute(
            "SELECT status, safe_error_message FROM opentakeoff_worker_jobs WHERE job_id=?", (failed_job_id,)
        ).fetchone()
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM canonical_takeoff_evidence WHERE project_id=?", (str(project_id),)
        ).fetchone()[0]
    assert failed_row["status"] == "failed"
    assert failed_row["safe_error_message"] == original_error
    assert evidence_count == 1
    assert _no_leftover_extraction_temp_dirs(tmp_path)
