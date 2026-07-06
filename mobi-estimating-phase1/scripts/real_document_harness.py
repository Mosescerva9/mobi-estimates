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


def _json_response(response: Any) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        data = {"raw_text": response.text[:4000]}
    return {
        "status_code": response.status_code,
        "ok": 200 <= response.status_code < 300,
        "body": data,
    }


def _post(client: Any, path: str, *, json_body: Any | None = None) -> dict[str, Any]:
    if json_body is None:
        return _json_response(client.post(path))
    return _json_response(client.post(path, json=json_body))


def _get(client: Any, path: str) -> dict[str, Any]:
    return _json_response(client.get(path))


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
            upload = client.post(
                "/api/v1/projects/upload",
                data={"project_name": project_name},
                files={"plan": (pdf_path.name, fh, "application/pdf")},
            )
        report["stages"]["upload"] = _json_response(upload)
        if not report["stages"]["upload"]["ok"]:
            return report
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

    return report


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
    print(json.dumps({
        "output": str(output.resolve()),
        "project_id": report.get("project_id"),
        "readiness": initial_readiness,
        "readiness_after_test_inputs": after_test_inputs,
        "owner_review_after_test_inputs": owner_review,
        "workdir": str(workdir.resolve()),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
