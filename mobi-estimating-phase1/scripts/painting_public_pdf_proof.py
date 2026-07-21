#!/usr/bin/env python3
"""Prove one real public-PDF painting evidence-to-pricing-preview slice.

The proof is local/internal only. It uses a tracked public project manual, verifies two
specific Section 099000 specification pages, runs the deterministic ``source_text``
provider, approves the one fully source-backed 100-SF mockup scope item, and exercises
an internal pricing preview with an explicitly fictional fixture cost book.

It never creates an estimate version, approves a final estimate, creates/issues a
proposal, sends a message, processes a payment, or unlocks customer delivery.
"""

from __future__ import annotations

import argparse
import hashlib
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

DEFAULT_PDF = ENGINE_ROOT / "data/golden_set/documents/norman_ruby_grant_park_specs_amendment_one.pdf"
EXPECTED_PDF_SHA256 = "41fa4d685c8b5ccc66b14ff15815846e9823fd0faa8d4068e43da767393cd993"
SOURCE_URL = (
    "https://www.normanok.gov/sites/default/files/documents/2020-12/"
    "ruby_grant_park_-_specs_-_amendment_one.pdf"
)
TENANT_HEADERS = {
    "X-Mobi-Tenant-Id": "painting_public_proof_tenant",
    "X-Mobi-Company-Id": "painting_public_proof_company",
}
TARGET_PAGES = {
    258: ("099000-1", "PAINTING"),
    259: ("099000-2", "PAINTING"),
}


