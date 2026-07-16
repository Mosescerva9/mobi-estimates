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
    assert "record_count" in UNSUPPORTED_MVP_OPERATIONS
    assert "raster_or_scanned_plan_measurement" in UNSUPPORTED_MVP_OPERATIONS


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
