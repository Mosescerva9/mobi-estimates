"""Internal/local-only bridge: run the REAL merged OpenTakeoff MCP runtime.

This drives the pinned local ``opentakeoff-mcp`` subprocess (not a mock) against
the PR #96 public Golden Set fixture plan (``ca_dgs_24_253614_plans.pdf``) and
reproduces the target C011 line measurement (37.5 LF). It emits a compact JSON
payload for the staff-only estimator takeoff workbench.

Safety / scope:
- Uses only the public golden-set fixture PDF. No confidential customer files.
- persist=False by default; it does not write canonical evidence to any real DB
  and it never delivers a customer estimate.
- This is an internal/local staff proof harness. It is NOT wired into a deployed
  Next.js server action, because the runtime needs a local Node subprocess +
  pdfinfo; see docs/estimator-takeoff-workbench.md.

Run:
    cd mobi-estimating-phase1
    MOBI_DEPLOYMENT_ENVIRONMENT=local PYTHONPATH=. \
        python scripts/opentakeoff_workbench_bridge.py [--out path.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.takeoff import (
    OpenTakeoffMCPClient,
    OpenTakeoffNormalizeOptions,
    OpenTakeoffRuntimeConfig,
    OpenTakeoffScaleConfirmation,
    OpenTakeoffWorkerService,
    ResolvedProjectDocument,
    TakeoffContext,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1_ROOT = Path(__file__).resolve().parents[1]

# PR #96 public Golden Set fixture. C011 is page 4 of this plan set.
PUBLIC_FIXTURE_PDF = (
    PHASE1_ROOT / "data" / "golden_set_v2" / "documents" / "ca_dgs_24_253614_plans.pdf"
)
SHEET_KEY = "ca_dgs_24_253614_plans.pdf#4"
SHEET_LABEL = "C011"
PAGE_NUMBER = 4

# Target C011 line: 5 EVCS Type 2 stalls @ 7.5' = 37'-6" == 37.5 LF.
# Scale calibrated from the printed 15'-0" vertical stall-depth dimension.
LINE_POINTS = [(3244.32, 1267.2), (3712.32, 1267.2)]
UNITS_PER_PX = 0.08012820512820511
SCALE_SOURCE = "manual_calibration_from_printed_dimension"
SCALE_LABEL = "C011 Level GA printed vertical stall depth 15'-0\""
CONDITION = "PROOF-LINE"


def _stable_uuid(name: str):
    return uuid5(NAMESPACE_URL, f"mobi-workbench-bridge:{name}")


def run_bridge() -> dict:
    if not PUBLIC_FIXTURE_PDF.is_file():
        raise SystemExit(f"Public fixture PDF not found: {PUBLIC_FIXTURE_PDF}")

    sha256 = hashlib.sha256(PUBLIC_FIXTURE_PDF.read_bytes()).hexdigest()
    document = ResolvedProjectDocument(
        tenant_id=_stable_uuid("tenant"),
        company_id=_stable_uuid("company"),
        project_id=_stable_uuid("project"),
        document_id=_stable_uuid("document"),
        safe_local_path=PUBLIC_FIXTURE_PDF,
        original_filename=PUBLIC_FIXTURE_PDF.name,
        sha256=sha256,
    )
    sheet_id = _stable_uuid(SHEET_LABEL)
    context = TakeoffContext(
        tenant_id=document.tenant_id,
        company_id=document.company_id,
        project_id=document.project_id,
        document_id=document.document_id,
        sheet_id=sheet_id,
        extractor_version="opentakeoff-workbench-bridge",
    )

    service = OpenTakeoffWorkerService(artifact_root=REPO_ROOT / "tmp", operation_timeout_seconds=60)
    job = service.create_job(document, operation="measure_line", payload_hash="workbench-c011-line-37_5")

    # Real subprocess runtime. cwd defaults to repo root where the pinned
    # node_modules/opentakeoff-mcp/dist/server.js lives.
    client = OpenTakeoffMCPClient(OpenTakeoffRuntimeConfig(tool_timeout_seconds=60))

    result = service.run_linear_or_polygon_export(
        job=job,
        client=client,
        context=context,
        options=OpenTakeoffNormalizeOptions(
            trade="electrical",
            scope_category="ev_charging",
            default_description="OpenTakeoff workbench C011 line proof",
            page_by_sheet={SHEET_KEY: PAGE_NUMBER},
        ),
        scale=OpenTakeoffScaleConfirmation(
            sheet_id=sheet_id,
            sheet_key=SHEET_KEY,
            page_number=PAGE_NUMBER,
            scale_source=SCALE_SOURCE,
            scale_label=SCALE_LABEL,
            units_per_px=UNITS_PER_PX,
        ),
        measurements=[{"type": "line", "pts": LINE_POINTS, "condition": CONDITION}],
        persist=False,
    )

    if not result.ok or not result.evidence:
        raise SystemExit(f"Runtime produced no evidence: ok={result.ok}")
    evidence = result.evidence[0]

    xs = [p[0] for p in LINE_POINTS]
    ys = [p[1] for p in LINE_POINTS]
    payload = {
        "runtime": "real_opentakeoff_mcp_subprocess",
        "engine_version": client.engine_version,
        "runtime_reported_version": client.diagnostics.engine_version,
        "provider": evidence.takeoff_provider,
        "provider_record_id": evidence.provider_record_id,
        "provenance_label": "OpenTakeoff measured",
        "evidence_class": evidence.evidence_class,
        "measurement_method": evidence.measurement_method,
        "review_status": evidence.review_status,
        "sheet_label": SHEET_LABEL,
        "sheet_key": SHEET_KEY,
        "page_number": evidence.page_number,
        "scale": evidence.scale,
        "units_per_px": UNITS_PER_PX,
        "quantity": float(evidence.quantity) if evidence.quantity is not None else None,
        "unit": evidence.unit,
        "trade": evidence.trade,
        "scope_category": evidence.scope_category,
        "condition": evidence.condition,
        "region_coordinates": list(evidence.region_coordinates) if evidence.region_coordinates else None,
        "marked_geometry": {"type": "line", "pts": [list(p) for p in LINE_POINTS]},
        "source_region": {"bounding_box": [min(xs), min(ys), max(xs), max(ys)]},
        "operation_timings_ms": dict(client.diagnostics.operation_timings_ms),
        "cleaned_temp_dir": client.diagnostics.cleaned_temp_dir,
        "training_eligibility": "not_training_eligible",
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args()

    payload = run_bridge()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n")
    print(rendered)

    ok = (
        payload["quantity"] == 37.5
        and payload["unit"] == "LF"
        and payload["provider"] == "open_takeoff"
        and payload["scale"] == "units_per_px:0.08012820512820511"
        and payload["page_number"] == PAGE_NUMBER
    )
    print(
        f"\nWORKBENCH RUNTIME PROOF: {'PASS' if ok else 'FAIL'} "
        f"({payload['quantity']} {payload['unit']} via {payload['engine_version']})",
        file=sys.stderr,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
