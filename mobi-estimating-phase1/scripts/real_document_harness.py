#!/usr/bin/env python3
"""Run a real construction PDF through the Mobi estimating engine smoke pipeline.

This is a local/test harness for bid-board document shakeouts. It uses FastAPI's
TestClient against the engine app, writes to an isolated temp database/upload dir
by default, and produces a JSON report with stage responses and blockers.

It does not send messages, create customer deliverables, process payments, or
approve/finalize construction estimates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))


def _configure_env(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MOBI_DB_PATH", str(workdir / "mobi.db"))
    os.environ.setdefault("MOBI_UPLOAD_DIR", str(workdir / "uploads"))
    os.environ.setdefault("MOBI_ENABLED_TRADES", "painting,demo_concrete,general_trade")


def _json_response(response: Any, *, duration_ms: int | None = None) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        data = {"raw_text": response.text[:4000]}
    result = {
        "status_code": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "body": data,
    }
    if duration_ms is not None:
        result["duration_ms"] = duration_ms
    return result


def _post(client: Any, path: str, *, json_body: Any | None = None) -> dict[str, Any]:
    start = time.perf_counter()
    if json_body is None:
        response = client.post(path)
    else:
        response = client.post(path, json=json_body)
    return _json_response(response, duration_ms=int((time.perf_counter() - start) * 1000))


def _get(client: Any, path: str) -> dict[str, Any]:
    start = time.perf_counter()
    response = client.get(path)
    return _json_response(response, duration_ms=int((time.perf_counter() - start) * 1000))


def _item_count(stage: dict[str, Any]) -> int | None:
    body = stage.get("body") if isinstance(stage, dict) else None
    if not isinstance(body, dict):
        return None
    items = body.get("items")
    if isinstance(items, list):
        return len(items)
    total = body.get("total")
    if isinstance(total, int):
        return total
    return None


def _error_summary(stage: dict[str, Any]) -> dict[str, Any] | None:
    if stage.get("ok"):
        return None
    body = stage.get("body") if isinstance(stage, dict) else None
    if not isinstance(body, dict):
        return {"message": "Stage failed without a JSON body."}
    detail = body.get("detail")
    if isinstance(detail, dict):
        return {
            "code": detail.get("code") or detail.get("error_code"),
            "message": detail.get("message") or detail.get("detail"),
        }
    if isinstance(detail, str):
        return {"message": detail}
    if isinstance(body.get("raw_text"), str):
        return {"message": body["raw_text"][:500]}
    return {"message": body.get("message") or body.get("error") or "Stage failed."}


def _build_stage_summary(report: dict[str, Any]) -> dict[str, Any]:
    stages = report.get("stages", {})
    per_stage: dict[str, Any] = {}
    failed: list[dict[str, Any]] = []
    for name, stage in stages.items():
        if not isinstance(stage, dict):
            continue
        summary = {
            "ok": bool(stage.get("ok")),
            "status_code": stage.get("status_code"),
            "duration_ms": stage.get("duration_ms"),
        }
        count = _item_count(stage)
        if count is not None:
            summary["item_count"] = count
        error = _error_summary(stage)
        if error:
            summary["error"] = error
            failed.append({"stage": name, **error})
        per_stage[name] = summary

    readiness_stage = stages.get("readiness_after_test_inputs") or stages.get("readiness")
    owner_review_stage = stages.get("owner_review_after_test_inputs") or stages.get("owner_review")
    readiness = readiness_stage.get("body", {}) if isinstance(readiness_stage, dict) else {}
    owner_review = owner_review_stage.get("body", {}) if isinstance(owner_review_stage, dict) else {}
    register = owner_review.get("review_packet", {}).get("assumptions_register", {}) if isinstance(owner_review, dict) else {}
    register_summary = register.get("summary", {}) if isinstance(register, dict) else {}
    sheets = stages.get("sheets", {})
    coverage_validate = stages.get("coverage_validate", {})
    scope_items = stages.get("scope_items", {})
    quantity_requirements = stages.get("quantity_requirements", {})
    qa_findings = stages.get("qa_findings", {})
    provenance = readiness.get("details", {}).get("provenance_confidence", {}) if isinstance(readiness, dict) else {}
    successful = sum(1 for item in per_stage.values() if item.get("ok"))
    total = len(per_stage)
    return {
        "stage_count": total,
        "ok_stage_count": successful,
        "failed_stage_count": total - successful,
        "stage_success_rate": round(successful / total, 4) if total else 0,
        "failed_stages": failed,
        "per_stage": per_stage,
        "outputs": {
            "sheet_count": _item_count(sheets) or 0,
            "coverage_finding_count": len(coverage_validate.get("body", {}).get("findings", [])) if isinstance(coverage_validate.get("body"), dict) else 0,
            "scope_item_count": _item_count(scope_items) or 0,
            "scope_items_with_trusted_evidence_count": provenance.get("items_with_trusted_evidence_count", 0) if isinstance(provenance, dict) else 0,
            "scope_items_missing_trusted_evidence_count": provenance.get("items_missing_trusted_evidence_count", 0) if isinstance(provenance, dict) else 0,
            "low_confidence_item_count": provenance.get("low_confidence_item_count", 0) if isinstance(provenance, dict) else 0,
            "quantity_basis_unclear_count": provenance.get("quantity_basis_unclear_count", 0) if isinstance(provenance, dict) else 0,
            "trusted_evidence_coverage_rate": provenance.get("trusted_evidence_coverage_rate", 0) if isinstance(provenance, dict) else 0,
            "assumption_count": register_summary.get("assumption_count", 0),
            "exclusion_count": register_summary.get("exclusion_count", 0),
            "open_question_count": register_summary.get("open_question_count", 0),
            "register_blocking_entry_count": register_summary.get("blocking_entry_count", 0),
            "quantity_requirement_count": _item_count(quantity_requirements) or 0,
            "qa_finding_count": _item_count(qa_findings) or 0,
            "readiness_status": readiness.get("status") if isinstance(readiness, dict) else None,
            "readiness_blockers": readiness.get("blockers") if isinstance(readiness, dict) else None,
            "owner_review_status": owner_review.get("status") if isinstance(owner_review, dict) else None,
            "customer_delivery_ready": bool(readiness.get("customer_delivery_ready")) if isinstance(readiness, dict) else False,
        },
    }


def _finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report["summary"] = _build_stage_summary(report)
    return report


def _apply_test_quantity_and_pricing_inputs(client: Any, project_id: str, report: dict[str, Any]) -> None:
    """Apply explicit fictional inputs so the harness can test readiness flow.

    These values are only for local smoke testing. They are marked in the source
    fields and must never be treated as market pricing or final estimate data.
    """
    base = f"/api/v1/projects/{project_id}"
    reqs = _get(client, f"{base}/quantity-requirements")
    report["stages"]["test_input_quantity_requirements_before"] = reqs
    if reqs["ok"]:
        for req in reqs["body"].get("items", []):
            if req.get("status") != "open":
                continue
            report["stages"][f"test_apply_quantity_{req['id']}"] = _post(
                client,
                f"{base}/quantity-requirements/{req['id']}/apply",
                json_body={
                    "quantity": "10",
                    "unit": req.get("suggested_unit") or "EA",
                    "source": "harness_test_only_quantity",
                },
            )

    scope = _get(client, f"{base}/scope-items?limit=200")
    report["stages"]["test_input_scope_items_before_pricing"] = scope
    if scope["ok"]:
        for item in scope["body"].get("items", []):
            detail = _get(client, f"{base}/scope-items/{item['id']}")
            trade_data = detail.get("body", {}).get("trade_data") or {}
            method = trade_data.get("pricing_method")
            if not method or trade_data.get("pricing_ready"):
                continue
            report["stages"][f"test_apply_pricing_{item['id']}"] = _post(
                client,
                f"{base}/pricing/generic-inputs/{item['id']}/apply",
                json_body={
                    "pricing_method": method,
                    "amount": "100",
                    "source": "harness_test_only_pricing",
                },
            )

    report["stages"]["qa_findings_after_test_inputs"] = _post(client, f"{base}/qa/findings/draft")
    report["stages"]["readiness_after_test_inputs"] = _get(client, f"{base}/estimate-readiness")
    report["stages"]["owner_review_after_test_inputs"] = _get(client, f"{base}/owner-review/package")


def run_harness(pdf_path: Path, *, project_name: str, workdir: Path, apply_test_inputs: bool = False) -> dict[str, Any]:
    _configure_env(workdir)

    # Import after env is configured so settings point at the harness DB/files.
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.database import init_db
    from app.main import app

    settings.db_path = workdir / "mobi.db"
    settings.upload_dir = workdir / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.enabled_trades = ["painting", "demo_concrete", "general_trade"]
    init_db()

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_pdf": str(pdf_path.resolve()),
        "project_name": project_name,
        "workdir": str(workdir.resolve()),
        "safety": {
            "customer_delivery": False,
            "external_messages": False,
            "final_estimate_approval": False,
            "payments": False,
            "test_inputs_only": apply_test_inputs,
        },
        "project_id": None,
        "stages": {},
    }

    with TestClient(app) as client:
        with pdf_path.open("rb") as fh:
            start = time.perf_counter()
            upload = client.post(
                "/api/v1/projects/upload",
                data={"project_name": project_name},
                files={"plan": (pdf_path.name, fh, "application/pdf")},
            )
        report["stages"]["upload"] = _json_response(upload, duration_ms=int((time.perf_counter() - start) * 1000))
        if not report["stages"]["upload"]["ok"]:
            return _finalize_report(report)
        project_id = report["stages"]["upload"]["body"]["project_id"]
        report["project_id"] = project_id
        base = f"/api/v1/projects/{project_id}"

        stage_calls: list[tuple[str, str, Any | None]] = [
            ("process", f"{base}/process", None),
            ("coverage_draft", f"{base}/coverage/draft", None),
            ("generic_scope_draft", f"{base}/coverage/generic-scope/draft", None),
            ("pricing_methods_draft", f"{base}/pricing/generic-methods/draft", {}),
            ("quantity_requirements_draft", f"{base}/quantity-requirements/draft", None),
            ("qa_findings_draft", f"{base}/qa/findings/draft", None),
        ]
        for name, path, body in stage_calls:
            report["stages"][name] = _post(client, path, json_body=body)

        for name, path in [
            ("sheets", f"{base}/sheets?limit=200"),
            ("coverage", f"{base}/coverage"),
            ("coverage_validate", f"{base}/coverage/validate"),
            ("scope_items", f"{base}/scope-items?limit=200"),
            ("quantity_requirements", f"{base}/quantity-requirements"),
            ("qa_findings", f"{base}/qa/findings"),
            ("boe", f"{base}/boe/draft"),
            ("readiness", f"{base}/estimate-readiness"),
            ("owner_review", f"{base}/owner-review/package"),
        ]:
            report["stages"][name] = _get(client, path)

        if apply_test_inputs:
            _apply_test_quantity_and_pricing_inputs(client, project_id, report)

    return _finalize_report(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real PDF through the Mobi estimating smoke pipeline.")
    parser.add_argument("pdf", type=Path, help="Path to a PDF plan/spec set")
    parser.add_argument("--project-name", default="Harness Project", help="Project name to use in the engine")
    parser.add_argument("--workdir", type=Path, default=None, help="Harness working directory; defaults to a temp dir")
    parser.add_argument("--output", type=Path, default=None, help="JSON report path")
    parser.add_argument(
        "--apply-test-inputs",
        action="store_true",
        help="Apply explicit fictional quantity/pricing inputs to exercise readiness flow.",
    )
    args = parser.parse_args()

    if not args.pdf.exists() or not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="mobi-real-doc-"))
    report = run_harness(
        args.pdf,
        project_name=args.project_name,
        workdir=workdir,
        apply_test_inputs=args.apply_test_inputs,
    )
    output = args.output or (workdir / "real_document_harness_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    initial_readiness = report.get("stages", {}).get("readiness", {}).get("body", {}).get("status")
    after_test_inputs = report.get("stages", {}).get("readiness_after_test_inputs", {}).get("body", {}).get("status")
    owner_review = report.get("stages", {}).get("owner_review_after_test_inputs", {}).get("body", {}).get("status")
    failed_stage_count = report.get("summary", {}).get("failed_stage_count", 0)
    print(json.dumps({
        "output": str(output.resolve()),
        "project_id": report.get("project_id"),
        "readiness": initial_readiness,
        "readiness_after_test_inputs": after_test_inputs,
        "owner_review_after_test_inputs": owner_review,
        "failed_stage_count": failed_stage_count,
        "workdir": str(workdir.resolve()),
    }, indent=2, sort_keys=True))
    return 1 if failed_stage_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
