"""Actual OpenTakeoff MCP runtime tests.

These tests launch the pinned local OpenTakeoff MCP subprocess; they are not fake
provider tests. Low-level process faults are simulated with tiny local scripts
where forcing the real provider to misbehave would be unsafe or nondeterministic.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
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
    get_worker_job_record_by_idempotency,
    update_worker_job_status,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN = REPO_ROOT / "mobi-estimating-phase1/data/golden_set_v2/documents/ca_dgs_24_253614_plans.pdf"
SHEET = "ca_dgs_24_253614_plans.pdf#4"


def _document(path: Path = PLAN) -> ResolvedProjectDocument:
    return ResolvedProjectDocument(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        safe_local_path=path,
        original_filename=path.name,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def _fake_mcp_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_mcp.py"
    script.write_text(body)
    return script


def _runtime_for_script(tmp_path: Path, script: Path, **overrides) -> OpenTakeoffMCPClient:
    config = OpenTakeoffRuntimeConfig(
        command=(sys.executable, str(script)),
        cwd=tmp_path,
        temp_root=tmp_path,
        startup_timeout_seconds=overrides.pop("startup_timeout_seconds", 1),
        tool_timeout_seconds=overrides.pop("tool_timeout_seconds", 1),
        max_stdout_line_bytes=overrides.pop("max_stdout_line_bytes", 10_000),
        max_tool_content_bytes=overrides.pop("max_tool_content_bytes", 10_000),
        max_stderr_bytes=overrides.pop("max_stderr_bytes", 80),
        **overrides,
    )
    return OpenTakeoffMCPClient(config)


def test_opentakeoff_mcp_package_is_pinned_with_lockfile_integrity():
    package = json.loads((REPO_ROOT / "package.json").read_text())
    lock = json.loads((REPO_ROOT / "package-lock.json").read_text())
    locked = lock["packages"][f"node_modules/{OPEN_TAKEOFF_MCP_PACKAGE}"]

    assert package["dependencies"][OPEN_TAKEOFF_MCP_PACKAGE] == OPEN_TAKEOFF_MCP_VERSION
    assert locked["version"] == OPEN_TAKEOFF_MCP_VERSION
    assert locked["integrity"] == OPEN_TAKEOFF_MCP_INTEGRITY
    assert locked["license"] == OPEN_TAKEOFF_MCP_LICENSE


def test_actual_mcp_runtime_line_job_normalizes_through_worker_contract(tmp_path):
    doc = _document()
    tenant_id = doc.tenant_id
    company_id = doc.company_id
    project_id = doc.project_id
    document_id = doc.document_id
    sheet_id = uuid4()
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


def test_startup_failure_is_structured(tmp_path):
    client = OpenTakeoffMCPClient(
        OpenTakeoffRuntimeConfig(command=("definitely-not-opentakeoff",), temp_root=tmp_path)
    )
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.start()
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_START_FAILED


def test_runtime_timeout_cleans_process_and_temp_dir(tmp_path):
    client = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(tool_timeout_seconds=0.001, temp_root=tmp_path))
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.load_plan(PLAN)
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_TIMEOUT
    assert client.diagnostics.cleaned_temp_dir is True


def test_malformed_protocol_response_is_structured_and_cleans_up(tmp_path):
    script = _fake_mcp_script(tmp_path, "import sys\nprint('not-json', flush=True)\n")
    client = _runtime_for_script(tmp_path, script)
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.start()
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR
    assert client.diagnostics.cleaned_temp_dir is True


def test_provider_crash_is_structured_and_cleans_up(tmp_path):
    script = _fake_mcp_script(tmp_path, "import sys\nsys.exit(3)\n")
    client = _runtime_for_script(tmp_path, script)
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.start()
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_CRASH
    assert client.diagnostics.cleaned_temp_dir is True


def test_cancellation_terminates_process_and_persists_cancelled_state(tmp_path):
    script = _fake_mcp_script(
        tmp_path,
        "import json, sys, time\n"
        "for line in sys.stdin:\n"
        "    req=json.loads(line); print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':{'protocolVersion':'2024-11-05','serverInfo':{'version':'fake'}}}), flush=True); time.sleep(30)\n",
    )
    client = _runtime_for_script(tmp_path, script, shutdown_grace_seconds=0.01)
    client.start()
    client.cancel()
    assert client.diagnostics.cancelled is True
    assert client.diagnostics.cleaned_temp_dir is True

    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    doc = _document()
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    job = service.create_job(doc, operation="measure_line", payload_hash="cancel")
    create_worker_job_record(conn, job, operation="measure_line", requested_by="staff:test")
    update_worker_job_status(conn, job, status=OpenTakeoffWorkerStatus.RUNNING, attempt_count=1)
    row = update_worker_job_status(conn, job, status=OpenTakeoffWorkerStatus.CANCELLED)
    assert row["status"] == "cancelled"
    assert row["cancelled_at"] is not None


def test_stdout_line_size_rejection_closes_runtime(tmp_path):
    script = _fake_mcp_script(tmp_path, "print('x' * 200, flush=True)\n")
    client = _runtime_for_script(tmp_path, script, max_stdout_line_bytes=50)
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.start()
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR
    assert client.diagnostics.cleaned_temp_dir is True


def test_tool_content_size_rejection_closes_runtime(tmp_path):
    script = _fake_mcp_script(
        tmp_path,
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    req=json.loads(line)\n"
        "    if req['method']=='initialize': result={'protocolVersion':'2024-11-05','serverInfo':{'version':'fake'}}\n"
        "    else: result={'content':[{'type':'text','text':'x'*200}]}\n"
        "    print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}), flush=True)\n",
    )
    client = _runtime_for_script(tmp_path, script, max_tool_content_bytes=50)
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.takeoff_summary()
    assert exc.value.category == OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR
    assert client.diagnostics.cleaned_temp_dir is True


def test_file_size_and_page_count_reject_before_provider_start(tmp_path):
    too_large = tmp_path / "too-large.pdf"
    too_large.write_bytes(b"%PDF-1.4\n" + b"x" * 100)
    client = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(max_pdf_bytes=10, temp_root=tmp_path))
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.load_plan(too_large)
    assert exc.value.category == OpenTakeoffWorkerErrorCode.RESOURCE_LIMIT
    assert client._process is None

    client = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(max_pages=1, temp_root=tmp_path))
    with pytest.raises(OpenTakeoffRuntimeError) as exc:
        client.load_plan(PLAN)
    assert exc.value.category == OpenTakeoffWorkerErrorCode.RESOURCE_LIMIT
    assert client._process is None


def test_stderr_is_bounded_and_redacted(tmp_path):
    script = _fake_mcp_script(
        tmp_path,
        "import json, sys\n"
        "sys.stderr.write('/tmp/customer/secret_plan.pdf token=abc123 password=hunter2\\n' * 20); sys.stderr.flush()\n"
        "for line in sys.stdin:\n"
        "    req=json.loads(line); print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':{'protocolVersion':'2024-11-05','serverInfo':{'version':'fake'}}}), flush=True)\n",
    )
    client = _runtime_for_script(tmp_path, script, max_stderr_bytes=120)
    client.start()
    client.close()
    assert len(client.diagnostics.stderr_tail) <= 120
    assert "secret_plan.pdf" not in client.diagnostics.stderr_tail
    assert "abc123" not in client.diagnostics.stderr_tail
    assert "hunter2" not in client.diagnostics.stderr_tail


def test_worker_job_status_persistence_records_runtime_outcome(tmp_path):
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    doc = _document()
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


def test_duplicate_idempotency_returns_existing_and_cross_tenant_isolated(tmp_path):
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    first_doc = _document()
    first = service.create_job(first_doc, operation="measure_line", payload_hash="same")
    first_row = create_worker_job_record(conn, first, operation="measure_line", requested_by="staff:test")

    duplicate = service.create_job(first_doc, operation="measure_line", payload_hash="same")
    duplicate_row = create_worker_job_record(conn, duplicate, operation="measure_line", requested_by="staff:test")
    assert duplicate_row["job_id"] == first_row["job_id"]
    idempotent_row = get_worker_job_record_by_idempotency(conn, first.idempotency_key)
    assert idempotent_row is not None
    assert idempotent_row["job_id"] == first_row["job_id"]

    second_doc = ResolvedProjectDocument(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=first_doc.project_id,
        document_id=first_doc.document_id,
        safe_local_path=first_doc.safe_local_path,
        original_filename=first_doc.original_filename,
        sha256=first_doc.sha256,
    )
    second = service.create_job(second_doc, operation="measure_line", payload_hash="same")
    second_row = create_worker_job_record(conn, second, operation="measure_line", requested_by="staff:test")
    assert second_row["job_id"] != first_row["job_id"]
    assert second.idempotency_key != first.idempotency_key


def test_status_transitions_cannot_move_backward_or_mark_failed_completed(tmp_path):
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    job = service.create_job(_document(), operation="measure_line", payload_hash="transitions")
    create_worker_job_record(conn, job, operation="measure_line", requested_by="staff:test")
    update_worker_job_status(conn, job, status=OpenTakeoffWorkerStatus.RUNNING, attempt_count=1)
    update_worker_job_status(
        conn,
        job,
        status=OpenTakeoffWorkerStatus.FAILED,
        error_category=OpenTakeoffWorkerErrorCode.PROVIDER_CRASH,
        safe_error_message="provider crashed",
    )
    with pytest.raises(ValueError, match="invalid_worker_job_transition"):
        update_worker_job_status(conn, job, status=OpenTakeoffWorkerStatus.COMPLETED)
