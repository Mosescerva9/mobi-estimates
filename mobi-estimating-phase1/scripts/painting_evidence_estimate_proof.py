#!/usr/bin/env python3
"""Deterministic internal-only painting evidence-to-estimate proof.

The proof reads two source pages from the public Ruby Grant Park project manual,
uses the conservative source-text painting extractor, validates the existing
painting assembly mapping, and exercises the generic bridge/preview safety
contracts without creating a proposal, approving an estimate, sending a message,
or exposing a fictional price.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import fitz

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

# Importing the generic bridge loads the engine settings. This proof is an
# explicitly local, read-only harness and must never inherit release semantics.
os.environ.setdefault("MOBI_DEPLOYMENT_ENVIRONMENT", "local")
os.environ.setdefault("MOBI_ENGINE_AUTH_MODE", "local_dev_open")

from app.capability_registry import is_test_only_source  # noqa: E402
from app.extraction.provider_schemas import (  # noqa: E402
    ProviderSheetInput,
    ScopeExtractionRequest,
)
from app.extraction.source_text_provider import SourceTextExtractionProvider  # noqa: E402
from app.generic_estimate_bridge import _missing_blockers  # noqa: E402
from app.proposals.draft_preview import _line_to_preview  # noqa: E402
from app.trades.painting.definition import PaintingTradeModule  # noqa: E402

DEFAULT_FIXTURE = (
    ENGINE_ROOT
    / "data"
    / "golden_set"
    / "documents"
    / "norman_ruby_grant_park_specs_amendment_one.pdf"
)
EXPECTED_SHA256 = "41fa4d685c8b5ccc66b14ff15815846e9823fd0faa8d4068e43da767393cd993"
SOURCE_URL = (
    "https://www.normanok.gov/sites/default/files/documents/2020-12/"
    "ruby_grant_park_-_specs_-_amendment_one.pdf"
)
SOURCE_PAGES = (
    (258, "099000-1"),
    (259, "099000-2"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_sheets(pdf: Path) -> list[ProviderSheetInput]:
    document = fitz.open(pdf)
    try:
        return [
            ProviderSheetInput(
                sheet_id=uuid5(NAMESPACE_URL, f"{EXPECTED_SHA256}#page={page_number}"),
                pdf_page_number=page_number,
                verified_sheet_number=sheet_number,
                verified_sheet_title="PAINTING",
                embedded_text=str(document[page_number - 1].get_text("text")),
            )
            for page_number, sheet_number in SOURCE_PAGES
        ]
    finally:
        document.close()


def build_proof(pdf: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    pdf = pdf.resolve()
    actual_sha256 = _sha256(pdf)
    if actual_sha256 != EXPECTED_SHA256:
        raise ValueError(
            "Ruby Grant Park fixture SHA-256 mismatch: "
            f"expected {EXPECTED_SHA256}, got {actual_sha256}."
        )

    module = PaintingTradeModule()
    provider = SourceTextExtractionProvider()
    response = provider.extract_scope(
        ScopeExtractionRequest(
            trade_code="painting",
            prompt_version=module.get_prompt_version("scope_extractor"),
            allowed_categories=module.get_scope_categories(),
            allowed_units=[unit.value for unit in module.get_allowed_units()],
            sheets=_source_sheets(pdf),
        )
    )
    candidates = response.get("candidates") or []
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one supported painting candidate, got {len(candidates)}.")

    candidate = candidates[0]
    quantity = candidate["quantity"]
    trade_data = module.validate_trade_data(candidate["trade_data"])
    assembly_codes = module.map_scope_to_assembly(candidate["category_code"], trade_data)
    if assembly_codes != ["PT-INT-WALL"]:
        raise ValueError(f"Unexpected painting assembly mapping: {assembly_codes!r}.")
    assembly = next(
        row for row in module.get_assembly_templates()
        if row["assembly_code"] == assembly_codes[0]
    )
    pricing_input_errors = module.validate_pricing_inputs(
        category_code=candidate["category_code"],
        trade_data=trade_data,
        assembly=assembly,
    )

    quantity_source = f"sha256:{actual_sha256}#page=258#section=099000-1.4.A.1.a"
    generic_item = {
        "id": "ruby-grant-painting-mockup",
        "trade_code": "painting",
        "category_code": candidate["category_code"],
        "description": candidate["description"],
        "location": candidate["location"],
        "quantity": quantity["value"],
        "unit": quantity["unit"],
        "quantity_basis": quantity["basis"],
        "raw_quantity_inputs": {
            "verified_quantity_input_v1": {
                "quantity": quantity["value"],
                "unit": quantity["unit"],
                "quantity_basis": quantity["basis"],
                "source": quantity_source,
                "source_url": SOURCE_URL,
                "pdf_page_number": 258,
                "verified_sheet_number": "099000-1",
                "scope_limit": "mockup_only_not_total_project_painting",
            }
        },
        "trade_data": {
            **trade_data,
            "pricing_method": "unit_rate_needed",
            "pricing_ready": False,
        },
        "blocking_issues": [
            {
                "code": "missing_unit_rate",
                "message": "No approved cost-book rate is supplied by the public specification.",
            }
        ],
    }
    bridge_blockers = _missing_blockers(generic_item)

    preview_line, quantity_abstained, unsupported_scope = _line_to_preview(
        {
            "scope_item_id": generic_item["id"],
            "trade_code": generic_item["trade_code"],
            "category_code": generic_item["category_code"],
            "description": generic_item["description"],
            "location": generic_item["location"],
            "quantity": generic_item["quantity"],
            "unit": generic_item["unit"],
            "quantity_source": quantity_source,
        },
        supported_scope=False,
    )
    # ``_line_to_preview`` normally resolves this through the process-wide trade
    # registry, whose bootstrap state differs between direct CLI and pytest runs.
    # The proof already owns the validated module, so make the output deterministic.
    preview_line["section"] = module.trade_name

    evidence = [
        {
            **row,
            "source_artifact_ref": f"sha256:{actual_sha256}",
            "source_url": SOURCE_URL,
        }
        for row in candidate["evidence"]
    ]
    safety_flags = {
        "preview_only": True,
        "customer_delivery_ready": False,
        "customer_message_ready": False,
        "send_ready": False,
        "final_estimate_approved": False,
        "external_messages": False,
        "payments": False,
        "proposal_created": False,
        "proposal_issued": False,
    }
    blocker_codes = sorted({row["code"] for row in bridge_blockers})
    checks = {
        "fixture_hash_verified": actual_sha256 == EXPECTED_SHA256,
        "source_evidence_complete": len(evidence) == 2
        and all(row.get("extracted_text_quote") for row in evidence),
        "quantity_is_source_backed": not is_test_only_source(quantity_source)
        and quantity["value"] == "100"
        and quantity["unit"] == "SF",
        "quantity_is_mockup_only": candidate["assumptions"] == [
            "This candidate covers only the explicitly specified mockup, not total project painting quantity."
        ],
        "painting_pricing_structure_valid": not pricing_input_errors
        and assembly_codes == ["PT-INT-WALL"],
        "monetary_pricing_fail_closed": "missing_unit_rate" in blocker_codes,
        "unsupported_delivery_fail_closed": "unsupported_customer_delivery_scope" in blocker_codes,
        "preview_quantity_abstained": quantity_abstained
        and preview_line["quantity"] == ""
        and preview_line["unit"] == "",
        "all_delivery_actions_locked": all(
            value is False for key, value in safety_flags.items() if key != "preview_only"
        ),
    }

    return {
        "proof_version": "painting_evidence_estimate_proof_v1",
        "status": "passed" if all(checks.values()) else "failed",
        "source": {
            "title": "Ruby Grant Park - Sealed Bid Specifications and Contract Documents, Amendment One",
            "agency": "City of Norman Parks & Recreation Department",
            "url": SOURCE_URL,
            "sha256": actual_sha256,
            "internal_testing_only": True,
            "pages_used": [page for page, _sheet in SOURCE_PAGES],
        },
        "scope": {
            "trade_code": "painting",
            "category_code": candidate["category_code"],
            "description": candidate["description"],
            "location": candidate["location"],
            "assumptions": candidate["assumptions"],
            "exclusions": candidate["exclusions"],
        },
        "evidence": evidence,
        "quantity_input": generic_item["raw_quantity_inputs"]["verified_quantity_input_v1"],
        "pricing_inputs": {
            "assembly_code": assembly_codes[0],
            "assembly_name": assembly["name"],
            "input_unit": assembly["input_unit"],
            "coating_system": trade_data["coating_system"],
            "finish_coats": trade_data["finish_coats"],
            "structure_validation_errors": pricing_input_errors,
            "approved_monetary_rate_present": False,
            "monetary_pricing_ready": False,
        },
        "generic_estimate_bridge": {
            "line_created": False,
            "blocker_codes": blocker_codes,
            "blocked_before_persistence": True,
        },
        "customer_safe_preview": {
            "status": "internal_preview_only",
            "line_items": [preview_line],
            "summary": {
                "scope_line_count": 1,
                "quantity_abstained_count": 1 if quantity_abstained else 0,
                "unsupported_scope_count": 1 if unsupported_scope else 0,
                "customer_delivery_ready": False,
                "final_estimate_approved": False,
                "external_messages": False,
                "payments": False,
            },
            "safety_flags": safety_flags,
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = build_proof(args.pdf)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        return 1

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
