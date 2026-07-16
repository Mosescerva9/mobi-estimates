"""OpenTakeoff export normalization tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.takeoff import (
    EvidenceClass,
    MeasurementMethod,
    OpenTakeoffNormalizeOptions,
    TakeoffContext,
    TakeoffProviderKind,
    normalize_opentakeoff_export,
)


def _context() -> TakeoffContext:
    return TakeoffContext(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        sheet_id=uuid4(),
        extractor_version="opentakeoff-adapter-test",
    )


def _options() -> OpenTakeoffNormalizeOptions:
    return OpenTakeoffNormalizeOptions(
        trade="finishes",
        scope_category="flooring",
        default_description="Golden Set OpenTakeoff test",
        page_by_sheet={"A-101": 1, "A-101#2": 2},
    )


def _export() -> dict:
    return {
        "schema": "opentakeoff.takeoff_canvas.v1",
        "units": "imperial",
        "sheets": [
            {"sheet_id": "A-101", "units_per_px": 0.027777777777777776},
            {"sheet_id": "A-101#2", "units_per_px": 0.125},
        ],
        "conditions": [
            {"id": "c-area", "finish_tag": "CPT-1"},
            {"id": "c-line", "finish_tag": "BASE"},
            {"id": "c-count", "finish_tag": "DOOR"},
        ],
        "shapes": [
            {
                "id": "shape-area",
                "sheet_id": "A-101",
                "condition_id": "c-area",
                "measure_role": "floor_area",
                "verts_norm": [[0.1, 0.2], [0.4, 0.2], [0.4, 0.6], [0.1, 0.6]],
                "computed": {"area_sf": 437.98, "perimeter_lf": 86.61},
            },
            {
                "id": "shape-line",
                "sheet_id": "A-101#2",
                "condition_id": "c-line",
                "measure_role": "linear",
                "verts_norm": [[0.2, 0.3], [0.6, 0.3]],
                "computed": {"perimeter_lf": 42.5},
            },
            {
                "id": "shape-count",
                "sheet_id": "A-101",
                "condition_id": "c-count",
                "measure_role": "count",
                "verts_norm": [[0.5, 0.5]],
                "computed": {"count": 3},
            },
        ],
    }


def test_normalizes_supported_opentakeoff_shapes_to_canonical_evidence():
    ctx = _context()
    result = normalize_opentakeoff_export(_export(), context=ctx, options=_options())

    assert result.ok is True
    assert result.provider == TakeoffProviderKind.OPEN_TAKEOFF
    assert len(result.evidence) == 3

    area, line, count = result.evidence
    assert area.takeoff_provider == TakeoffProviderKind.OPEN_TAKEOFF.value
    assert area.evidence_class == EvidenceClass.MEASURED.value
    assert area.measurement_method == MeasurementMethod.DIGITAL_MEASUREMENT.value
    assert area.tenant_id == ctx.tenant_id
    assert area.company_id == ctx.company_id
    assert area.project_id == ctx.project_id
    assert area.document_id == ctx.document_id
    assert area.sheet_id == ctx.sheet_id
    assert area.provider_record_id == "shape-area"
    assert area.quantity == Decimal("437.98")
    assert area.unit == "SF"
    assert area.condition == "CPT-1"
    assert area.scale == "units_per_px:0.027777777777777776"
    assert area.region_coordinates == (0.1, 0.2, 0.4, 0.6)

    assert line.provider_record_id == "shape-line"
    assert line.page_number == 2
    assert line.quantity == Decimal("42.5")
    assert line.unit == "LF"
    assert line.condition == "BASE"
    assert line.scale == "units_per_px:0.125"

    assert count.provider_record_id == "shape-count"
    assert count.quantity == Decimal("3")
    assert count.unit == "EA"
    assert count.condition == "DOOR"


def test_unsupported_opentakeoff_schema_quarantines_whole_export():
    result = normalize_opentakeoff_export(
        {"schema": "opentakeoff.future.v9", "shapes": []},
        context=_context(),
        options=_options(),
    )
    assert len(result.evidence) == 0
    assert len(result.quarantined) == 1
    assert result.quarantined[0].reason_code == "unsupported_opentakeoff_schema"


def test_unsupported_measure_role_quarantines_only_that_shape():
    payload = _export()
    payload["shapes"].append(
        {
            "id": "shape-unknown",
            "sheet_id": "A-101",
            "measure_role": "mystery",
            "computed": {"something": 1},
        }
    )

    result = normalize_opentakeoff_export(payload, context=_context(), options=_options())
    assert len(result.evidence) == 3
    assert len(result.quarantined) == 1
    assert result.quarantined[0].reason_code == "unsupported_measure_role"


def test_opentakeoff_export_cannot_set_server_owned_identity():
    payload = _export()
    payload["tenant_id"] = str(uuid4())
    payload["company_id"] = str(uuid4())
    payload["shapes"][0]["project_id"] = str(uuid4())
    ctx = _context()

    result = normalize_opentakeoff_export(payload, context=ctx, options=_options())

    assert len(result.evidence) == 3
    for evidence in result.evidence:
        assert evidence.tenant_id == ctx.tenant_id
        assert evidence.company_id == ctx.company_id
        assert evidence.project_id == ctx.project_id
        assert evidence.document_id == ctx.document_id
        assert evidence.sheet_id == ctx.sheet_id
