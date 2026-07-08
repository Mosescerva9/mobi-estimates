#!/usr/bin/env python3
"""Create, validate, and run Mobi real-test PDF batches from a manifest.

This helper is intentionally local/offline. It organizes public/authorized test
PDFs and delegates execution to ``bid_board_batch_shakeout.py``. It never sends
customer messages, approves final estimates, processes payments, or changes
production data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from scripts.bid_board_batch_shakeout import run_batch  # noqa: E402

SCHEMA_VERSION = "mobi-real-test-batch-v1"
ALLOWED_SOURCE_ACCESS = {"public", "authorized_customer", "sample", "internal_owned"}
BLOCKED_SOURCE_ACCESS = {"private_planroom", "login_required", "paywalled", "captcha", "unknown"}


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def template_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": "batch-001",
        "purpose": "Initial no-client real-PDF automation readiness test.",
        "operator_notes": [
            "Use public, sample, internal-owned, or customer-authorized PDFs only.",
            "Do not add login-only/paywalled/private plan-room documents without authorization.",
            "The harness produces internal readiness reports only; it does not deliver estimates.",
        ],
        "success_targets": {
            "pdf_processing_success_rate_min": 0.8,
            "evidence_quote_coverage_rate_min": 0.6,
            "customer_delivery_ready_count_max": 0,
            "safety_violation_count_max": 0,
        },
        "documents": [],
    }


def example_document() -> dict[str, Any]:
    return {
        "id": "example-public-project-001",
        "project_name": "Example Public Bid Project",
        "local_path": "pdfs/example-project.pdf",
        "source_url": "https://example.gov/path/to/public-bid-package.pdf",
        "source_access": "public",
        "source_notes": "Public agency bid package; replace this example before running.",
        "expected_trades": ["electrical", "plumbing", "concrete"],
        "expected_document_types": ["drawings", "specifications"],
        "testing_notes": "Record whether plans are text-readable, scanned/image-heavy, or missing addenda.",
    }


def init_batch(batch_dir: Path, *, force: bool = False) -> dict[str, str]:
    batch_dir.mkdir(parents=True, exist_ok=True)
    for name in ("pdfs", "reports", "workdir"):
        folder = batch_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".gitkeep").touch()

    manifest_path = batch_dir / "manifest.json"
    if manifest_path.exists() and not force:
        raise FileExistsError(f"Manifest already exists: {manifest_path}")
    manifest = template_manifest()
    manifest["documents"] = [example_document()]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    review_path = batch_dir / "review-template.md"
    if force or not review_path.exists():
        review_path.write_text(REVIEW_TEMPLATE, encoding="utf-8")

    return {
        "batch_dir": str(batch_dir.resolve()),
        "manifest": str(manifest_path.resolve()),
        "pdfs": str((batch_dir / "pdfs").resolve()),
        "reports": str((batch_dir / "reports").resolve()),
        "workdir": str((batch_dir / "workdir").resolve()),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object.")
    return data


def _resolve_doc_path(manifest_path: Path, local_path: str) -> Path:
    path = Path(local_path)
    if path.is_absolute():
        raise ValueError("local_path must be relative to the batch directory, not absolute.")
    return (manifest_path.parent / path).resolve()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_manifest(manifest_path: Path, *, require_files: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    manifest = load_manifest(manifest_path)
    issues: list[str] = []
    docs_out: list[dict[str, Any]] = []

    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"schema_version must be {SCHEMA_VERSION!r}.")
    if not manifest.get("batch_id"):
        issues.append("batch_id is required.")

    docs = manifest.get("documents")
    if not isinstance(docs, list):
        issues.append("documents must be a list.")
        docs = []
    if require_files and not docs:
        issues.append("documents must contain at least one PDF before running.")

    seen_ids: set[str] = set()
    for index, doc in enumerate(docs, start=1):
        if not isinstance(doc, dict):
            issues.append(f"documents[{index}] must be an object.")
            continue
        doc_id = str(doc.get("id") or "").strip()
        if not doc_id:
            issues.append(f"documents[{index}].id is required.")
        elif doc_id in seen_ids:
            issues.append(f"documents[{index}].id duplicates {doc_id!r}.")
        seen_ids.add(doc_id)

        source_access = str(doc.get("source_access") or "").strip()
        if source_access in BLOCKED_SOURCE_ACCESS:
            issues.append(f"{doc_id or f'documents[{index}]'} source_access {source_access!r} is blocked for automated tests.")
        elif source_access not in ALLOWED_SOURCE_ACCESS:
            issues.append(
                f"{doc_id or f'documents[{index}]'} source_access must be one of {sorted(ALLOWED_SOURCE_ACCESS)}."
            )
        if not str(doc.get("source_url") or "").strip() and not str(doc.get("source_notes") or "").strip():
            issues.append(f"{doc_id or f'documents[{index}]'} must include source_url or source_notes for auditability.")

        local_path = str(doc.get("local_path") or "").strip()
        if not local_path:
            issues.append(f"{doc_id or f'documents[{index}]'} local_path is required.")
            continue
        try:
            resolved = _resolve_doc_path(manifest_path, local_path)
        except ValueError as exc:
            issues.append(f"{doc_id or local_path} {exc}")
            continue
        pdf_dir = (manifest_path.parent / "pdfs").resolve()
        if not _is_within(resolved, pdf_dir):
            issues.append(f"{doc_id or local_path} local_path must stay inside the batch pdfs/ directory.")
        if resolved.suffix.lower() != ".pdf":
            issues.append(f"{doc_id or local_path} local_path must point to a PDF file.")
        if require_files and not resolved.is_file():
            issues.append(f"{doc_id or local_path} PDF file not found at {resolved}.")

        expected_trades = doc.get("expected_trades", [])
        if expected_trades is not None and not isinstance(expected_trades, list):
            issues.append(f"{doc_id or local_path} expected_trades must be a list.")

        docs_out.append({**doc, "resolved_path": str(resolved)})

    return docs_out, issues


def run_manifest(
    manifest_path: Path,
    *,
    output: Path | None = None,
    workdir: Path | None = None,
    apply_test_inputs: bool = False,
    stop_on_failure: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    docs, issues = validate_manifest(manifest_path, require_files=True)
    if issues:
        raise ValueError("Manifest is not runnable:\n- " + "\n- ".join(issues))
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than 0 when provided.")
    selected = docs[:limit] if limit is not None else docs
    pdfs = [Path(doc["resolved_path"]) for doc in selected]
    project_names = [str(doc.get("project_name") or "").strip() or None for doc in selected]
    stamp = _now_slug()
    base_dir = manifest_path.parent
    workdir = workdir or (base_dir / "workdir" / stamp)
    output = output or (base_dir / "reports" / f"batch-report-{stamp}.json")

    report = run_batch(
        pdfs,
        workdir=workdir,
        apply_test_inputs=apply_test_inputs,
        stop_on_failure=stop_on_failure,
        project_names=project_names,
    )
    report["manifest"] = {
        "path": str(manifest_path.resolve()),
        "batch_id": load_manifest(manifest_path).get("batch_id"),
        "document_count": len(selected),
        "documents": [
            {
                "id": doc.get("id"),
                "project_name": doc.get("project_name"),
                "source_url": doc.get("source_url"),
                "source_access": doc.get("source_access"),
                "expected_trades": doc.get("expected_trades", []),
                "expected_document_types": doc.get("expected_document_types", []),
            }
            for doc in selected
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    review = output.with_suffix(".review.md")
    review.write_text(render_review_markdown(report), encoding="utf-8")
    return {"output": str(output.resolve()), "review": str(review.resolve()), "workdir": str(workdir.resolve()), "summary": report["summary"]}


def render_review_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    safety = report.get("safety", {}) if isinstance(report.get("safety"), dict) else {}
    manifest = report.get("manifest", {}) if isinstance(report.get("manifest"), dict) else {}
    lines = [
        "# Mobi Real-Test Batch Review",
        "",
        f"Generated: {report.get('generated_at', 'unknown')}",
        f"Manifest: {manifest.get('path', 'unknown')}",
        "",
        "## Pass/fail snapshot",
        "",
        f"- PDFs tested: {summary.get('pdf_count', 0)}",
        f"- Clean PDF runs: {summary.get('ok_count', 0)}",
        f"- Failed PDF runs: {summary.get('failed_count', 0)}",
        f"- Blocked readiness count: {summary.get('blocked_readiness_count', 0)}",
        f"- Customer-delivery-ready count: {summary.get('customer_delivery_ready_count', 0)}",
        "",
        "## Evidence and scope explainability",
        "",
        f"- Total scope items: {summary.get('total_scope_item_count', 0)}",
        f"- Scope items with evidence quotes: {summary.get('total_scope_items_with_evidence_quote_count', 0)}",
        f"- Scope items missing evidence quotes: {summary.get('total_scope_items_missing_evidence_quote_count', 0)}",
        f"- Average evidence quote coverage rate: {summary.get('avg_evidence_quote_coverage_rate', 0)}",
        "",
        "## Quantity/pricing blockers",
        "",
        f"- Quantity missing count: {summary.get('total_quantity_missing_count', 0)}",
        f"- Quantity traceable count: {summary.get('total_quantity_traceable_count', 0)}",
        f"- Quantity test-input count: {summary.get('total_quantity_test_input_count', 0)}",
        f"- Formula/check blocked count: {summary.get('total_formula_check_blocked_count', 0)}",
        f"- Missing unit-rate blockers: {summary.get('total_missing_unit_rate_pricing_blocker_count', 0)}",
        f"- Missing subcontract quote blockers: {summary.get('total_missing_subcontract_quote_pricing_blocker_count', 0)}",
        f"- Missing allowance-basis blockers: {summary.get('total_missing_allowance_basis_pricing_blocker_count', 0)}",
        "",
        "## Safety gates",
        "",
        f"- customer_delivery: {safety.get('customer_delivery')}",
        f"- external_messages: {safety.get('external_messages')}",
        f"- final_estimate_approval: {safety.get('final_estimate_approval')}",
        f"- payments: {safety.get('payments')}",
        "",
        "## Reviewer notes",
        "",
        "- [ ] List obvious trades Mobi missed.",
        "- [ ] List trades Mobi invented or over-detected.",
        "- [ ] List scope items missing evidence quotes.",
        "- [ ] List quantity/table/schedule extraction failures.",
        "- [ ] Pick the top one or two failure patterns for the next automation improvement loop.",
        "",
    ]
    return "\n".join(lines)


REVIEW_TEMPLATE = """# Manual Review Template for Real-Test Batch

