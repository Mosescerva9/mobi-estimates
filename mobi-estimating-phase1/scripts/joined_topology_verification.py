#!/usr/bin/env python3
"""Joined-topology verification harness for the canonical internal engine.

This harness proves the *safe* target topology end to end on a throwaway
local/staging stack: one canonical FastAPI application, backed by ONE temporary
SQLite database and data root, that serves both the normal ``/api/v1`` upload +
processing routes AND the ``/internal/takeoff`` OpenTakeoff worker API. It:

* uploads and processes one approved public Golden Set PDF through the real
  FastAPI application path (no direct DB seeding, no browser filesystem path);
* runs the real pinned OpenTakeoff MCP worker for the line, polygon/area, and
  count operations against that SAME uploaded project/document — no duplicate
  project or database registration;
* verifies canonical quantities/evidence (provider, unit, geometry, scale,
  provider version, ``review_status=pending``), wrong-tenant denial, evidence
  persistence, create idempotency, and safe failure + retry;
* asserts no customer delivery / payment / message / final-approval side effects
  occurred (evidence stays pending, jobs never reach ``completed``, no proposal
  is issued, project status never leaves its safe pre-delivery set);
* writes a machine-readable JSON result to a caller-selected ``--output`` path.

It NEVER contacts Stripe, sends a message/email, deploys, edits Caddy/DNS/Vercel,
runs a production migration, or mutates any production database — it runs wholly
inside a fresh temporary directory and tears it down on exit. It is a local /
staging verification tool, not a production action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

API_KEY = "joined-topology-harness-key"

# Build the ONE canonical app under the internal-VPS engine configuration: the
# normal /api/v1 routes and /internal/takeoff worker served together behind one
# shared-key + tenant-header boundary. These are set before importing app.config
# so the fail-closed startup contract is exercised, not bypassed.
os.environ.setdefault("MOBI_DEPLOYMENT_ENVIRONMENT", "internal_vps")
os.environ.setdefault("MOBI_ENGINE_AUTH_MODE", "internal_vps_shared_key")
os.environ.setdefault("MOBI_API_KEY", API_KEY)

# Default approved public Golden Set document (CA DGS public plan set) used by the
# existing real OpenTakeoff worker proof. Page 4 (C011) has a known measurable
# conduit run that yields a deterministic 37.5 LF at the calibrated scale below.
DEFAULT_PLAN = REPO_ROOT / "data" / "golden_set_v2" / "documents" / "ca_dgs_24_253614_plans.pdf"
DEFAULT_PAGE = 4
# Calibrated units-per-px for the C011 stall-depth dimension on page 4.
CALIBRATED_UPP = 0.08012820512820511
# Deterministic line geometry (468 px * upp = 37.5 LF).
LINE_POINTS = [[3244.32, 1267.2], [3712.32, 1267.2]]
# Deterministic axis-aligned rectangle for the polygon/area operation.
POLYGON_VERTS = [
    [3244.32, 1267.2],
    [3712.32, 1267.2],
    [3712.32, 1467.2],
    [3244.32, 1467.2],
]
# Four discrete markers -> 4 EA count.
COUNT_MARKS = [[3300.0, 1300.0], [3400.0, 1300.0], [3500.0, 1300.0], [3600.0, 1300.0]]

SAFE_PROJECT_STATUSES = {
    "created",
    "uploaded",
    "queued",
    "processing",
    "ready_for_review",
    "needs_review",
    "complete",
}


class HarnessError(RuntimeError):
    """A verification assertion failed; the harness exits non-zero."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


class _ExternalNetworkBlocked(HarnessError):
    """Raised if the harness/app attempts any non-loopback network connection."""