def _configure(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    os.environ["MOBI_DB_PATH"] = str(workdir / "mobi.db")
    os.environ["MOBI_UPLOAD_DIR"] = str(workdir / "uploads")
    os.environ["MOBI_DEPLOYMENT_ENVIRONMENT"] = "local"
    os.environ["MOBI_ENGINE_AUTH_MODE"] = "local_dev_open"
    os.environ["MOBI_ENABLED_TRADES"] = "painting,demo_concrete,general_trade"
    os.environ["MOBI_EXTRACTION_PROVIDER"] = "source_text"
    os.environ["MOBI_ENABLE_LIVE_EXTRACTION"] = "false"


def _payload(response: Any) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:
        body = {"raw_text": response.text[:4000]}
    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "body": body,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paged_items(client: Any, path: str, *, page_size: int = 200) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = client.get(
            path,
            params={"limit": page_size, "offset": offset},
            headers=TENANT_HEADERS,
        )
        response.raise_for_status()
        body = response.json()
        batch = body.get("items") or []
        items.extend(batch)
        total = int(body.get("total") or len(items))
        if not batch or len(items) >= total:
            return items
        offset += len(batch)


def _post_checked(client: Any, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post(path, json=body, headers=TENANT_HEADERS) if body is not None else client.post(path, headers=TENANT_HEADERS)
    response.raise_for_status()
    return response.json()


def _seed_fixture_painting_cost_book(client: Any) -> str:
    """Create a fictional, proof-only painting cost book and return its version id."""
    cost_book = _post_checked(client, "/api/v1/cost-books", {"name": "PAINTING PROOF FIXTURE ONLY"})
    cost_book_id = cost_book["id"]
    version = _post_checked(
        client,
        f"/api/v1/cost-books/{cost_book_id}/versions",
        {
            "version_label": "fixture-v1-not-market-pricing",
            "effective_date": "2026-01-01",
            "pricing_date": "2026-01-01",
        },
    )
    version_id = version["id"]
    base = f"/api/v1/cost-books/{cost_book_id}/versions/{version_id}"
    source = _post_checked(
        client,
        f"{base}/sources",
        {
            "source_type": "contractor_rate",
            "source_name": "FICTIONAL HARNESS TEST ONLY - NOT MARKET PRICING",
            "effective_date": "2026-01-01",
            "verified": True,
        },
    )
    source_id = source["id"]

    _post_checked(
        client,
        f"{base}/labor-rates",
        {
            "classification": "PAINTER",
            "trade_code": "painting",
            "rate_type": "manual_all_in",
            "manual_all_in_rate": "50.00",
            "effective_date": "2026-01-01",
            "source_id": source_id,
        },
    )
    for code, value in (("PROD-PT-PREP", "200"), ("PROD-PT-FINISH", "150")):
        _post_checked(
            client,
            f"{base}/production-rates",
            {
                "production_code": code,
                "trade_code": "painting",
                "scope_category": "interior_walls",
                "quantity_unit": "SF",
                "basis": "units_per_labor_hour",
                "value": value,
                "effective_date": "2026-01-01",
                "source_id": source_id,
            },
        )
    for code, cost, coverage in (
        ("MAT-PT-PRIMER", "30.00", "300"),
        ("MAT-PT-FINISH", "40.00", "350"),
    ):
        _post_checked(
            client,
            f"{base}/material-rates",
            {
                "material_code": code,
                "description": f"{code} FIXTURE ONLY",
                "trade_code": "painting",
                "purchase_unit": "GAL",
                "unit_cost": cost,
                "coverage_per_unit": coverage,
                "coverage_unit": "SF",
                "effective_date": "2026-01-01",
                "source_id": source_id,
            },
        )
    _post_checked(
        client,
        f"{base}/other-direct-costs",
        {
            "odc_code": "ODC-MASKING",
            "cost_type": "masking",
            "unit": "SF",
            "unit_rate": "0.10",
            "source_id": source_id,
        },
    )

    from app.trades.registry import trade_registry

    for template in trade_registry.get("painting").get_assembly_templates():
        _post_checked(client, f"{base}/assemblies", {**template, "trade_code": "painting"})
    _post_checked(client, f"{base}/publish")
    return version_id


def run_proof(
    pdf_path: Path,
    workdir: Path,
    *,
    enforce_registered_source_hash: bool = True,
) -> dict[str, Any]:
    """Run the proof without leaking its opt-in settings into the caller process."""
    database_path = workdir / "mobi.db"
    if database_path.exists():
        raise ValueError(
            f"Refusing to publish fixture rates into an existing database: {database_path}"
        )

    environment_names = (
        "MOBI_DB_PATH",
        "MOBI_UPLOAD_DIR",
        "MOBI_DEPLOYMENT_ENVIRONMENT",
        "MOBI_ENGINE_AUTH_MODE",
        "MOBI_ENABLED_TRADES",
        "MOBI_EXTRACTION_PROVIDER",
        "MOBI_ENABLE_LIVE_EXTRACTION",
    )
    saved_environment = {name: os.environ.get(name) for name in environment_names}
    settings = None
    saved_settings: dict[str, Any] = {}
    try:
        # The settings module itself fails closed outside an explicitly labelled
        # local harness. Keep both startup-gate mutation and import inside the
        # restoration boundary so even an import/configuration failure is isolated.
        os.environ["MOBI_DEPLOYMENT_ENVIRONMENT"] = "local"
        os.environ["MOBI_ENGINE_AUTH_MODE"] = "local_dev_open"

        from app.config import settings as runtime_settings

        settings = runtime_settings
        setting_names = (
            "db_path",
            "upload_dir",
            "deployment_environment",
            "engine_auth_mode",
            "enabled_trades",
            "extraction_provider",
            "enable_live_extraction",
            "extraction_cache_enabled",
        )
        saved_settings = {name: getattr(settings, name) for name in setting_names}
        return _run_proof_impl(
            pdf_path,
            workdir,
            enforce_registered_source_hash=enforce_registered_source_hash,
        )
    finally:
        if settings is not None:
            for name, value in saved_settings.items():
                setattr(settings, name, value)
        for name, value in saved_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value



def _run_proof_impl(
    pdf_path: Path,
    workdir: Path,
    *,
    enforce_registered_source_hash: bool = True,
) -> dict[str, Any]:
    _configure(workdir)

    from fastapi.testclient import TestClient

    from app.config import settings
    from app.database import init_db
    from app.main import app

    settings.db_path = workdir / "mobi.db"
    settings.upload_dir = workdir / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.deployment_environment = "local"
    settings.engine_auth_mode = "local_dev_open"
    settings.enabled_trades = ["painting", "demo_concrete", "general_trade"]
    settings.extraction_provider = "source_text"
    settings.enable_live_extraction = False
    settings.extraction_cache_enabled = False
    init_db()

    actual_sha256 = _sha256(pdf_path)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_pdf": str(pdf_path.resolve()),
        "workdir": str(workdir.resolve()),
        "classification": "internal_public_fixture_proof",
        "pricing_data_class": "fictional_fixture_only_not_market_pricing",
        "source": {
            "url": SOURCE_URL,
            "sha256": actual_sha256,
            "registered_sha256": EXPECTED_PDF_SHA256,
            "registry_match": actual_sha256 == EXPECTED_PDF_SHA256,
            "internal_testing_only": True,
        },
        "safety": {
            "customer_delivery_ready": False,
            "customer_message_ready": False,
            "send_ready": False,
            "final_estimate_approved": False,
            "external_messages": False,
            "payments": False,
            "proposal_created": False,
            "proposal_issued": False,
            "estimate_version_created": False,
        },
        "stages": {},
        "failures": [],
        "status": "fail",
    }

    if enforce_registered_source_hash and actual_sha256 != EXPECTED_PDF_SHA256:
        report["failures"].append("public_source_hash_mismatch")
        return report

    with TestClient(app, raise_server_exceptions=False) as client:
        with pdf_path.open("rb") as handle:
            upload_response = client.post(
                "/api/v1/projects/upload",
                data={"project_name": "Ruby Grant Park - Painting Public Proof"},
                files={"plan": (pdf_path.name, handle, "application/pdf")},
                headers=TENANT_HEADERS,
            )
        report["stages"]["upload"] = _payload(upload_response)
        if not report["stages"]["upload"]["ok"]:
            report["failures"].append("upload_failed")
            return report

        project_id = upload_response.json()["project_id"]
        report["project_id"] = project_id
        base = f"/api/v1/projects/{project_id}"

        process_response = client.post(f"{base}/process", headers=TENANT_HEADERS)
        report["stages"]["process"] = _payload(process_response)
        if not report["stages"]["process"]["ok"]:
            report["failures"].append("processing_failed")
            return report

        sheets = _paged_items(client, f"{base}/sheets")
        sheets_by_page = {int(row["pdf_page_number"]): row for row in sheets}
        report["sheet_count"] = len(sheets)
        verified_pages: list[dict[str, Any]] = []
        for page_number, (sheet_number, title) in TARGET_PAGES.items():
            sheet = sheets_by_page.get(page_number)
            if sheet is None:
                report["failures"].append(f"missing_target_page_{page_number}")
                continue
            verification = client.patch(
                f"{base}/sheets/{sheet['sheet_id']}/verification",
                json={
                    "verified_sheet_number": sheet_number,
                    "verified_sheet_title": title,
                    "review_notes": "Public fixture page manually selected for deterministic painting proof",
                    "review_status": "verified",
                },
                headers=TENANT_HEADERS,
            )
            if verification.status_code != 200:
                report["failures"].append(f"verification_failed_page_{page_number}")
                continue
            verified_pages.append(
                {
                    "pdf_page_number": page_number,
                    "sheet_id": sheet["sheet_id"],
                    "verified_sheet_number": sheet_number,
                    "verified_sheet_title": title,
                }
            )
        report["verified_pages"] = verified_pages
        if report["failures"]:
            return report

        eligible_response = client.get(f"{base}/trades/painting/eligible-sheets", headers=TENANT_HEADERS)
        report["stages"]["painting_eligible_sheets"] = _payload(eligible_response)
        extraction_response = client.post(
            f"{base}/trades/painting/extractions",
            json={},
            headers=TENANT_HEADERS,
        )
        report["stages"]["painting_extraction"] = _payload(extraction_response)
        if extraction_response.status_code != 202:
            report["failures"].append("painting_extraction_failed")
            return report

        scope_rows = _paged_items(client, f"{base}/scope-items?trade_code=painting")
        scope_details = []
        for row in scope_rows:
            detail_response = client.get(f"{base}/scope-items/{row['id']}", headers=TENANT_HEADERS)
            detail_response.raise_for_status()
            scope_details.append(detail_response.json())
        report["painting_scope_items"] = scope_details

        candidates = [
            detail
            for detail in scope_details
            if (detail.get("scope_item") or {}).get("description", "").startswith("Apply a minimum 100 SF")
        ]
        if len(candidates) != 1:
            report["failures"].append("expected_one_source_backed_mockup_candidate")
            return report
        candidate = candidates[0]
        scope_item = candidate["scope_item"]
        evidence = candidate.get("evidence") or []
        if scope_item.get("quantity") != "100" or scope_item.get("unit") != "SF":
            report["failures"].append("source_quantity_mismatch")
        if len(evidence) != 2 or not all(row.get("extracted_text_quote") for row in evidence):
            report["failures"].append("source_evidence_incomplete")
        # Provider/model candidates intentionally retain this flag until the
        # explicit scope-review action below; verified sheet identity alone must
        # never masquerade as human-reviewed scope.
        if not all(bool(row.get("requires_human_verification")) for row in evidence):
            report["failures"].append("model_candidate_review_flag_missing")
        if report["failures"]:
            return report

        approval_response = client.post(
            f"{base}/scope-items/{scope_item['id']}/approve",
            json={
                "reviewer_id": "painting-public-proof-reviewer",
                "reviewer_notes": "Verified only the explicit 100-SF mockup sub-scope; no total project quantity inferred",
            },
            headers=TENANT_HEADERS,
        )
        report["stages"]["scope_review"] = _payload(approval_response)
        if approval_response.status_code != 200:
            report["failures"].append("scope_review_failed")
            return report

        cost_book_version_id = _seed_fixture_painting_cost_book(client)
        report["fixture_cost_book_version_id"] = cost_book_version_id
        mapping_response = client.post(
            f"{base}/scope-items/{scope_item['id']}/assembly-mapping",
            json={
                "assembly_code": "PT-INT-WALL",
                "reviewer_id": "painting-public-proof-reviewer",
                "notes": "Explicit mapping for the verified Section 099000 gypsum-board mockup scope only",
            },
            headers=TENANT_HEADERS,
        )
        report["stages"]["assembly_mapping"] = _payload(mapping_response)
        if mapping_response.status_code != 200:
            report["failures"].append("assembly_mapping_failed")
            return report
        preview_response = client.post(
            f"{base}/pricing/preview",
            json={
                "cost_book_version_id": cost_book_version_id,
                "trade_code": "painting",
                "scope_item_ids": [scope_item["id"]],
            },
            headers=TENANT_HEADERS,
        )
        report["stages"]["internal_pricing_preview"] = _payload(preview_response)
        if preview_response.status_code != 200:
            report["failures"].append("internal_pricing_preview_failed")
            return report

        preview = preview_response.json()
        report["internal_preview_summary"] = {
            "estimate_version_created": preview.get("estimate_version_created"),
            "estimated_api_cost": preview.get("estimated_api_cost"),
            "scope_items_considered_count": len(preview.get("scope_items_considered") or []),
            "proposed_mapping_count": len(preview.get("proposed_mappings") or []),
            "missing_mapping_count": len(preview.get("missing_mappings") or []),
            "blocking_exception_count": len(preview.get("blocking_exceptions") or []),
        }
        from app.proposals.draft_preview import _line_to_preview

        safe_line, quantity_abstained, unsupported_scope = _line_to_preview(
            {
                "scope_item_id": scope_item["id"],
                "trade_code": scope_item["trade_code"],
                "category_code": scope_item["category_code"],
                "description": scope_item["description"],
                "location": scope_item["location"],
                "quantity": scope_item["quantity"],
                "unit": scope_item["unit"],
                "quantity_source": (
                    f"sha256:{report['source']['sha256']}#page=258#section=099000-1.4.A.1.a"
                ),
            },
            supported_scope=False,
        )
        report["customer_safe_preview"] = {
            "status": "internal_preview_only",
            "line_items": [safe_line],
            "summary": {
                "scope_line_count": 1,
                "quantity_abstained_count": 1 if quantity_abstained else 0,
                "unsupported_scope_count": 1 if unsupported_scope else 0,
                "customer_delivery_ready": False,
                "final_estimate_approved": False,
                "external_messages": False,
                "payments": False,
            },
            "safety_flags": {**report["safety"], "preview_only": True},
        }
        estimates = client.get(f"{base}/estimates", headers=TENANT_HEADERS)
        report["stages"]["estimate_version_absence_check"] = _payload(estimates)
        estimate_rows = estimates.json().get("items") if estimates.status_code == 200 else None
        proposals = client.get(f"{base}/proposals", headers=TENANT_HEADERS)
        report["stages"]["proposal_absence_check"] = _payload(proposals)
        proposal_rows = proposals.json().get("items") if proposals.status_code == 200 else None
        report["persistence_absence"] = {
            "estimates_verified_empty": estimate_rows == [],
            "proposals_verified_empty": proposal_rows == [],
        }
        if preview.get("estimate_version_created") is not False:
            report["failures"].append("preview_created_estimate_version")
        if len(preview.get("scope_items_considered") or []) != 1:
            report["failures"].append("preview_did_not_consider_source_scope")
        if len(preview.get("proposed_mappings") or []) != 1:
            report["failures"].append("preview_did_not_map_source_scope")
        if preview.get("blocking_exceptions"):
            report["failures"].append("preview_has_blocking_pricing_exceptions")
        if not quantity_abstained or safe_line.get("quantity") or safe_line.get("unit"):
            report["failures"].append("customer_safe_preview_exposed_unsupported_quantity")
        if estimate_rows != []:
            report["failures"].append("persistent_estimate_created")
        if proposal_rows != []:
            report["failures"].append("persistent_proposal_created")

    report["status"] = "pass" if not report["failures"] else "fail"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--workdir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if not args.pdf.is_file():
        raise SystemExit(f"Public fixture PDF not found: {args.pdf}")
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="mobi-painting-public-proof-"))
    report = run_proof(args.pdf, workdir)
    output = args.output or (workdir / "painting_public_pdf_proof_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report.get("status", "fail"),
                "failures": report.get("failures", []),
                "output": str(output.resolve()),
                "project_id": report.get("project_id"),
                "sheet_count": report.get("sheet_count"),
                "internal_preview_summary": report.get("internal_preview_summary"),
                "safety": report.get("safety"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