Use this after each batch run. Review failure patterns, not individual estimates.

## Batch grade

- [ ] Pass: most PDFs processed and reports are useful.
- [ ] Partial: reports are useful but obvious trades/evidence/quantity paths are weak.
- [ ] Fail: pipeline/reporting failed or output is not actionable.

## Top missed trades

| PDF | Expected trade | What Mobi did | Evidence/source note |
|---|---|---|---|

## Top false positives

| PDF | Detected trade | Why it looks wrong | Evidence/source note |
|---|---|---|---|

## Evidence quote gaps

| PDF | Trade/scope | Missing quote issue | Next improvement idea |
|---|---|---|---|

## Quantity/pricing blockers

| PDF | Trade/scope | Blocker | Next improvement idea |
|---|---|---|---|

## Next automation loop

1. Failure pattern to fix first:
2. Why it matters:
3. Acceptance test:
4. PDFs to rerun after fix:
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Mobi real-test PDF batch manifests.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create a real-test batch folder skeleton.")
    init_p.add_argument("batch_dir", type=Path)
    init_p.add_argument("--force", action="store_true")

    validate_p = sub.add_parser("validate", help="Validate a batch manifest.")
    validate_p.add_argument("manifest", type=Path)
    validate_p.add_argument("--require-files", action="store_true")

    run_p = sub.add_parser("run", help="Validate and run a batch manifest.")
    run_p.add_argument("manifest", type=Path)
    run_p.add_argument("--output", type=Path, default=None)
    run_p.add_argument("--workdir", type=Path, default=None)
    run_p.add_argument("--apply-test-inputs", action="store_true")
    run_p.add_argument("--stop-on-failure", action="store_true")
    run_p.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()
    if args.command == "init":
        print(json.dumps(init_batch(args.batch_dir, force=args.force), indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        docs, issues = validate_manifest(args.manifest, require_files=args.require_files)
        result = {"ok": not issues, "document_count": len(docs), "issues": issues}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if issues else 0
    if args.command == "run":
        result = run_manifest(
            args.manifest,
            output=args.output,
            workdir=args.workdir,
            apply_test_inputs=args.apply_test_inputs,
            stop_on_failure=args.stop_on_failure,
            limit=args.limit,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if result["summary"].get("failed_count", 0) else 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
