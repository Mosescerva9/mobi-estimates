"""Deployable internal OpenTakeoff worker API tests.

These tests cover the VPS-side FastAPI boundary. The browser submits IDs and
geometry; the API resolves the document server-side and launches the real pinned
OpenTakeoff MCP subprocess for the happy-path public fixture proof.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import database
from app.config import settings
from app.main import create_app
from app.services import storage
from app.takeoff.mcp_runtime import OpenTakeoffRuntimeConfig
from app.takeoff.worker_api import OpenTakeoffWorkerApiService
from app.takeoff.worker import OpenTakeoffWorkerStatus
from app.takeoff.worker_jobs import update_worker_job_status
import app.routers_opentakeoff_worker as worker_router
import app.takeoff.worker_api as worker_api_module

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN = REPO_ROOT / "mobi-estimating-phase1/data/golden_set_v2/documents/ca_dgs_24_253614_plans.pdf"
SHEET = "ca_dgs_24_253614_plans.pdf#4"
API_KEY = "test-worker-api-key"


def _headers(tenant_id: str, company_id: str, *, role: str = "estimator", key: str = API_KEY) -> dict[str, str]:
    return {
        "X-API-Key": key,
        "X-Mobi-Tenant-Id": tenant_id,
        "X-Mobi-Company-Id": company_id,
        "X-Mobi-Actor-Role": role,
        "X-Mobi-Actor-Id": "staff-user-1",
    }


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
    yield client


def _seed_project_pdf(*, tenant_id: str, company_id: str, project_id: UUID | None = None) -> UUID:
    project_id = project_id or uuid4()
    dest = storage.project_dir(project_id, tenant_id=tenant_id, company_id=company_id) / PLAN.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLAN, dest)
    stored_file_path = storage.relative_to_data_root(dest)
    database.create_project(
        project_id=project_id,
        name="Public C011 OpenTakeoff fixture",
        contractor_name="Mobi test",
        original_file_name=PLAN.name,
        stored_file_path=stored_file_path,
        status="uploaded",
        page_count=8,
        file_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
        file_size_bytes=dest.stat().st_size,
        tenant_id=tenant_id,
        company_id=company_id,
    )
    return project_id


def _seed_sheet(project_id: UUID, *, page_number: int = 4) -> UUID:
    sheet_id = uuid4()
    database.insert_sheet(
        {
            "id": str(sheet_id),
            "project_id": str(project_id),
            "job_id": None,
            "pdf_page_number": page_number,
            "page_index": page_number - 1,
            "detected_sheet_number": f"C{page_number:03d}",
            "verified_sheet_number": None,
            "detected_sheet_title": "Public fixture sheet",
            "verified_sheet_title": None,
            "detection_confidence": 1.0,
            "requires_review": 0,
            "requires_ocr": 0,
            "text_char_count": 100,
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


def _create_job(client: TestClient, tenant_id: str, company_id: str, project_id: UUID, *, idem: str = "idem-line"):
    return client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "tenant_id": tenant_id,
            "company_id": company_id,
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_line",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "condition": "RUNTIME-LINE",
            "default_description": "Public C011 measured conduit line",
            "idempotency_key": idem,
            "requested_by": "staff-user-1",
        },
    )


def _confirm_scale(client: TestClient, tenant_id: str, company_id: str, job_id: str, sheet_id: UUID):
    return client.post(
        f"/internal/takeoff/jobs/{job_id}/confirm-scale",
        headers=_headers(tenant_id, company_id),
        json={
            "tenant_id": tenant_id,
            "company_id": company_id,
            "sheet_id": str(sheet_id),
            "page_number": 4,
            "scale_source": "printed 15'-0 stall-depth dimension",
            "scale_label": "calibrated",
            "units_per_px": 0.08012820512820511,
        },
    )


def test_unauthenticated_request_denied_when_shared_key_configured(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    response = worker_client.post(
        "/internal/takeoff/jobs",
        headers={
            "X-Mobi-Tenant-Id": tenant_id,
            "X-Mobi-Company-Id": company_id,
            "X-Mobi-Actor-Role": "estimator",
            "X-Mobi-Actor-Id": "staff-user-1",
        },
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_line",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "idempotency_key": "missing-key",
        },
    )
    assert response.status_code == 401


def test_customer_role_denied(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    response = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id, role="client"),
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_line",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "idempotency_key": "customer-denied",
        },
    )
    assert response.status_code == 403


def test_staff_can_create_job_with_ids_not_paths_and_duplicate_is_idempotent(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)

    first = _create_job(worker_client, tenant_id, company_id, project_id, idem="dupe")
    duplicate = _create_job(worker_client, tenant_id, company_id, project_id, idem="dupe")

    assert first.status_code == 201, first.text
    assert duplicate.status_code == 201, duplicate.text
    assert first.json()["created"] is True
    assert duplicate.json()["created"] is False
    assert duplicate.json()["job"]["job_id"] == first.json()["job"]["job_id"]
    assert "safe_local_path" not in str(first.json())
    assert "uploads" not in str(first.json())


def test_wrong_tenant_and_wrong_document_relationship_denied(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)

    wrong_tenant = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(str(uuid4()), company_id),
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_line",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "idempotency_key": "wrong-tenant",
        },
    )
    assert wrong_tenant.status_code == 403

    wrong_document = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id),
            "document_id": str(uuid4()),
            "operation": "measure_line",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "idempotency_key": "wrong-document",
        },
    )
    assert wrong_document.status_code == 422


def test_confirm_scale_missing_scale_invalid_geometry_and_cancellation(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    created = _create_job(worker_client, tenant_id, company_id, project_id, idem="state-check")
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]

    missing_scale = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[0, 0], [1, 1]]}},
    )
    assert missing_scale.status_code == 409

    missing_sheet = _confirm_scale(worker_client, tenant_id, company_id, job_id, uuid4())
    assert missing_sheet.status_code == 422
    assert "sheet_not_found" in missing_sheet.text

    other_project = _seed_project_pdf(tenant_id=str(uuid4()), company_id=str(uuid4()))
    other_sheet = _seed_sheet(other_project)
    wrong_tenant_sheet = _confirm_scale(worker_client, tenant_id, company_id, job_id, other_sheet)
    assert wrong_tenant_sheet.status_code == 422
    assert "sheet_not_found" in wrong_tenant_sheet.text

    wrong_page_sheet = _seed_sheet(project_id, page_number=5)
    wrong_page = _confirm_scale(worker_client, tenant_id, company_id, job_id, wrong_page_sheet)
    assert wrong_page.status_code == 422
    assert "sheet_page_mismatch" in wrong_page.text

    scale = _confirm_scale(worker_client, tenant_id, company_id, job_id, _seed_sheet(project_id))
    assert scale.status_code == 200, scale.text
    assert scale.json()["job"]["status"] == "awaiting_geometry"

    sheet_key_injection = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/confirm-scale",
        headers=_headers(tenant_id, company_id),
        json={
            "sheet_id": str(uuid4()),
            "sheet_key": "../../secret.pdf#1",
            "page_number": 4,
            "scale_source": "attempted client provider selector",
            "scale_label": "bad",
        },
    )
    assert sheet_key_injection.status_code == 422

    invalid = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[0, 0]]}},
    )
    assert invalid.status_code == 422

    cancel = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/cancel",
        headers=_headers(tenant_id, company_id),
        json={},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["job"]["status"] == "cancelled"


def test_real_worker_api_line_measurement_persists_pending_evidence_and_artifacts(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    created = _create_job(worker_client, tenant_id, company_id, project_id, idem="actual-c011-37-5")
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]
    sheet_id = _seed_sheet(project_id)
    scale = _confirm_scale(worker_client, tenant_id, company_id, job_id, sheet_id)
    assert scale.status_code == 200, scale.text

    measured = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={
            "tenant_id": tenant_id,
            "company_id": company_id,
            "geometry": {"points": [[3244.32, 1267.2], [3712.32, 1267.2]]},
            "condition": "RUNTIME-LINE",
        },
    )
    assert measured.status_code == 200, measured.text
    job = measured.json()["job"]
    assert job["status"] == "awaiting_review"
    evidence_ids = job["evidence_ids"]
    assert "[]" not in evidence_ids

    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM canonical_takeoff_evidence WHERE project_id=? AND tenant_id=? AND company_id=?",
            (str(project_id), tenant_id, company_id),
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["takeoff_provider"] == "open_takeoff"
    assert float(row["quantity"]) == 37.5
    assert row["unit"] == "LF"
    assert row["review_status"] == "pending"
    assert row["sheet_id"] == str(sheet_id)
    # A native line measurement is a digital measurement, not a marker tally.
    assert row["measurement_method"] == "digital_measurement"

    artifacts = worker_client.get(
        f"/internal/takeoff/jobs/{job_id}/artifacts",
        headers=_headers(tenant_id, company_id),
    )
    assert artifacts.status_code == 200, artifacts.text
    returned = artifacts.json()["artifacts"]
    assert {a["artifact_type"] for a in returned} >= {
        "opentakeoff_export",
        "canonical_evidence",
        "marked_region_metadata",
        "worker_metadata",
    }
    for artifact in returned:
        assert artifact["signed_url"] is None
        assert artifact["expires_at"] is None
        assert "relative_path" not in artifact
        assert "storage_key" not in artifact
        assert "mobi-estimates" not in str(artifact)
        assert "tmp" not in str(artifact)


def test_real_worker_api_count_measurement_persists_pending_ea_evidence(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)

    # Create a count job (operation = measure_count) on the same uploaded project.
    created = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_count",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "condition": "RUNTIME-COUNT",
            "default_description": "Public C011 EV charger count",
            "idempotency_key": "actual-c011-count-4",
            "requested_by": "staff-user-1",
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]
    sheet_id = _seed_sheet(project_id)
    scale = _confirm_scale(worker_client, tenant_id, company_id, job_id, sheet_id)
    assert scale.status_code == 200, scale.text

    measured = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-count",
        headers=_headers(tenant_id, company_id),
        json={
            "geometry": {"points": [[3244.3, 1267.2], [3712.3, 1267.2], [3500.0, 1500.0], [3300.0, 1600.0]]},
            "condition": "RUNTIME-COUNT",
        },
    )
    assert measured.status_code == 200, measured.text
    job = measured.json()["job"]
    assert job["status"] == "awaiting_review"
    assert "[]" not in job["evidence_ids"]

    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM canonical_takeoff_evidence WHERE project_id=? AND tenant_id=? AND company_id=?",
            (str(project_id), tenant_id, company_id),
        ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["takeoff_provider"] == "open_takeoff"
    assert float(row["quantity"]) == 4
    assert row["unit"] == "EA"
    assert row["review_status"] == "pending"
    assert row["sheet_id"] == str(sheet_id)
    assert row["page_number"] == 4
    # Count provenance is an explicit staff marker tally — NOT an MCP-native /
    # autonomous digital measurement — so downstream evidence can distinguish it
    # from native line/polygon measurement.
    assert row["measurement_method"] == "staff_marker_tally"

    # Idempotent duplicate create must not spawn a second job.
    duplicate = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_count",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "idempotency_key": "actual-c011-count-4",
        },
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["created"] is False
    assert duplicate.json()["job"]["job_id"] == job_id

    artifacts = worker_client.get(
        f"/internal/takeoff/jobs/{job_id}/artifacts",
        headers=_headers(tenant_id, company_id),
    )
    assert artifacts.status_code == 200, artifacts.text
    assert {a["artifact_type"] for a in artifacts.json()["artifacts"]} >= {
        "opentakeoff_export",
        "canonical_evidence",
        "marked_region_metadata",
        "worker_metadata",
    }


def test_cancellation_race_before_persistence_does_not_insert_evidence(worker_client, monkeypatch):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    created = _create_job(worker_client, tenant_id, company_id, project_id, idem="cancel-race")
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(worker_client, tenant_id, company_id, job_id, _seed_sheet(project_id)).status_code == 200

    def fake_run_linear_or_polygon_export(*, job, **_kwargs):
        with database.get_connection() as conn:
            update_worker_job_status(conn, job, status=OpenTakeoffWorkerStatus.CANCELLED)
        return SimpleNamespace(quarantined=[], evidence=[SimpleNamespace(evidence_id=uuid4())])

    def fail_if_evidence_inserted(_evidence, *, conn=None):  # pragma: no cover - should not run
        raise AssertionError("cancelled job must not persist evidence")

    def fail_if_artifacts_written(**_kwargs):  # pragma: no cover - should not run
        raise AssertionError("cancelled job must not write successful evidence artifacts")

    service = worker_router.worker_api_service
    monkeypatch.setattr(service._worker_service, "run_linear_or_polygon_export", fake_run_linear_or_polygon_export)
    monkeypatch.setattr(service, "_write_artifacts", fail_if_artifacts_written)
    monkeypatch.setattr(worker_api_module, "insert_canonical_evidence", fail_if_evidence_inserted)

    measured = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[3244.32, 1267.2], [3712.32, 1267.2]]}},
    )
    assert measured.status_code == 409
    assert "evidence/artifacts were not persisted" in measured.text

    with database.get_connection() as conn:
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM canonical_takeoff_evidence WHERE project_id=?",
            (str(project_id),),
        ).fetchone()[0]
        job_row = conn.execute(
            "SELECT status FROM opentakeoff_worker_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
    assert evidence_count == 0
    assert job_row["status"] == "cancelled"


def test_timeout_failure_marks_job_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "db_path", tmp_path / "timeout-worker.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "api_key", API_KEY)
    database.init_db()
    service = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", service)
    client = TestClient(create_app())

    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    created = _create_job(client, tenant_id, company_id, project_id, idem="timeout")
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, _seed_sheet(project_id)).status_code == 200

    measured = client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[3244.32, 1267.2], [3712.32, 1267.2]]}},
    )
    assert measured.status_code == 500
    status = client.get(f"/internal/takeoff/jobs/{job_id}", headers=_headers(tenant_id, company_id))
    assert status.status_code == 200
    assert status.json()["job"]["status"] == "failed"


def _evidence_count(project_id: UUID) -> int:
    with database.get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM canonical_takeoff_evidence WHERE project_id=?",
            (str(project_id),),
        ).fetchone()[0]


def _job_row(job_id: str) -> dict:
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM opentakeoff_worker_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    return dict(row) if row else {}


def test_measure_endpoint_operation_mismatch_is_safe_and_immutable(worker_client):
    """A measurement endpoint whose kind != the persisted operation is rejected
    before any state change/provider launch/evidence write, and leaves the job
    and evidence unchanged (B2)."""
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)

    sheet_id = _seed_sheet(project_id)

    # A line job measured through measure-count must be a safe 409.
    line_job = _create_job(worker_client, tenant_id, company_id, project_id, idem="op-line")
    assert line_job.status_code == 201, line_job.text
    line_id = line_job.json()["job"]["job_id"]
    assert _confirm_scale(worker_client, tenant_id, company_id, line_id, sheet_id).status_code == 200

    mismatch = worker_client.post(
        f"/internal/takeoff/jobs/{line_id}/measure-count",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[10, 10], [20, 20]]}},
    )
    assert mismatch.status_code == 409, mismatch.text
    assert "operation_mismatch" in mismatch.text
    assert _job_row(line_id)["status"] == "awaiting_geometry"
    assert _evidence_count(project_id) == 0

    # A count job measured through measure-line must also be a safe 409.
    count_job = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id),
            "document_id": str(project_id),
            "operation": "measure_count",
            "trade": "electrical",
            "scope_category": "ev_charging",
            "idempotency_key": "op-count",
        },
    )
    assert count_job.status_code == 201, count_job.text
    count_id = count_job.json()["job"]["job_id"]
    assert _confirm_scale(worker_client, tenant_id, company_id, count_id, sheet_id).status_code == 200
    mismatch2 = worker_client.post(
        f"/internal/takeoff/jobs/{count_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[10, 10], [20, 20]]}},
    )
    assert mismatch2.status_code == 409, mismatch2.text
    assert _job_row(count_id)["status"] == "awaiting_geometry"
    assert _evidence_count(project_id) == 0


# NaN/Infinity are not JSON-compliant for the strict client serializer, but the
# server's json.loads accepts them, so a hostile client CAN submit them as a raw
# body. These raw bodies exercise the backend's non-finite rejection at the wire.
@pytest.mark.parametrize(
    "raw_body,label",
    [
        ('{"geometry": {"points": [[1.0, 1.0], [1.0, 1.0]]}}', "zero-length line"),
        ('{"geometry": {"points": [[NaN, 0.0], [1.0, 1.0]]}}', "nan line"),
        ('{"geometry": {"points": [[Infinity, 0.0], [1.0, 1.0]]}}', "inf line"),
        ('{"geometry": {"points": [[-Infinity, 0.0], [1.0, 1.0]]}}', "neg-inf line"),
    ],
)
def test_degenerate_line_geometry_is_rejected_and_immutable(worker_client, raw_body, label):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    created = _create_job(worker_client, tenant_id, company_id, project_id, idem=f"geom-{label}")
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(worker_client, tenant_id, company_id, job_id, _seed_sheet(project_id)).status_code == 200
    resp = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers={**_headers(tenant_id, company_id), "Content-Type": "application/json"},
        content=raw_body,
    )
    assert resp.status_code == 422, f"{label}: {resp.text}"
    assert "invalid_geometry" in resp.text
    assert _job_row(job_id)["status"] == "awaiting_geometry"
    assert _evidence_count(project_id) == 0


def test_degenerate_polygon_and_count_geometry_is_rejected(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)

    poly_job = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id), "document_id": str(project_id),
            "operation": "measure_polygon", "trade": "electrical",
            "scope_category": "ev_charging", "idempotency_key": "geom-poly",
        },
    )
    poly_id = poly_job.json()["job"]["job_id"]
    sheet_id = _seed_sheet(project_id)
    assert _confirm_scale(worker_client, tenant_id, company_id, poly_id, sheet_id).status_code == 200

    # Duplicate vertices (fewer than three distinct) -> rejected.
    dup = worker_client.post(
        f"/internal/takeoff/jobs/{poly_id}/measure-polygon",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"vertices": [[0, 0], [0, 0], [0, 0]]}},
    )
    assert dup.status_code == 422, dup.text
    # Collinear vertices -> zero area -> rejected.
    collinear = worker_client.post(
        f"/internal/takeoff/jobs/{poly_id}/measure-polygon",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"vertices": [[0, 0], [1, 1], [2, 2]]}},
    )
    assert collinear.status_code == 422, collinear.text
    assert _evidence_count(project_id) == 0

    count_job = worker_client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": str(project_id), "document_id": str(project_id),
            "operation": "measure_count", "trade": "electrical",
            "scope_category": "ev_charging", "idempotency_key": "geom-count",
        },
    )
    count_id = count_job.json()["job"]["job_id"]
    assert _confirm_scale(worker_client, tenant_id, company_id, count_id, sheet_id).status_code == 200
    empty = worker_client.post(
        f"/internal/takeoff/jobs/{count_id}/measure-count",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": []}},
    )
    assert empty.status_code == 422, empty.text
    assert _evidence_count(project_id) == 0


def test_job_state_and_artifacts_survive_a_fresh_service_instance(monkeypatch, tmp_path):
    """A job created + scale-confirmed by one service instance can be measured
    and its artifacts read by a FRESH instance sharing the same DB/data root —
    proving lifecycle state is durable, not process-local (B3)."""
    monkeypatch.setattr(settings, "db_path", tmp_path / "restart-worker.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "api_key", API_KEY)
    database.init_db()

    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id)

    # Instance A creates the job and confirms scale.
    service_a = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", service_a)
    client = TestClient(create_app())
    created = _create_job(client, tenant_id, company_id, project_id, idem="restart")
    assert created.status_code == 201, created.text
    job_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, job_id, sheet_id).status_code == 200

    # A brand-new instance B (no shared memory) measures the SAME job.
    service_b = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", service_b)
    client_b = TestClient(create_app())
    measured = client_b.post(
        f"/internal/takeoff/jobs/{job_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[3244.32, 1267.2], [3712.32, 1267.2]]}},
    )
    assert measured.status_code == 200, measured.text
    assert measured.json()["job"]["status"] == "awaiting_review"

    # A THIRD fresh instance reads the artifacts persisted by instance B.
    service_c = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", service_c)
    client_c = TestClient(create_app())
    artifacts = client_c.get(
        f"/internal/takeoff/jobs/{job_id}/artifacts",
        headers=_headers(tenant_id, company_id),
    )
    assert artifacts.status_code == 200, artifacts.text
    assert {a["artifact_type"] for a in artifacts.json()["artifacts"]} >= {
        "opentakeoff_export", "canonical_evidence", "marked_region_metadata", "worker_metadata",
    }
    for artifact in artifacts.json()["artifacts"]:
        assert "storage_key" not in artifact
        assert artifact["signed_url"] is None


def test_retry_creates_linked_attempt_retains_failure_and_is_idempotent(monkeypatch, tmp_path):
    """Retry is a real new attempt linked to the failed job (attempt_number +
    parent/root lineage); the original failure is retained; repeated retries are
    idempotent and do not duplicate the attempt or its evidence (B5)."""
    monkeypatch.setattr(settings, "db_path", tmp_path / "retry-worker.db")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "api_key", API_KEY)
    database.init_db()

    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    sheet_id = _seed_sheet(project_id)

    healthy = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path)
    )
    failing = OpenTakeoffWorkerApiService(
        OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_path)
    )
    monkeypatch.setattr(worker_router, "worker_api_service", failing)
    client = TestClient(create_app())

    created = _create_job(client, tenant_id, company_id, project_id, idem="retry-base")
    assert created.status_code == 201, created.text
    failed_id = created.json()["job"]["job_id"]
    assert _confirm_scale(client, tenant_id, company_id, failed_id, sheet_id).status_code == 200
    failed = client.post(
        f"/internal/takeoff/jobs/{failed_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[3244.32, 1267.2], [3712.32, 1267.2]]}},
    )
    assert failed.status_code == 500, failed.text
    assert _job_row(failed_id)["status"] == "failed"
    original_error = _job_row(failed_id)["safe_error_message"]
    assert original_error

    # Retry on a healthy instance -> a NEW linked attempt.
    monkeypatch.setattr(worker_router, "worker_api_service", healthy)
    client = TestClient(create_app())
    retry = client.post(
        f"/internal/takeoff/jobs/{failed_id}/retry",
        headers=_headers(tenant_id, company_id),
        json={},
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["created"] is True
    retry_id = retry.json()["job"]["job_id"]
    assert retry_id != failed_id
    retry_row = _job_row(retry_id)
    assert retry_row["attempt_number"] == 2
    assert retry_row["parent_job_id"] == failed_id
    assert retry_row["root_job_id"] == failed_id
    assert retry_row["status"] == "awaiting_scale_confirmation"

    # The original failed job and its error are retained unchanged.
    assert _job_row(failed_id)["status"] == "failed"
    assert _job_row(failed_id)["safe_error_message"] == original_error

    # Idempotent: retrying the failed job again returns the same attempt.
    retry_again = client.post(
        f"/internal/takeoff/jobs/{failed_id}/retry",
        headers=_headers(tenant_id, company_id),
        json={},
    )
    assert retry_again.status_code == 201, retry_again.text
    assert retry_again.json()["created"] is False
    assert retry_again.json()["job"]["job_id"] == retry_id

    # The retry attempt measures successfully to awaiting_review (one evidence).
    assert _confirm_scale(client, tenant_id, company_id, retry_id, sheet_id).status_code == 200
    measured = client.post(
        f"/internal/takeoff/jobs/{retry_id}/measure-line",
        headers=_headers(tenant_id, company_id),
        json={"geometry": {"points": [[3244.32, 1267.2], [3712.32, 1267.2]]}},
    )
    assert measured.status_code == 200, measured.text
    assert measured.json()["job"]["status"] == "awaiting_review"
    assert _evidence_count(project_id) == 1

    # Only one worker job may reach completed: none here (all awaiting/failed).
    with database.get_connection() as conn:
        statuses = [r[0] for r in conn.execute(
            "SELECT status FROM opentakeoff_worker_jobs WHERE project_id=?", (str(project_id),)
        ).fetchall()]
    assert statuses.count("completed") == 0
    assert statuses.count("failed") == 1
    assert statuses.count("awaiting_review") == 1


def test_retry_rejected_for_non_failed_job(worker_client):
    tenant_id = str(uuid4())
    company_id = str(uuid4())
    project_id = _seed_project_pdf(tenant_id=tenant_id, company_id=company_id)
    created = _create_job(worker_client, tenant_id, company_id, project_id, idem="retry-guard")
    job_id = created.json()["job"]["job_id"]
    retry = worker_client.post(
        f"/internal/takeoff/jobs/{job_id}/retry",
        headers=_headers(tenant_id, company_id),
        json={},
    )
    assert retry.status_code == 409, retry.text
    assert "job_not_failed" in retry.text