@contextmanager
def _fail_on_external_network(record: dict[str, Any]) -> Iterator[None]:
    """Instrument the process so ANY outbound non-loopback socket connect fails.

    This is the proof method for "no external side effects": the worker path
    runs entirely in-process over a TestClient (ASGI, no sockets) and a local
    SQLite file, so a genuine attempt to reach Stripe / an email or messaging
    provider / any delivery endpoint would open a real socket and be caught here
    instead of being asserted absent by a hardcoded ``false``. Loopback is left
    open for any incidental local IPC.
    """

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    record["external_connect_attempts"] = 0
    record["external_connect_targets"] = []

    def _host_of(address: Any) -> str:
        if isinstance(address, tuple) and address:
            return str(address[0])
        return str(address)

    def _guarded_connect(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = _host_of(address)
        if host not in _LOOPBACK_HOSTS:
            record["external_connect_attempts"] += 1
            record["external_connect_targets"].append(host)
            raise _ExternalNetworkBlocked(
                f"external network connection attempted to {host!r}; "
                "the harness must never contact production/external services"
            )
        return real_connect(self, address, *args, **kwargs)

    def _guarded_connect_ex(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = _host_of(address)
        if host not in _LOOPBACK_HOSTS:
            record["external_connect_attempts"] += 1
            record["external_connect_targets"].append(host)
            raise _ExternalNetworkBlocked(
                f"external network connection attempted to {host!r}"
            )
        return real_connect_ex(self, address, *args, **kwargs)

    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = real_connect_ex  # type: ignore[method-assign]


def _headers(tenant_id: str, company_id: str, *, role: str = "estimator") -> dict[str, str]:
    return {
        "X-API-Key": API_KEY,
        "X-Mobi-Tenant-Id": tenant_id,
        "X-Mobi-Company-Id": company_id,
        "X-Mobi-Actor-Role": role,
        "X-Mobi-Actor-Id": "harness-staff-1",
    }


def _upload_headers(tenant_id: str, company_id: str) -> dict[str, str]:
    # Upload/process routes take the shared key + tenant identity, but no actor.
    return {
        "X-API-Key": API_KEY,
        "X-Mobi-Tenant-Id": tenant_id,
        "X-Mobi-Company-Id": company_id,
    }


@contextmanager
def _temporary_stack(plan: Path) -> Iterator[dict[str, Any]]:
    """Build one canonical app over a temp DB + data root; tear it down after."""

    tmp_root = Path(tempfile.mkdtemp(prefix="mobi-joined-topology-"))
    try:
        from app import database
        from app.config import settings
        from app.services import storage  # noqa: F401 - imported for side-effect parity
        import app.routers_opentakeoff_worker as worker_router
        from app.main import create_app
        from app.takeoff.mcp_runtime import OpenTakeoffRuntimeConfig
        from app.takeoff.worker_api import OpenTakeoffWorkerApiService

        # Point the ONE canonical app at the throwaway DB + data root and enable
        # the real shared-key + tenant-header boundary so denial is genuinely
        # enforced by the deployed middleware (not just route guards).
        original = {
            "db_path": settings.db_path,
            "upload_dir": settings.upload_dir,
            "api_key": settings.api_key,
            "render_dpi": settings.render_dpi,
            "thumbnail_max_width": settings.thumbnail_max_width,
            "worker_service": worker_router.worker_api_service,
        }
        settings.db_path = tmp_root / "engine.db"
        settings.upload_dir = tmp_root / "data"
        settings.api_key = API_KEY
        # Keep engine-side rendering light; the worker's MCP renders the PDF
        # itself, so this does not affect measurement accuracy.
        settings.render_dpi = 72
        settings.thumbnail_max_width = 200
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        database.init_db()

        service = OpenTakeoffWorkerApiService(
            OpenTakeoffRuntimeConfig(tool_timeout_seconds=45, temp_root=tmp_root)
        )
        worker_router.worker_api_service = service
        failing_service = OpenTakeoffWorkerApiService(
            OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_root)
        )

        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        yield {
            "client": client,
            "database": database,
            "settings": settings,
            "worker_router": worker_router,
            "service": service,
            "failing_service": failing_service,
            "plan": plan,
            "tmp_root": tmp_root,
        }
        # Restore mutated singleton state so the harness leaves no global residue.
        for key, value in original.items():
            if key == "worker_service":
                worker_router.worker_api_service = value
            else:
                setattr(settings, key, value)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def _upload_and_process(ctx: dict[str, Any], tenant_id: str, company_id: str) -> dict[str, Any]:
    client = ctx["client"]
    plan: Path = ctx["plan"]
    # Upload with the multipart filename "original.pdf" so the stored file's
    # basename matches the recorded original_file_name; the worker derives its
    # sheet key from that name and the OpenTakeoff MCP keys sheets by basename.
    with plan.open("rb") as handle:
        response = client.post(
            "/api/v1/projects/upload",
            headers=_upload_headers(tenant_id, company_id),
            data={"project_name": "Joined topology verification", "contractor_name": "Mobi harness"},
            files={"plan": ("original.pdf", handle, "application/pdf")},
        )
    _check(response.status_code == 201, f"upload failed: {response.status_code} {response.text}")
    project_id = response.json()["project_id"]

    processed = client.post(
        f"/api/v1/projects/{project_id}/process",
        headers=_upload_headers(tenant_id, company_id),
        json={"force": False},
    )
    _check(
        processed.status_code in (200, 202),
        f"process failed: {processed.status_code} {processed.text}",
    )

    sheets = client.get(
        f"/api/v1/projects/{project_id}/sheets?limit=200&offset=0",
        headers=_upload_headers(tenant_id, company_id),
    )
    _check(sheets.status_code == 200, f"sheet listing failed: {sheets.status_code} {sheets.text}")
    items = sheets.json().get("items") or sheets.json().get("sheets") or []
    page_sheet = next((s for s in items if int(s.get("pdf_page_number") or 0) == DEFAULT_PAGE), None)
    _check(page_sheet is not None, f"no processed sheet found for page {DEFAULT_PAGE}")
    return {"project_id": project_id, "sheet_id": page_sheet["sheet_id"], "sheet_count": len(items)}


def _run_operation(
    ctx: dict[str, Any],
    *,
    tenant_id: str,
    company_id: str,
    project_id: str,
    sheet_id: str,
    operation: str,
    idempotency_key: str,
    geometry: dict[str, Any],
    condition: str,
    measure_path: str,
) -> dict[str, Any]:
    client = ctx["client"]
    created = client.post(
        "/internal/takeoff/jobs",
        headers=_headers(tenant_id, company_id),
        json={
            "project_id": project_id,
            "document_id": project_id,
            "operation": operation,
            "trade": "electrical",
            "scope_category": "ev_charging",
            "condition": condition,
            "default_description": f"Joined topology {operation}",
            "idempotency_key": idempotency_key,
        },
    )
    _check(created.status_code == 201, f"{operation} create failed: {created.status_code} {created.text}")
    _check(created.json()["created"] is True, f"{operation} first create must report created=True")
    job_id = created.json()["job"]["job_id"]

    confirm = client.post(
        f"/internal/takeoff/jobs/{job_id}/confirm-scale",
        headers=_headers(tenant_id, company_id),
        json={
            "sheet_id": sheet_id,
            "page_number": DEFAULT_PAGE,
            "scale_source": "printed 15'-0 stall-depth dimension",
            "scale_label": "calibrated",
            "units_per_px": CALIBRATED_UPP,
        },
    )
    _check(confirm.status_code == 200, f"{operation} confirm-scale failed: {confirm.status_code} {confirm.text}")

    measured = client.post(
        f"/internal/takeoff/jobs/{job_id}/{measure_path}",
        headers=_headers(tenant_id, company_id),
        json={"geometry": geometry, "condition": condition},
    )
    _check(measured.status_code == 200, f"{operation} measure failed: {measured.status_code} {measured.text}")
    job = measured.json()["job"]
    _check(job["status"] == "awaiting_review", f"{operation} job must be awaiting_review, got {job['status']}")
    return {"job_id": job_id, "status": job["status"]}


def run(plan: Path) -> dict[str, Any]:
    tenant_a = str(uuid4())
    company_a = str(uuid4())
    tenant_b = str(uuid4())

    results: dict[str, Any] = {
        "harness": "joined_topology_verification",
        "plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "operations": {},
        "checks": {},
        "side_effect_locks": {},
    }

    # Prove no external service is ever contacted: any non-loopback socket connect
    # during the whole run raises instead of being asserted absent by a hardcoded
    # boolean.
    network_record: dict[str, Any] = {}

    with _fail_on_external_network(network_record), _temporary_stack(plan) as ctx:
        client = ctx["client"]
        database = ctx["database"]

        uploaded = _upload_and_process(ctx, tenant_a, company_a)
        project_id = uploaded["project_id"]
        sheet_id = uploaded["sheet_id"]
        results["project_id"] = project_id
        results["sheet_id"] = sheet_id
        results["sheet_count"] = uploaded["sheet_count"]

        # --- Line, polygon/area, and count against the SAME uploaded project ---
        results["operations"]["line"] = _run_operation(
            ctx, tenant_id=tenant_a, company_id=company_a, project_id=project_id,
            sheet_id=sheet_id, operation="measure_line", idempotency_key="line-1",
            geometry={"points": LINE_POINTS}, condition="RUNTIME-LINE", measure_path="measure-line",
        )
        results["operations"]["polygon"] = _run_operation(
            ctx, tenant_id=tenant_a, company_id=company_a, project_id=project_id,
            sheet_id=sheet_id, operation="measure_polygon", idempotency_key="polygon-1",
            geometry={"vertices": POLYGON_VERTS}, condition="RUNTIME-AREA", measure_path="measure-polygon",
        )
        results["operations"]["count"] = _run_operation(
            ctx, tenant_id=tenant_a, company_id=company_a, project_id=project_id,
            sheet_id=sheet_id, operation="measure_count", idempotency_key="count-1",
            geometry={"points": COUNT_MARKS}, condition="RUNTIME-COUNT", measure_path="measure-count",
        )

        # --- Idempotency: duplicate create must not spawn a second job/evidence ---
        duplicate = client.post(
            "/internal/takeoff/jobs",
            headers=_headers(tenant_a, company_a),
            json={
                "project_id": project_id,
                "document_id": project_id,
                "operation": "measure_line",
                "trade": "electrical",
                "scope_category": "ev_charging",
                "idempotency_key": "line-1",
            },
        )
        _check(duplicate.status_code == 201, f"duplicate create status: {duplicate.status_code} {duplicate.text}")
        _check(duplicate.json()["created"] is False, "duplicate idempotency key must report created=False")
        _check(
            duplicate.json()["job"]["job_id"] == results["operations"]["line"]["job_id"],
            "duplicate idempotency key must resolve to the original job id",
        )
        results["checks"]["idempotent_duplicate_created_false"] = True

        # --- Wrong tenant/company is denied (no cross-tenant access) ---
        wrong_tenant = client.post(
            "/internal/takeoff/jobs",
            headers=_headers(tenant_b, company_a),
            json={
                "project_id": project_id,
                "document_id": project_id,
                "operation": "measure_line",
                "trade": "electrical",
                "scope_category": "ev_charging",
                "idempotency_key": "wrong-tenant",
            },
        )
        _check(wrong_tenant.status_code == 403, f"wrong tenant must be denied, got {wrong_tenant.status_code}")
        results["checks"]["wrong_tenant_denied"] = True

        # --- Failed job persists a safe error and can be retried without loss ---
        ctx["worker_router"].worker_api_service = ctx["failing_service"]
        try:
            fail_created = client.post(
                "/internal/takeoff/jobs",
                headers=_headers(tenant_a, company_a),
                json={
                    "project_id": project_id,
                    "document_id": project_id,
                    "operation": "measure_line",
                    "trade": "electrical",
                    "scope_category": "ev_charging",
                    "idempotency_key": "fail-1",
                },
            )
            _check(fail_created.status_code == 201, f"fail-job create: {fail_created.text}")
            fail_job_id = fail_created.json()["job"]["job_id"]
            client.post(
                f"/internal/takeoff/jobs/{fail_job_id}/confirm-scale",
                headers=_headers(tenant_a, company_a),
                json={
                    "sheet_id": sheet_id, "page_number": DEFAULT_PAGE,
                    "scale_source": "printed dimension", "scale_label": "calibrated",
                    "units_per_px": CALIBRATED_UPP,
                },
            )
            failed = client.post(
                f"/internal/takeoff/jobs/{fail_job_id}/measure-line",
                headers=_headers(tenant_a, company_a),
                json={"geometry": {"points": LINE_POINTS}},
            )
            _check(failed.status_code == 500, f"forced-timeout measure must 500, got {failed.status_code}")
        finally:
            ctx["worker_router"].worker_api_service = ctx["service"]

        with database.get_connection() as conn:
            fail_row = conn.execute(
                "SELECT status, safe_error_message, error_category FROM opentakeoff_worker_jobs WHERE job_id=?",
                (fail_job_id,),
            ).fetchone()
        _check(fail_row is not None and fail_row["status"] == "failed", "forced-timeout job must persist status=failed")
        _check(bool(fail_row["safe_error_message"]), "failed job must persist a safe, non-empty error message")
        results["checks"]["failed_job_persists_safe_error"] = {
            "status": fail_row["status"],
            "error_category": fail_row["error_category"],
            "safe_error_message": fail_row["safe_error_message"],
        }

        # --- REAL retry: a new attempt linked to the failed job (not a fresh,
        # unrelated job). It carries attempt_number=2 and parent/root lineage; the
        # original failed job/error is retained; repeated retries are idempotent. ---
        retry_created = client.post(
            f"/internal/takeoff/jobs/{fail_job_id}/retry",
            headers=_headers(tenant_a, company_a),
            json={},
        )
        _check(retry_created.status_code == 201, f"retry create: {retry_created.text}")
        _check(retry_created.json()["created"] is True, "first retry must report created=True")
        retry_job_id = retry_created.json()["job"]["job_id"]
        _check(retry_job_id != fail_job_id, "retry must be a NEW job id, not the failed one")

        # Idempotent retry: repeating the request returns the same attempt.
        retry_again = client.post(
            f"/internal/takeoff/jobs/{fail_job_id}/retry",
            headers=_headers(tenant_a, company_a),
            json={},
        )
        _check(retry_again.status_code == 201, f"retry idempotent: {retry_again.text}")
        _check(retry_again.json()["created"] is False, "repeated retry must report created=False")
        _check(
            retry_again.json()["job"]["job_id"] == retry_job_id,
            "repeated retry must resolve to the same attempt (no duplicate retries)",
        )

        with database.get_connection() as conn:
            retry_row = conn.execute(
                "SELECT attempt_number, parent_job_id, root_job_id, status "
                "FROM opentakeoff_worker_jobs WHERE job_id=?",
                (retry_job_id,),
            ).fetchone()
            failed_after = conn.execute(
                "SELECT status, safe_error_message FROM opentakeoff_worker_jobs WHERE job_id=?",
                (fail_job_id,),
            ).fetchone()
        _check(retry_row is not None, "retry attempt must be persisted")
        _check(int(retry_row["attempt_number"]) == 2, f"retry attempt_number must be 2, got {retry_row['attempt_number']}")
        _check(retry_row["parent_job_id"] == fail_job_id, "retry parent_job_id must be the failed job")
        _check(retry_row["root_job_id"] == fail_job_id, "retry root_job_id must be the failed job (lineage root)")
        _check(failed_after["status"] == "failed", "original failed job must remain failed after retry")
        _check(bool(failed_after["safe_error_message"]), "original failure error must be retained after retry")

        # Drive the retry attempt to a successful measurement (confirm scale, then
        # measure the same conduit run) — proving durable retry actually succeeds.
        confirm_retry = client.post(
            f"/internal/takeoff/jobs/{retry_job_id}/confirm-scale",
            headers=_headers(tenant_a, company_a),
            json={
                "sheet_id": sheet_id, "page_number": DEFAULT_PAGE,
                "scale_source": "printed 15'-0 stall-depth dimension",
                "scale_label": "calibrated", "units_per_px": CALIBRATED_UPP,
            },
        )
        _check(confirm_retry.status_code == 200, f"retry confirm-scale: {confirm_retry.text}")
        measured_retry = client.post(
            f"/internal/takeoff/jobs/{retry_job_id}/measure-line",
            headers=_headers(tenant_a, company_a),
            json={"geometry": {"points": LINE_POINTS}, "condition": "RUNTIME-LINE"},
        )
        _check(measured_retry.status_code == 200, f"retry measure: {measured_retry.text}")
        _check(
            measured_retry.json()["job"]["status"] == "awaiting_review",
            "retry attempt must reach awaiting_review",
        )
        results["operations"]["retry_line"] = {
            "job_id": retry_job_id,
            "status": "awaiting_review",
            "attempt_number": int(retry_row["attempt_number"]),
            "parent_job_id": fail_job_id,
            "root_job_id": fail_job_id,
        }
        results["checks"]["retry_after_failure_succeeds"] = True
        results["checks"]["retry_is_linked_attempt_and_idempotent"] = True

        # --- Canonical evidence verification (quantities, lineage, review state) ---
        with database.get_connection() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM canonical_takeoff_evidence WHERE project_id=? AND tenant_id=? AND company_id=? "
                "ORDER BY unit, quantity",
                (project_id, tenant_a, company_a),
            ).fetchall()]

        by_unit: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_unit.setdefault(row["unit"], []).append(row)

        _check(len(rows) == 4, f"expected 4 evidence rows (2 LF, 1 SF, 1 EA), got {len(rows)}")
        _check(len(by_unit.get("LF", [])) == 2, "expected two LF (line + retry) evidence rows")
        _check(len(by_unit.get("SF", [])) == 1, "expected one SF (polygon/area) evidence row")
        _check(len(by_unit.get("EA", [])) == 1, "expected one EA (count) evidence row")

        for row in rows:
            _check(row["takeoff_provider"] == "open_takeoff", "evidence provider must be open_takeoff")
            _check(row["review_status"] == "pending", "every evidence row must be review_status=pending")
            _check(str(row["project_id"]) == project_id, "evidence must carry the source project id")
            _check(str(row["document_id"]) == project_id, "evidence must carry the source document id")
            _check(str(row["sheet_id"]) == sheet_id, "evidence must carry the source sheet id")
            _check(int(row["page_number"]) == DEFAULT_PAGE, "evidence must carry the source page number")
            _check(bool(row["region_coordinates"]), "evidence must carry geometry region coordinates")
            _check(bool(row["extractor_version"]), "evidence must carry a provider/extractor version")

        line_qty = float(by_unit["LF"][0]["quantity"])
        _check(abs(line_qty - 37.5) < 0.01, f"line quantity must be 37.5 LF, got {line_qty}")
        count_qty = float(by_unit["EA"][0]["quantity"])
        _check(abs(count_qty - 4) < 1e-9, f"count quantity must be 4 EA, got {count_qty}")
        # The SF row must carry a scale ("where applicable"); the EA row need not.
        _check(bool(by_unit["SF"][0]["scale"]), "area evidence must record the confirmed scale")

        # --- Provenance: count must be an explicit staff marker tally, NOT an
        # MCP-native/autonomous measurement; line/polygon are digital measurements.
        for row in by_unit["LF"] + by_unit["SF"]:
            _check(
                row["measurement_method"] == "digital_measurement",
                f"line/area evidence must be digital_measurement, got {row['measurement_method']}",
            )
        count_row = by_unit["EA"][0]
        _check(
            count_row["measurement_method"] == "staff_marker_tally",
            f"count evidence must be staff_marker_tally, got {count_row['measurement_method']}",
        )
        # Count remains scale-independent in quantity: 4 markers -> 4 EA regardless
        # of the confirmed scale, though document/sheet lineage is preserved.
        _check(str(count_row["document_id"]) == project_id, "count evidence keeps document lineage")
        _check(int(count_row["page_number"]) == DEFAULT_PAGE, "count evidence keeps sheet/page lineage")
        results["checks"]["count_provenance"] = {
            "measurement_method": count_row["measurement_method"],
            "quantity_ea": count_qty,
            "scale_independent": True,
            "document_id": str(count_row["document_id"]),
            "page_number": int(count_row["page_number"]),
        }

        results["checks"]["canonical_evidence"] = {
            "total_rows": len(rows),
            "line_lf": line_qty,
            "area_sf": float(by_unit["SF"][0]["quantity"]),
            "count_ea": count_qty,
            "all_pending": True,
            "line_area_method": "digital_measurement",
            "count_method": "staff_marker_tally",
        }

        # --- Persistence + no duplicate project registration ---
        with database.get_connection() as conn:
            project_count = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE id=?", (project_id,)
            ).fetchone()[0]
            total_projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            job_rows = [dict(r) for r in conn.execute(
                "SELECT status FROM opentakeoff_worker_jobs WHERE project_id=?", (project_id,)
            ).fetchall()]
            proposal_count = conn.execute(
                "SELECT COUNT(*) FROM proposals WHERE project_id=?", (project_id,)
            ).fetchone()[0]
            # Customer delivery / issuance is recorded as an issued proposal version.
            proposals_issued = conn.execute(
                "SELECT COUNT(*) FROM proposal_versions WHERE project_id=? AND issued_at IS NOT NULL",
                (project_id,),
            ).fetchone()[0]
            # Pricing / final approval is recorded as an approved estimate version.
            estimates_approved = conn.execute(
                "SELECT COUNT(*) FROM estimate_versions WHERE project_id=? AND approved_at IS NOT NULL",
                (project_id,),
            ).fetchone()[0]
            estimate_count = conn.execute(
                "SELECT COUNT(*) FROM estimates WHERE project_id=?", (project_id,)
            ).fetchone()[0]
            # External customer messages/revisions land in customer_revision_requests.
            customer_messages = conn.execute(
                "SELECT COUNT(*) FROM customer_revision_requests WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            project_status = conn.execute(
                "SELECT status FROM projects WHERE id=?", (project_id,)
            ).fetchone()[0]

        _check(project_count == 1, "the project must be registered exactly once")
        _check(total_projects == 1, "only one project may exist (no duplicate project registration)")
        results["checks"]["single_project_registration"] = True

        job_statuses = [r["status"] for r in job_rows]
        awaiting = sum(1 for s in job_statuses if s == "awaiting_review")
        failed = sum(1 for s in job_statuses if s == "failed")
        completed = sum(1 for s in job_statuses if s == "completed")
        _check(awaiting == 4, f"expected 4 awaiting_review jobs, got {awaiting} ({job_statuses})")
        _check(failed == 1, f"expected 1 failed job, got {failed}")
        _check(completed == 0, "no worker job may reach 'completed' (only human review completes work)")

        # --- No customer delivery / payment / message / final-approval side
        # effects. Each claim is PROVEN by querying the local table that would
        # record the effect (or, for external providers with no local table, by
        # the process-wide network guard), never by a hardcoded false. ---
        _check(proposal_count == 0, "no proposal may exist for the worker path project")
        _check(proposals_issued == 0, "no proposal version may be issued/delivered")
        _check(estimates_approved == 0, "no estimate version may be approved (no pricing/final approval)")
        _check(estimate_count == 0, "no estimate may be produced by the worker path")
        _check(customer_messages == 0, "no customer revision/message may be created")
        _check(project_status in SAFE_PROJECT_STATUSES, f"project status left safe set: {project_status}")

        # External services (Stripe payments/refunds/checkout, email/SMS messaging,
        # proposal issuance transport) have no local table; their absence is proven
        # by the network guard catching any real outbound connection.
        external_attempts = int(network_record.get("external_connect_attempts", 0))
        _check(
            external_attempts == 0,
            f"no external network connection may occur, saw {external_attempts} "
            f"to {network_record.get('external_connect_targets')}",
        )

        results["side_effect_locks"] = {
            "customer_delivery": {
                "proven_by": "proposal_versions.issued_at query",
                "issued_count": proposals_issued,
                "occurred": proposals_issued > 0,
            },
            "proposal_issuance": {
                "proven_by": "proposals table count",
                "proposal_count": proposal_count,
                "occurred": proposal_count > 0,
            },
            "pricing_final_approval": {
                "proven_by": "estimate_versions.approved_at query",
                "approved_count": estimates_approved,
                "estimate_count": estimate_count,
                "occurred": estimates_approved > 0,
            },
            "external_message": {
                "proven_by": "customer_revision_requests count + network guard",
                "message_count": customer_messages,
                "occurred": customer_messages > 0,
            },
            "payments_refunds_checkout": {
                "proven_by": "no local table; process-wide network guard (fail-on-connect)",
                "external_connect_attempts": external_attempts,
                "external_connect_targets": network_record.get("external_connect_targets", []),
                "occurred": external_attempts > 0,
            },
            "worker_jobs_completed": completed,
            "project_status": project_status,
            "all_evidence_pending": all(r["review_status"] == "pending" for r in rows),
        }
        results["worker_job_statuses"] = job_statuses

    results["passed"] = True
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Path to write machine-readable JSON results")
    parser.add_argument("--plan", default=str(DEFAULT_PLAN), help="Approved public Golden Set PDF to verify")
    args = parser.parse_args()

    plan = Path(args.plan).resolve()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if not plan.is_file():
        payload = {"harness": "joined_topology_verification", "passed": False, "error": f"plan not found: {plan}"}
        output.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"joined-topology verification FAILED: plan not found: {plan}", file=sys.stderr)
        return 2

    try:
        results = run(plan)
    except HarnessError as exc:
        payload = {"harness": "joined_topology_verification", "passed": False, "error": str(exc)}
        output.write_text(json.dumps(payload, indent=2, sort_keys=True))
        print(f"joined-topology verification FAILED: {exc}", file=sys.stderr)
        return 1

    output.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"joined-topology verification PASSED -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
