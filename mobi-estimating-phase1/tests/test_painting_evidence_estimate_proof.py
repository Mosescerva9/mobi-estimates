"""Real public-PDF painting evidence-to-internal-estimate proof tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.capability_registry import is_test_only_source
from scripts.painting_evidence_estimate_proof import (
    DEFAULT_FIXTURE,
    EXPECTED_SHA256,
    build_proof,
)


def test_real_painting_proof_is_deterministic_traceable_and_fail_closed():
    first = build_proof()
    second = build_proof()

    assert first == second
    assert first["status"] == "passed"
    assert first["source"]["sha256"] == EXPECTED_SHA256
    assert first["source"]["pages_used"] == [258, 259]
    assert first["source"]["internal_testing_only"] is True

    assert len(first["evidence"]) == 2
    assert all(row["source_artifact_ref"] == f"sha256:{EXPECTED_SHA256}" for row in first["evidence"])
    assert "100 sq. ft." in first["evidence"][0]["extracted_text_quote"]
    assert "Aquapon Epoxy" in first["evidence"][1]["extracted_text_quote"]

    quantity = first["quantity_input"]
    assert quantity["quantity"] == "100"
    assert quantity["unit"] == "SF"
    assert quantity["quantity_basis"] == "explicit_plan_quantity"
    assert quantity["scope_limit"] == "mockup_only_not_total_project_painting"
    assert is_test_only_source(quantity["source"]) is False

    pricing = first["pricing_inputs"]
    assert pricing["assembly_code"] == "PT-INT-WALL"
    assert pricing["finish_coats"] == 3
    assert pricing["structure_validation_errors"] == []
    assert pricing["approved_monetary_rate_present"] is False
    assert pricing["monetary_pricing_ready"] is False

    bridge = first["generic_estimate_bridge"]
    assert bridge["line_created"] is False
    assert bridge["blocked_before_persistence"] is True
    assert "missing_unit_rate" in bridge["blocker_codes"]
    assert "unsupported_customer_delivery_scope" in bridge["blocker_codes"]

    preview = first["customer_safe_preview"]
    assert preview["status"] == "internal_preview_only"
    assert preview["line_items"][0]["quantity"] == ""
    assert preview["line_items"][0]["unit"] == ""
    assert preview["summary"]["quantity_abstained_count"] == 1
    assert preview["summary"]["unsupported_scope_count"] == 1
    assert preview["safety_flags"]["preview_only"] is True
    assert all(
        value is False
        for key, value in preview["safety_flags"].items()
        if key != "preview_only"
    )
    assert all(first["checks"].values())


def test_painting_proof_cli_writes_same_machine_readable_report(tmp_path: Path):
    output = tmp_path / "painting-proof.json"
    command = [
        sys.executable,
        "scripts/painting_evidence_estimate_proof.py",
        "--pdf",
        str(DEFAULT_FIXTURE),
        "--output",
        str(output),
    ]

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(completed.stdout)
    assert written == printed == build_proof()
