"""Actual OpenTakeoff MCP runtime tests.

These tests launch the pinned local OpenTakeoff MCP subprocess; they are not fake
provider tests.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from app.migrations import apply_migrations
from app.takeoff import (
    OPEN_TAKEOFF_MCP_INTEGRITY,
    OPEN_TAKEOFF_MCP_LICENSE,
    OPEN_TAKEOFF_MCP_PACKAGE,
    OPEN_TAKEOFF_MCP_VERSION,
    OpenTakeoffMCPClient,
    OpenTakeoffNormalizeOptions,
    OpenTakeoffRuntimeConfig,
    OpenTakeoffRuntimeError,
    OpenTakeoffScaleConfirmation,
    OpenTakeoffWorkerErrorCode,
    OpenTakeoffWorkerService,
    OpenTakeoffWorkerStatus,
    ResolvedProjectDocument,
    TakeoffContext,
)
from app.takeoff.worker_jobs import (
    create_worker_job_record,
    get_worker_job_record,
    update_worker_job_status,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN = REPO_ROOT / "mobi-estimating-phase1/data/golden_set_v2/documents/ca_dgs_24_253614_plans.pdf"
SHEET = "ca_dgs_24_253614_plans.pdf#4"


def test_opentakeoff_mcp_package_is_pinned_with_lockfile_integrity():
    package = json.loads((REPO_ROOT / "package.json").read_text())
    lock = json.loads((REPO_ROOT / "package-lock.json").read_text())
    locked = lock["packages"][f"node_modules/{OPEN_TAKEOFF_MCP_PACKAGE}"]

    assert package["dependencies"][OPEN_TAKEOFF_MCP_PACKAGE] == OPEN_TAKEOFF_MCP_VERSION
    assert locked["version"] == OPEN_TAKEOFF_MCP_VERSION
    assert locked["integrity"] == OPEN_TAKEOFF_MCP_INTEGRITY
    assert locked["license"] == OPEN_TAKEOFF_MCP_LICENSE


def test_actual_mcp_runtime_line_job_normalizes_through_worker_contract(tmp_path):
    tenant_id = uuid4()
    company_id = uuid4()
    project_id = uuid4()
    document_id = uuid4()
    sheet_id = uuid4()
    doc = ResolvedProjectDocument(
        tenant_id=tenant_id,
        company_id=company_id,
        project_id=project_id,
        document_id=document_id,
        safe_local_path=PLAN,
        original_filename=PLAN.name,
        sha256=__import__("hashlib").sha256(PLAN.read_bytes()).hexdigest(),
    )
    service = OpenTakeoffWorkerService(artifact_root=tmp_path, operation_timeout_seconds=30)
    job = service.create_job(doc, operation="measure_line", payload_hash="runtime-line-37_5")
    context = TakeoffContext(
        tenant_id=tenant_id,
        company_id=company_id,
        project_id=project_id,
        document_id=document_id,
        sheet_id=sheet_id,
        extractor_version="opentakeoff-mcp-runtime-test",
    )
    client = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(tool_timeout_seconds=30, temp_root=tmp_path))

    result = service.run_linear_or_polygon_export(
        job=job,
        client=client,
        context=context,
        options=OpenTakeoffNormalizeOptions(
            trade="electrical",
            scope_category="ev_charging",
            default_description="Runtime line proof",
            page_by_sheet={SHEET: 4},
        ),
        scale=OpenTakeoffScaleConfirmation(
            sheet_id=sheet_id,
            sheet_key=SHEET,
            page_number=4,
            scale_source="printed 15'-0 stall-depth dimension",
            scale_label="calibrated",
            units_per_px=0.08012820512820511,
        ),
        measurements=[
            {"type": "line", "pts": [(3244.32, 1267.2), (3712.32, 1267.2)], "condition": "RUNTIME-LINE"}
        ],
        persist=False,
    )

    assert result.ok is True
    evidence = result.evidence[0]
    assert evidence.takeoff_provider == "open_takeoff"
    assert evidence.quantity == 37.5
    assert evidence.unit == "LF"
    assert evidence.page_number == 4
    assert evidence.scale == "units_per_px:0.08012820512820511"
    assert evidence.tenant_id == tenant_id
    assert evidence.project_id == project_id
    assert client.diagnostics.operation_timings_ms["load_plan"] >= 0
    assert client.diagnostics.operation_timings_ms["measure_line"] >= 0
    assert client.diagnostics.cleaned_temp_dir is True


def test_runtime_timeout_cleans_process_and_temp_dir(tmp_path):
    client = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_path))
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.load_plan(PLAN)
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_TIMEOUT
    client.close(force=True)
    assert client.diagnostics.cleaned_temp_dir is True


def test_worker_job_status_persistence_records_runtime_outcome(tmp_path):
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    doc = ResolvedProjectDocument(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        safe_local_path=PLAN,
        original_filename=PLAN.name,
        sha256=__import__("hashlib").sha256(PLAN.read_bytes()).hexdigest(),
    )
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    job = service.create_job(doc, operation="measure_line", payload_hash="persist")

    create_worker_job_record(conn, job, operation="measure_line", requested_by="staff:test")
    update_worker_job_status(conn, job, status=OpenTakeoffWorkerStatus.RUNNING, attempt_count=1)
    update_worker_job_status(
        conn,
        job,
        status=OpenTakeoffWorkerStatus.COMPLETED,
        artifact_ids=["artifact-1"],
        evidence_ids=["evidence-1"],
        attempt_count=1,
    )
    row = get_worker_job_record(conn, str(job.job_id))

    assert row is not None
    assert row["tenant_id"] == str(doc.tenant_id)
    assert row["company_id"] == str(doc.company_id)
    assert row["project_id"] == str(doc.project_id)
    assert row["document_id"] == str(doc.document_id)
    assert row["provider"] == "open_takeoff"
    assert row["operation"] == "measure_line"
    assert row["status"] == "completed"
    assert json.loads(row["artifact_ids"]) == ["artifact-1"]
    assert json.loads(row["evidence_ids"]) == ["evidence-1"]
    assert row["attempt_count"] == 1
