"""OpenTakeoff worker/service boundary tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.takeoff import (
    OpenTakeoffNormalizeOptions,
    OpenTakeoffOperation,
    OpenTakeoffScaleConfirmation,
    OpenTakeoffWorkerErrorCode,
    OpenTakeoffWorkerService,
    ResolvedProjectDocument,
    SUPPORTED_MVP_OPERATIONS,
    UNSUPPORTED_MVP_OPERATIONS,
    TakeoffContext,
    build_count_export,
)


class FakeOpenTakeoffClient:
    def __init__(self) -> None:
        self.closed = False
        self.calls: list[tuple[str, object]] = []
        self.export = {
            "schema": "opentakeoff.takeoff_canvas.v1",
            "sheets": [{"sheet_id": "sheet#1", "units_per_px": 0.1}],
            "conditions": [{"id": "c1", "finish_tag": "PROOF"}],
            "shapes": [
                {
                    "id": "shape-1",
                    "sheet_id": "sheet#1",
                    "condition_id": "c1",
                    "measure_role": "linear",
                    "verts_norm": [[0.1, 0.2], [0.5, 0.2]],
                    "computed": {"perimeter_lf": 40.0},
                }
            ],
        }

    def load_plan(self, path: Path) -> dict:
        self.calls.append(("load_plan", path))
        return {"ok": True}

    def sheet_info(self, sheet: str) -> dict:
        self.calls.append(("sheet_info", sheet))
        return {"ok": True}

    def set_scale(self, sheet: str, scale: OpenTakeoffScaleConfirmation) -> dict:
        self.calls.append(("set_scale", scale))
        return {"ok": True}

    def measure_line(self, sheet: str, pts: list[tuple[float, float]], condition: str) -> dict:
        self.calls.append(("measure_line", {"sheet": sheet, "pts": pts, "condition": condition}))
        return {"shape_id": "shape-1", "length_lf": 40.0}

    def measure_polygon(self, sheet: str, verts: list[tuple[float, float]], condition: str) -> dict:
        self.calls.append(("measure_polygon", {"sheet": sheet, "verts": verts, "condition": condition}))
        return {"shape_id": "shape-2", "area_sf": 100.0}

    def export_takeoff(self) -> dict:
        self.calls.append(("export_takeoff", None))
        return self.export

    def close(self) -> None:
        self.closed = True


def _document(tmp_path) -> ResolvedProjectDocument:
    pdf = tmp_path / "plan.pdf"
    pdf.write_bytes(b"%PDF-1.4\nproof")
    return ResolvedProjectDocument(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        safe_local_path=pdf,
        original_filename="plan.pdf",
        sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
    )


def test_worker_operation_sets_match_benchmark_selection():
    assert OpenTakeoffOperation.MEASURE_LINE in SUPPORTED_MVP_OPERATIONS
    assert OpenTakeoffOperation.MEASURE_POLYGON in SUPPORTED_MVP_OPERATIONS
    # The deterministic marker-tally count operation is supported; the hypothetical
    # MCP-native count primitive (record_count) stays unsupported.
    assert OpenTakeoffOperation.MEASURE_COUNT in SUPPORTED_MVP_OPERATIONS
    assert "record_count" in UNSUPPORTED_MVP_OPERATIONS
    assert "raster_or_scanned_plan_measurement" in UNSUPPORTED_MVP_OPERATIONS


def test_build_count_export_tallies_markers_as_ea_canonical_shape():
    marks = [(10.0, 10.0), (20.0, 20.0), (30.0, 10.0)]
    export = build_count_export(
        sheet_key="plan.pdf#4", units_per_px=0.08, marks=marks, condition="EV-COUNT"
    )
    assert export["schema"] == "opentakeoff.takeoff_canvas.v1"
    assert export["sheets"] == [{"sheet_id": "plan.pdf#4", "units_per_px": 0.08}]
    shape = export["shapes"][0]
    assert shape["measure_role"] == "count"
    assert shape["computed"]["count"] == 3
    assert shape["verts_norm"] == [[10.0, 10.0], [20.0, 20.0], [30.0, 10.0]]
    # No scale is still a valid count (EA does not depend on scale).
    no_scale = build_count_export(sheet_key="plan.pdf#4", units_per_px=None, marks=marks, condition="c")
    assert "units_per_px" not in no_scale["sheets"][0]


def test_worker_runs_count_export_as_deterministic_marker_tally(tmp_path):
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    doc = _document(tmp_path)
    job = service.create_job(doc, operation="measure_count", payload_hash="payload")
    ctx = TakeoffContext(
        tenant_id=doc.tenant_id,
        company_id=doc.company_id,
        project_id=doc.project_id,
        document_id=doc.document_id,
        sheet_id=uuid4(),
        extractor_version="worker-test",
    )
    client = FakeOpenTakeoffClient()
    marks = [(10.0, 10.0), (20.0, 20.0), (30.0, 10.0), (40.0, 40.0)]
    count_export = build_count_export(
        sheet_key="sheet#1", units_per_px=0.1, marks=marks, condition="EV-COUNT"
    )
    result = service.run_count_export(
        job=job,
        client=client,
        context=ctx,
        options=OpenTakeoffNormalizeOptions(
            trade="electrical",
            scope_category="ev_charging",
            default_description="Count proof",
            page_by_sheet={"sheet#1": 3},
        ),
        scale=OpenTakeoffScaleConfirmation(
            sheet_id=ctx.sheet_id,
            sheet_key="sheet#1",
            page_number=3,
            scale_source="printed_dimension",
            scale_label="calibrated",
            units_per_px=0.1,
        ),
        count_export=count_export,
        persist=False,
    )

    assert client.closed is True
    assert result.ok is True
    evidence = result.evidence[0]
    assert evidence.takeoff_provider == "open_takeoff"
    assert evidence.evidence_class == "measured"
    assert evidence.quantity == 4
    assert evidence.unit == "EA"
    assert evidence.page_number == 3
    assert evidence.review_status == "pending"
    assert evidence.region_coordinates == (10.0, 10.0, 40.0, 40.0)
    assert evidence.tenant_id == doc.tenant_id
    # The real document is loaded and the scale set, but the tally is deterministic:
    # no MCP measurement / export tool is called for a count.
    assert ("load_plan", doc.safe_local_path) in client.calls
    assert any(call[0] == "set_scale" for call in client.calls)
    assert not any(
        call[0] in {"measure_line", "measure_polygon", "export_takeoff"} for call in client.calls
    )


def test_worker_count_requires_scale_confirmation(tmp_path):
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    doc = _document(tmp_path)
    job = service.create_job(doc, operation="measure_count", payload_hash="payload")
    ctx = TakeoffContext(
        tenant_id=doc.tenant_id,
        company_id=doc.company_id,
        project_id=doc.project_id,
        document_id=doc.document_id,
        sheet_id=uuid4(),
        extractor_version="worker-test",
    )
    with pytest.raises(ValueError, match=OpenTakeoffWorkerErrorCode.SCALE_UNCONFIRMED.value):
        service.run_count_export(
            job=job,
            client=FakeOpenTakeoffClient(),
            context=ctx,
            options=OpenTakeoffNormalizeOptions(trade="electrical", scope_category="test"),
            scale=OpenTakeoffScaleConfirmation(
                sheet_id=ctx.sheet_id, sheet_key="sheet#1", page_number=1, scale_source="", scale_label=""
            ),
            count_export=build_count_export(
                sheet_key="sheet#1", units_per_px=0.1, marks=[(1.0, 1.0)], condition="c"
            ),
            persist=False,
        )


def test_create_job_rejects_customer_supplied_or_tampered_paths(tmp_path):
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    missing = ResolvedProjectDocument(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        safe_local_path=tmp_path / "missing.pdf",
        original_filename="missing.pdf",
        sha256="bad",
    )
    with pytest.raises(ValueError, match=OpenTakeoffWorkerErrorCode.DOCUMENT_NOT_FOUND.value):
        service.create_job(missing, operation="measure_line", payload_hash="x")

    doc = _document(tmp_path)
    tampered = ResolvedProjectDocument(**{**doc.__dict__, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="document_hash_mismatch"):
        service.create_job(tampered, operation="measure_line", payload_hash="x")


def test_idempotency_key_includes_tenant_company_project_and_document(tmp_path):
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    doc = _document(tmp_path)
    same_file_other_tenant = ResolvedProjectDocument(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=doc.project_id,
        document_id=doc.document_id,
        safe_local_path=doc.safe_local_path,
        original_filename=doc.original_filename,
        sha256=doc.sha256,
    )

    first = service.create_job(doc, operation="measure_line", payload_hash="payload")
    second = service.create_job(same_file_other_tenant, operation="measure_line", payload_hash="payload")

    assert str(doc.tenant_id) in first.idempotency_key
    assert str(doc.company_id) in first.idempotency_key
    assert str(doc.project_id) in first.idempotency_key
    assert str(doc.document_id) in first.idempotency_key
    assert first.idempotency_key != second.idempotency_key


def test_worker_requires_explicit_scale_confirmation(tmp_path):
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    doc = _document(tmp_path)
    job = service.create_job(doc, operation="measure_line", payload_hash="payload")
    ctx = TakeoffContext(
        tenant_id=doc.tenant_id,
        company_id=doc.company_id,
        project_id=doc.project_id,
        document_id=doc.document_id,
        sheet_id=uuid4(),
        extractor_version="worker-test",
    )
    scale = OpenTakeoffScaleConfirmation(
        sheet_id=ctx.sheet_id,
        sheet_key="sheet#1",
        page_number=1,
        scale_source="",
        scale_label="",
    )
    with pytest.raises(ValueError, match=OpenTakeoffWorkerErrorCode.SCALE_UNCONFIRMED.value):
        service.run_linear_or_polygon_export(
            job=job,
            client=FakeOpenTakeoffClient(),
            context=ctx,
            options=OpenTakeoffNormalizeOptions(trade="electrical", scope_category="test"),
            scale=scale,
            measurements=[{"type": "line", "pts": [(0, 0), (1, 1)], "condition": "PROOF"}],
            persist=False,
        )


def test_worker_runs_line_export_normalizes_with_server_owned_identity(tmp_path):
    service = OpenTakeoffWorkerService(artifact_root=tmp_path)
    doc = _document(tmp_path)
    job = service.create_job(doc, operation="measure_line", payload_hash="payload")
    ctx = TakeoffContext(
        tenant_id=doc.tenant_id,
        company_id=doc.company_id,
        project_id=doc.project_id,
        document_id=doc.document_id,
        sheet_id=uuid4(),
        extractor_version="worker-test",
    )
    client = FakeOpenTakeoffClient()
    result = service.run_linear_or_polygon_export(
        job=job,
        client=client,
        context=ctx,
        options=OpenTakeoffNormalizeOptions(
            trade="electrical",
            scope_category="ev_charging",
            default_description="Worker proof",
            page_by_sheet={"sheet#1": 7},
        ),
        scale=OpenTakeoffScaleConfirmation(
            sheet_id=ctx.sheet_id,
            sheet_key="sheet#1",
            page_number=7,
            scale_source="printed_dimension",
            scale_label="1/4\" = 1'-0\"",
            units_per_px=0.1,
        ),
        measurements=[{"type": "line", "pts": [(0, 0), (10, 0)], "condition": "PROOF"}],
        persist=False,
    )

    assert client.closed is True
    assert result.ok is True
    evidence = result.evidence[0]
    assert evidence.provider_record_id == "shape-1"
    assert evidence.takeoff_provider == "open_takeoff"
    assert evidence.quantity == 40
    assert evidence.unit == "LF"
    assert evidence.page_number == 7
    assert evidence.region_coordinates == (0.1, 0.2, 0.5, 0.2)
    assert evidence.tenant_id == doc.tenant_id
    assert evidence.company_id == doc.company_id
    assert evidence.project_id == doc.project_id
    assert evidence.document_id == doc.document_id
    assert evidence.sheet_id == ctx.sheet_id
