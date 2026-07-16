"""Regression tests for the real OpenTakeoff measurement proof artifacts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from app import database
from app.config import settings
from app.takeoff import (
    CanonicalEvidence,
    EvidenceClass,
    MeasurementMethod,
    OpenTakeoffNormalizeOptions,
    TakeoffContext,
    TakeoffProviderKind,
    deserialize_canonical_evidence,
    insert_canonical_evidence,
    list_canonical_evidence_by_project,
    normalize_opentakeoff_export,
)

PROOF_DIR = Path(__file__).resolve().parents[1] / "data" / "opentakeoff_proof"
EXPORT_PATH = PROOF_DIR / "lot50-c011-opentakeoff-export.json"
BENCHMARK_PATH = PROOF_DIR / "lot50-c011-benchmark-result.json"


def _load_artifacts() -> tuple[dict, dict]:
    return json.loads(EXPORT_PATH.read_text()), json.loads(BENCHMARK_PATH.read_text())


def _context(benchmark: dict) -> TakeoffContext:
    return TakeoffContext(
        tenant_id=uuid5(NAMESPACE_URL, "mobi-proof-tenant"),
        company_id=uuid5(NAMESPACE_URL, "mobi-proof-company"),
        project_id=uuid5(NAMESPACE_URL, benchmark["project_id"]),
        document_id=uuid5(NAMESPACE_URL, "mobi-proof-document"),
        sheet_id=uuid5(NAMESPACE_URL, benchmark["sheet_label"]),
        extractor_version="opentakeoff-proof-test",
    )


def _validate_geometric_proof(benchmark: dict) -> None:
    if benchmark.get("measurement_type") != "linear_geometric_measurement":
        raise ValueError("not_geometric_measurement")
    if benchmark.get("opentakeoff_method") != "measure_line":
        raise ValueError("unsupported_opentakeoff_method")
    if benchmark.get("scale_confirmed") is not True:
        raise ValueError("scale_not_confirmed")
    if not benchmark.get("scale_source"):
        raise ValueError("missing_scale_source")
    if benchmark.get("opentakeoff_quantity") is None:
        raise ValueError("missing_opentakeoff_quantity")


def test_real_opentakeoff_export_normalizes_and_persists(tmp_path, monkeypatch):
    export, benchmark = _load_artifacts()
    _validate_geometric_proof(benchmark)
    ctx = _context(benchmark)

    result = normalize_opentakeoff_export(
        export,
        context=ctx,
        options=OpenTakeoffNormalizeOptions(
            trade="electrical",
            scope_category="ev_charging_parking_layout",
            default_description="OpenTakeoff proof linear measurement",
            page_by_sheet={"ca_dgs_24_253614_plans.pdf#4": 4},
        ),
    )

    assert result.ok is True
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.takeoff_provider == TakeoffProviderKind.OPEN_TAKEOFF.value
    assert evidence.evidence_class == EvidenceClass.MEASURED.value
    assert evidence.measurement_method == MeasurementMethod.DIGITAL_MEASUREMENT.value
    assert evidence.provider_record_id == benchmark["provider_record_id"]
    assert evidence.page_number == 4
    assert evidence.quantity == Decimal(str(benchmark["opentakeoff_quantity"]))
    assert evidence.unit == "LF"
    assert evidence.scale == "units_per_px:0.08012820512820511"
    shape = export["shapes"][0]
    xs = [point[0] for point in shape["verts_norm"]]
    ys = [point[1] for point in shape["verts_norm"]]
    assert evidence.region_coordinates == (min(xs), min(ys), max(xs), max(ys))
    assert benchmark["region_coordinates"]["bounding_box"] == [3244.32, 1267.2, 3712.32, 1267.2]
    # Identity is server-owned by context, not the OpenTakeoff export.
    assert evidence.tenant_id == ctx.tenant_id
    assert evidence.company_id == ctx.company_id
    assert evidence.project_id == ctx.project_id
    assert evidence.document_id == ctx.document_id
    assert evidence.sheet_id == ctx.sheet_id

    monkeypatch.setattr(settings, "db_path", tmp_path / "proof.db")
    database.init_db()
    insert_canonical_evidence(evidence)
    rows = list_canonical_evidence_by_project(ctx.project_id, str(ctx.tenant_id), str(ctx.company_id))
    assert len(rows) == 1
    assert deserialize_canonical_evidence(rows[0]) == evidence


def test_ground_truth_comparison_calculation_matches_artifact():
    _, benchmark = _load_artifacts()
    measured = Decimal(str(benchmark["opentakeoff_quantity"]))
    verified = Decimal(str(benchmark["verified_quantity"]))
    absolute = abs(measured - verified)
    percentage = Decimal("0") if verified == 0 else absolute / verified * Decimal("100")

    assert absolute == Decimal(str(benchmark["absolute_error"]))
    assert percentage == Decimal(str(benchmark["percentage_error"]))
    assert percentage <= Decimal("5")


@pytest.mark.parametrize("field", ["scale_confirmed", "scale_source"])
def test_geometric_proof_fails_when_scale_is_absent_or_unconfirmed(field):
    _, benchmark = _load_artifacts()
    broken = dict(benchmark)
    broken[field] = False if field == "scale_confirmed" else ""

    with pytest.raises(ValueError):
        _validate_geometric_proof(broken)


def test_schedule_extracted_evidence_remains_separate_from_opentakeoff_measured_geometry():
    _, benchmark = _load_artifacts()
    ctx = _context(benchmark)

    schedule_evidence = CanonicalEvidence(
        tenant_id=ctx.tenant_id,
        company_id=ctx.company_id,
        project_id=ctx.project_id,
        document_id=ctx.document_id,
        sheet_id=ctx.sheet_id,
        page_number=4,
        takeoff_provider=TakeoffProviderKind.MOBI_NATIVE,
        provider_record_id="c011-schedule-total-stalls",
        evidence_class=EvidenceClass.SCHEDULE_EXTRACTED,
        measurement_method=MeasurementMethod.SCHEDULE_COUNT,
        trade="civil_sitework",
        scope_category="parking_schedule",
        description="C011 schedule/table count; not OpenTakeoff geometry",
        quantity=Decimal("58"),
        unit="EA",
        confidence=Decimal("0.9"),
        extractor_version="schedule-proof-test",
    )

    assert schedule_evidence.evidence_class == EvidenceClass.SCHEDULE_EXTRACTED.value
    assert schedule_evidence.measurement_method == MeasurementMethod.SCHEDULE_COUNT.value
    assert schedule_evidence.takeoff_provider != TakeoffProviderKind.OPEN_TAKEOFF.value
