"""Tests for the Mobi AutoResearch v1 helper script."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import mobi_autoresearch as ar


def _report(**aggregate_overrides):
    aggregate = {
        "scope_keyword_coverage_micro": 0.25,
        "trade_recall_micro": 0.5,
        "key_quantity_pass_count": 2,
        "key_quantity_evidence_pass_count": 3,
        "key_quantity_total": 4,
        "trade_unexpected_false_positive_total": 1,
        "safety_violation_count": 0,
        "harness_failed_count": 0,
        "evaluation_passed_count": 1,
        "evaluated_count": 3,
        "accuracy_failed_project_count": 2,
    }
    aggregate.update(aggregate_overrides)
    return {"aggregate": aggregate}


def _release_gate_report(**aggregate_overrides):
    aggregate = {
        "project_count": 1,
        "evaluated_count": 1,
        "evaluation_passed_count": 1,
        "skipped_count": 0,
        "harness_failed_count": 0,
        "safety_violation_count": 0,
        "benchmark_eligible_count": 1,
        "benchmark_ineligible_count": 0,
        "evaluated_benchmark_eligible_count": 1,
        "evaluated_benchmark_ineligible_count": 0,
        "accuracy_failed_project_count": 0,
        "missed_required_trade_project_count": 0,
        "trade_unexpected_false_positive_total": 0,
        "evaluated_benchmark_eligible_key_quantity_total": 1,
        "evaluated_benchmark_eligible_key_quantity_pass_count": 1,
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_pass_count": 1,
        "evaluated_benchmark_eligible_document_text_extraction_fail_count": 0,
        "scope_keyword_coverage_micro": 0.9,
        "trade_recall_micro": 1.0,
        "key_quantity_pass_count": 1,
        "key_quantity_evidence_pass_count": 1,
        "key_quantity_total": 1,
    }
    aggregate.update(aggregate_overrides)
    return {
        "run_mode": {
            "release_gate": True,
            "fail_on_accuracy": True,
            "report_only_baseline": False,
            "allow_missing_documents": False,
        },
        "aggregate": aggregate,
    }


def test_validate_release_gate_report_accepts_strict_valid_counts():
    result = ar.validate_release_gate_report(_release_gate_report())

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


def test_validate_release_gate_report_accepts_strict_evaluator_internal_labels():
    """Strict release-gate benchmark reports are internal evidence, not customer-delivery evidence."""
    report = _release_gate_report()
    report["internal_testing_only"] = True
    report["manifest_metadata"] = {"internal_testing_only": True, "source_authorization": "public"}

    result = ar.validate_release_gate_report(report)

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


@pytest.mark.parametrize("run_mode", [None, "release-gate", []])
def test_validate_release_gate_report_rejects_missing_or_malformed_run_mode(run_mode):
    report = _release_gate_report()
    if run_mode is None:
        report.pop("run_mode")
    else:
        report["run_mode"] = run_mode

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report does not prove it came from a strict release-gate run",
    }


@pytest.mark.parametrize(
    ("run_mode_override", "reason"),
    [
        ({"release_gate": False}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"release_gate": "true"}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"release_gate": 1}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"fail_on_accuracy": False}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"fail_on_accuracy": "true"}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"fail_on_accuracy": 1}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"report_only_baseline": True}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"report_only_baseline": "false"}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"report_only_baseline": 0}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"allow_missing_documents": True}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"allow_missing_documents": "false"}, "release gate report was produced with accuracy-bypass or report-only flags"),
        ({"allow_missing_documents": 0}, "release gate report was produced with accuracy-bypass or report-only flags"),
    ],
)
def test_validate_release_gate_report_rejects_non_strict_run_mode(run_mode_override, reason):
    report = _release_gate_report()
    report["run_mode"] = {**report["run_mode"], **run_mode_override}

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": reason,
    }


@pytest.mark.parametrize(
    "alias_payload",
    [
        {"metadata": {"commandFlags": {"failOnAccuracy": False}}},
        {"metadata": {"commandFlags": {"releaseGate": False}}},
        {"metadata": {"commandFlags": {"fail-on-accuracy": "false"}}},
        {"projects": [{"runMode": {"releaseGate": "0"}}]},
        {"metadata": {"command": ["python", "eval.py", "--failOnAccuracy=false"]}},
        {"metadata": {"command": ["python", "eval.py", "--releaseGate=false"]}},
        {"metadata": {"command": ["python", "eval.py", "--failOnAccuracy", "false"]}},
        {"metadata": {"command": ["python", "eval.py", "--releaseGate", "false"]}},
        {"metadata": {"commandFlags": {"--failOnAccuracy=false": True}}},
        {"metadata": {"commandFlags": {"--releaseGate=false": True}}},
        {"logs": "wrapper used failOnAccuracy=false"},
        {"logs": "wrapper used releaseGate=false"},
    ],
)
def test_validate_release_gate_report_rejects_contradictory_strict_mode_aliases(alias_payload):
    report = _release_gate_report()
    report.update(alias_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report was produced with accuracy-bypass or report-only flags",
    }


@pytest.mark.parametrize(
    "marker_payload",
    [
        {"metadata": {"is_internal_testing_only": True}},
        {"projects": [{"internal_testing_only": True}]},
        {"metadata": {"report_only_baseline": True}},
        {"metadata": {"command_flags": {"no_fail_on_accuracy": True}}},
        {"metadata": {"command_flags": {"no-fail-on-accuracy": True}}},
        {"metadata": {"command_flags": {"--no-fail-on-accuracy": True}}},
        {"metadata": {"command_flags": {"report-only-baseline": True}}},
        {"metadata": {"command_flags": {"--report-only-baseline": True}}},
        {"metadata": {"commandFlags": {"noFailOnAccuracy": True}}},
        {"metadata": {"commandFlags": {"accuracyBypassEnabled": True}}},
        {"metadata": {"commandFlags": {"allowAccuracyFailure": True}}},
        {"metadata": {"commandFlags": {"accuracyFailuresAllowed": True}}},
        {"metadata": {"accuracyFailureAllowance": "yes"}},
        {"metadata": {"commandFlags": {"reportOnlyBaseline": True}}},
        {"projects": [{"internalTestingOnly": True}]},
        {"projects": [{"accuracy_bypass_enabled": "true"}]},
        {"metadata": {"command": ["python", "golden_set_extraction_eval.py", "--no-fail-on-accuracy"]}},
        {"metadata": {"command": ["python", "golden_set_extraction_eval.py", "--allow-missing-documents"]}},
        {"logs": "baseline run used --report-only-baseline for internal comparison"},
        {"logs": "baseline run used no fail on accuracy for internal comparison"},
        {"logs": "release candidate allowed missing documents during evaluation"},
        {"logs": "run used accuracy-bypass"},
        {"logs": "run used accuracy bypass"},
        {"logs": "run used missing-document allowance"},
        {"logs": "run used missing documents allowance"},
        {"logs": "missing documents allowed"},
    ],
)
def test_validate_release_gate_report_rejects_test_only_or_accuracy_bypass_markers(marker_payload):
    report = _release_gate_report()
    report.update(marker_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report is marked test-only or accuracy-bypass evidence",
    }


@pytest.mark.parametrize(
    "unsupported_payload",
    [
        {"projects": [{"unsupported_scope": True}]},
        {"projects": [{"unsupportedscope": True}]},
        {"projects": [{"unsupportedScope": "yes"}]},
        {"projects": [{"notSupported": True}]},
        {"projects": [{"containsUnsupportedScope": True}]},
        {"projects": [{"containsunsupportedscope": True}]},
        {"projects": [{"unsupportedScope": {"detected": True}}]},
        {"projects": [{"unsupported_scope": {}}]},
        {"projects": [{"containsUnsupportedScope": []}]},
        {"projects": [{"scope_status": "out_of_supported_scope"}]},
        {"projects": [{"status": "unsupported"}]},
        {"projects": [{"projectStatus": "abstain"}]},
        {"projects": [{"scope": {"status": "unsupported"}}]},
        {"projects": [{"scope": {"decision": "unsupported"}}]},
        {"projects": [{"scope": {"decision": "abstain"}}]},
        {"projects": [{"scope": {"evidence": "scope is unsupported"}}]},
        {"projects": [{"scopeClassification": "abstain"}]},
        {"projects": [{"supported_scope": False}]},
        {"projects": [{"supportedCustomerDeliveryScope": False}]},
        {"metadata": {"requirements": {"supported_customer_delivery_scope": False}}},
        {"projects": [{"supportedScope": "false"}]},
        {"projects": [{"unsupported_scope_item_count": 1}]},
        {"projects": [{"unsupportedScopeItemsCount": "2"}]},
        {"projects": [{"unsupported_scope_items": [{"scope_item_id": "s1"}]}]},
        {"projects": [{"unsupported_scope_items": {"scope_item_id": "s1"}}]},
        {"projects": [{"unsupportedScopeItems": {"scope_item_id": "s1"}}]},
        {"projects": [{"unsupportedCustomerDeliveryScope": {"unsupported_scope_items": {"scope_item_id": "s1"}}}]},
        {"projects": [{"unsupportedCustomerDeliveryScope": {"unsupported_scope_item_count": 1}}]},
        {"aggregate": {**_release_gate_report()["aggregate"], "unsupported_scope_count": 1}},
        {"metadata": {"releaseScopeStatus": "unsupported_scope"}},
        {"metadata": {"shouldAbstain": True}},
        {"logs": "release wrapper saw supportedScope=false for project p1"},
        {"logs": "release wrapper saw scopeStatus=unsupported for project p1"},
        {"logs": "project p1 scope not supported"},
        {"logs": "project p1 abstained"},
        {"logs": "unsupported scope found for project p1"},
    ],
)
def test_validate_release_gate_report_rejects_unsupported_scope_markers(unsupported_payload):
    report = _release_gate_report()
    report.update(unsupported_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report contains unsupported-scope or abstention evidence",
    }


def test_validate_release_gate_report_allows_explicit_supported_scope_markers():
    report = _release_gate_report()
    report["projects"] = [
        {
            "supported_scope": True,
            "scope_status": "supported",
            "unsupported_scope": False,
            "unsupported_scope_item_count": 0,
            "unsupported_scope_items": [],
            "abstention": False,
        },
        {
            "scope_summary": {
                "evaluated_scope_item_count": 1,
                "malformed_scope_collection_count": 0,
                "supported_scope_item_count": 1,
                "unsupported_scope_item_count": 0,
                "supported_scope": True,
                "supported_customer_delivery_scope": True,
                "customer_delivery_scope_supported": True,
                "supportedCustomerDeliveryScope": True,
                "supported_scope_items": [
                    {"scope_item_id": "s1", "trade_code": "painting", "category_code": "generic_scope"}
                ],
                "unsupported_scope_items": [],
            }
        },
    ]

    result = ar.validate_release_gate_report(report)

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


@pytest.mark.parametrize(
    "delivery_payload",
    [
        {"customer_delivery_ready": True},
        {"final_delivery_ready": True},
        {"finalEstimateReady": "yes"},
        {"projects": [{"customer_delivery_ready": True}]},
        {"projects": [{"delivery_status": "ready_for_customer_delivery"}]},
        {"projects": [{"estimate_status": "final_estimate_delivered"}]},
        {"metadata": {"proposal_export": {"ready_for_customer": True}}},
        {"metadata": {"delivery": {"customerFacing": True}}},
        {"metadata": {"customer_facing_delivery": True}},
        {"metadata": {"customerEstimateExported": True}},
        {"metadata": {"delivery_status": "customer_facing"}},
        {"customer_delivery_lock": {"delivery_unlocked": True}},
        {"customer_delivery_lock": {"deliveryUnlocked": True}},
        {"final_customer_delivery_enabled": True},
        {"customer_delivery": True},
        {"final_estimate_approval": True},
        {"final_estimate_approved": True},
        {"aggregate": {"customer_delivery_ready_count": 1}},
        {"summary": {"outputs": {"customer_delivery_ready_count": 1}}},
        {"generic_estimate_draft_customer_delivery_ready": True},
        {"generic_proposal_preview_final_estimate_approved": True},
        {"customer_delivery_gate": "unlocked"},
        {"customer_delivery_approved": True},
        {"approved_for_customer_delivery": True},
        {"owner_approved_final_delivery": True},
        {"ownerApprovalScope": "final_customer_delivery"},
        {"final_delivery_approval": {"ownerApproved": True, "scope": "final_customer_delivery"}},
        {"delivery_status": "approved_for_customer_delivery"},
        {"final_delivery_status": "final_delivery_approval_recorded"},
        {"logs": "final delivery approval recorded"},
        {"logs": "owner approved final delivery"},
        {"logs": "customer delivery approved"},
        {"logs": "approved for customer delivery"},
        {"logs": "final estimate delivered to customer"},
        {"logs": "final estimate sent to customer"},
        {"logs": "ready for delivery to customer"},
        {"logs": "customer delivered estimate"},
        {"logs": "final estimate is customer facing"},
        {"logs": "customer facing estimate"},
        {"logs": "final customer estimate delivered"},
        {"logs": "final estimate approved"},
        {"logs": "final estimate approval recorded"},
        {"logs": "owner approved final estimate"},
        {"logs": "estimate is not ready for customer delivery; final estimate sent to customer"},
        {"logs": "customer delivery ready without owner approval"},
    ],
)
def test_validate_release_gate_report_rejects_customer_delivery_markers(delivery_payload):
    report = _release_gate_report()
    report.update(delivery_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report contains customer/final delivery exposure markers",
    }


@pytest.mark.parametrize(
    "counter_payload",
    [
        {"aggregate": {"test_only_quantity_count": 1}},
        {"aggregate": {"test_only_count": 1}},
        {"aggregate": {"testOnlyQuantityCount": "2"}},
        {"aggregate": {"test_only_evidence_count": 1}},
        {"aggregate": {"testOnlySourceCount": "1"}},
        {"aggregate": {"testOnlySourcesCount": "1"}},
        {"aggregate": {"testOnlyDeliverySourceCount": "1"}},
        {"aggregate": {"synthetic_fixture_quantity_count": 1}},
        {"aggregate": {"synthetic_quantities_count": 1}},
        {"aggregate": {"syntheticEvidenceCount": 1}},
        {"aggregate": {"syntheticSourcesCount": 1}},
        {"aggregate": {"mockQuantityCount": 1}},
        {"aggregate": {"mock_count": 1}},
        {"aggregate": {"mockEvidenceCount": 1}},
        {"aggregate": {"sample_count": 1}},
        {"aggregate": {"sampleQuantityCount": 1}},
        {"aggregate": {"demo_count": 1}},
        {"aggregate": {"demoSourceCount": 1}},
        {"aggregate": {"placeholder_count": 1}},
        {"aggregate": {"placeholderEvidenceCount": 1}},
        {"aggregate": {"fixture_count": 1}},
        {"aggregate": {"synthetic_count": 1}},
        {"aggregate": {"fixtureSourcesCount": 1}},
        {"aggregate": {"fixtureQuantitiesCount": 1}},
        {"aggregate": {"syntheticFixtureSourceCount": 1}},
        {"metadata": {"testOnlyEvidence": True}},
        {"metadata": {"syntheticEvidence": True}},
        {"metadata": {"mockEvidence": True}},
        {"metadata": {"sampleQuantity": True}},
        {"metadata": {"demoSource": "present"}},
        {"metadata": {"placeholderEvidence": "present"}},
        {"metadata": {"fixtureSource": "present"}},
        {"metadata": {"fixtureQuantity": True}},
        {"metadata": {"testOnlyQuantity": True}},
        {"metadata": {"testOnlyQuantities": True}},
        {"metadata": {"syntheticQuantity": True}},
        {"metadata": {"syntheticQuantities": True}},
        {"metadata": {"syntheticFixtureSource": True}},
        {"results": [{"evidence": [{"source": "synthetic_fixture_quantity"}]}]},
        {"results": [{"evidence": [{"source": "mock_quantity_row"}]}]},
        {"results": [{"evidence": [{"quantity_source": "sample_takeoff"}]}]},
        {"results": [{"evidence": [{"evidence_source": "demo_plan_fixture"}]}]},
        {"results": [{"evidence": [{"source": "placeholder_quantity"}]}]},
        {"metadata": {"sources": ["mock_quantity_row"]}},
        {"metadata": {"evidence_sources": ["sample_takeoff"]}},
        {"metadata": {"quantity_sources": ["demo_plan_fixture"]}},
        {"results": [{"evidence": ["placeholder_quantity"]}]},
        {"projects": [{"contains_test_only_quantities": True}]},
        {"projects": [{"containsTestOnlyEvidence": True}]},
        {"projects": [{"containsMockQuantities": True}]},
        {"projects": [{"hasSampleEvidence": True}]},
        {"projects": [{"containsDemoSource": True}]},
        {"projects": [{"hasPlaceholderQuantities": True}]},
        {"projects": [{"containsTestOnlyQuantity": True}]},
        {"projects": [{"containsTestOnlySource": True}]},
        {"projects": [{"containsSyntheticQuantity": True}]},
        {"projects": [{"containsSyntheticSource": True}]},
        {"metadata": {"containsFixtureSource": True}},
        {"metadata": {"containsSyntheticFixtureSource": True}},
        {"metadata": {"containsSyntheticFixtureQuantities": "yes"}},
        {"metadata": {"hasFixtureEvidence": "yes"}},
        {"metadata": {"hasTestOnlySource": "yes"}},
        {"metadata": {"hasTestOnlySources": "yes"}},
        {"metadata": {"hasTestOnlyQuantity": "yes"}},
        {"metadata": {"hasSyntheticQuantities": "yes"}},
        {"metadata": {"hasSyntheticEvidence": "yes"}},
        {"metadata": {"hasSyntheticSource": "yes"}},
        {"metadata": {"hasSyntheticSources": "yes"}},
        {"metadata": {"datasetProfile": "mock"}},
        {"metadata": {"benchmarkCorpusProfile": "synthetic_fixture"}},
        {"metadata": {"reportProfile": "demo"}},
        {"metadata": {"evidenceSetProfile": "placeholder"}},
        {"metadata": {"quantitySources": ["dummy_takeoff"]}},
        {"metadata": {"evidenceSources": ["fake_measurement"]}},
        {"metadata": {"sourceSetProfile": "stub"}},
        {"metadata": {"quantitySetProfile": "toy"}},
        {"aggregate": {"llm_quantity_count": 1}},
        {"aggregate": {"modelQuantityCount": 1}},
        {"aggregate": {"gptQuantitiesCount": 1}},
        {"aggregate": {"modelGeneratedQuantitiesCount": "2"}},
        {"aggregate": {"modelGeneratedEvidenceCount": 1}},
        {"aggregate": {"aiGeneratedEvidenceCount": 1}},
        {"aggregate": {"llmEvidenceCount": 1}},
        {"aggregate": {"gptSourceCount": 1}},
        {"aggregate": {"machineGeneratedQuantityCount": 1}},
        {"aggregate": {"automatedQuantitiesCount": 1}},
        {"aggregate": {"automatedGeneratedQuantityCount": 1}},
        {"aggregate": {"automatedGeneratedQuantitiesCount": 1}},
        {"aggregate": {"autogeneratedQuantityCount": 1}},
        {"aggregate": {"computerGeneratedQuantityCount": 1}},
        {"aggregate": {"computerGeneratedQuantitiesCount": 1}},
        {"projects": [{"containsLlmQuantities": True}]},
        {"projects": [{"containsModelQuantity": True}]},
        {"projects": [{"containsModelQuantities": True}]},
        {"projects": [{"hasModelQuantity": True}]},
        {"projects": [{"hasModelQuantities": True}]},
        {"metadata": {"modelGeneratedEvidence": True}},
        {"metadata": {"containsModelGeneratedEvidence": True}},
        {"metadata": {"containsModelGeneratedSource": True}},
        {"metadata": {"aiGeneratedEvidence": True}},
        {"metadata": {"containsAiGeneratedEvidence": True}},
        {"metadata": {"containsAiGeneratedSource": True}},
        {"metadata": {"llmEvidence": True}},
        {"metadata": {"containsLlmEvidence": True}},
        {"metadata": {"containsGptSource": True}},
        {"metadata": {"hasGptSource": "yes"}},
        {"metadata": {"containsModelQuantity": "yes"}},
        {"metadata": {"hasModelQuantities": "yes"}},
        {"projects": [{"containsModelGeneratedQuantity": True}]},
        {"projects": [{"hasAiGeneratedQuantities": "yes"}]},
        {"projects": [{"containsAutomatedGeneratedQuantities": True}]},
        {"projects": [{"hasComputerGeneratedQuantities": True}]},
        {"metadata": {"machineGeneratedQuantity": True}},
        {"metadata": {"automatedGeneratedQuantity": True}},
        {"metadata": {"computerGeneratedQuantity": True}},
        {"metadata": {"autogeneratedQuantity": True}},
        {"metadata": {"automatedQuantity": True}},
        {"metadata": {"modelGeneratedQuantity": True}},
        {"metadata": {"quantitySources": ["LLM generated quantity takeoff"]}},
        {"metadata": {"evidenceSources": ["Claude generated measurement"]}},
        {"metadata": {"sourceDocuments": ["OpenAI quantity draft"]}},
        {"results": [{"evidence": [{"source": "LLM generated quantity takeoff"}]}]},
        {"results": [{"evidence": [{"source": "GPT generated takeoff"}]}]},
        {"results": [{"evidence": [{"source_document": "OpenAI quantity draft"}]}]},
        {"results": [{"quantity": 12, "source": "llm"}]},
        {"results": [{"quantity": 12, "source": "model"}]},
        {"results": [{"measurement": 12, "source": "large language model"}]},
        {"results": [{"quantity": 12, "source_type": "ai_generated"}]},
        {"results": [{"quantity": 12, "source": "AI"}]},
        {"results": [{"quantity": 12, "source": "GPT-5"}]},
        {"results": [{"quantity": 12, "document": "GPT generated takeoff"}]},
        {"results": [{"quantity": 12, "lineage": "OpenAI quantity draft"}]},
        {"results": [{"quantity": 12, "reference": "Claude generated measurement"}]},
        {"results": [{"quantity": 12, "source_document": "AI generated takeoff"}]},
        {"results": [{"quantity": 12, "source": "Claude"}]},
        {"results": [{"quantity": 12, "source": "machine-generated takeoff"}]},
        {"results": [{"quantity": 12, "source": "computer generated measurement"}]},
        {"results": [{"quantity": 12, "source": "automated quantity takeoff"}]},
        {"results": [{"quantity": 12, "provenance": "automated generated"}]},
        {"results": [{"quantity": 12, "provenance": "model"}]},
        {"results": [{"quantity": 12, "source": {"type": "model"}}]},
        {"results": [{"quantity": 12, "provenance": {"type": "model"}}]},
        {"results": [{"quantity": 12, "source": [{"type": "model"}]}]},
        {"results": [{"quantity": 12, "sources": [{"type": "model"}]}]},
        {"results": [{"quantity": 12, "provenance": [{"type": "model"}]}]},
        {"results": [{"quantity": 12, "source": {"kind": "llm"}}]},
        {"results": [{"quantity": 12, "lineage": {"provider": "OpenAI"}}]},
        {"takeoff": {"value": 12}, "source": {"metadata": {"generated_by": "Claude"}}},
        {"results": [{"takeoff": {"value": 12}, "provenance": "model generated"}]},
        {"aggregate": {"test_only_quantity_count": "not-a-count"}},
        {"aggregate": {"mock_count": "not-a-count"}},
    ],
)
def test_validate_release_gate_report_rejects_test_only_quantity_counters(counter_payload):
    report = _release_gate_report()
    if "aggregate" in counter_payload:
        report["aggregate"].update(counter_payload["aggregate"])
    else:
        report.update(counter_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report contains test-only or synthetic quantity evidence",
    }


def test_validate_release_gate_report_allows_explicit_zero_test_only_quantity_counters():
    report = _release_gate_report()
    report["aggregate"].update(
        {
            "test_only_quantity_count": 0,
            "test_only_count": 0,
            "mock_count": "0",
            "sample_count": 0,
            "demo_count": 0,
            "placeholder_count": 0,
            "fixture_count": 0,
            "synthetic_count": 0,
            "synthetic_fixture_quantity_count": "0",
            "contains_test_only_quantities": False,
        }
    )

    result = ar.validate_release_gate_report(report)

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


def test_validate_release_gate_report_allows_document_model_schedule_source_text():
    """Product/equipment model references in drawing source text are not AI provenance."""
    report = _release_gate_report()
    report["results"] = [
        {"quantity": 12, "source": "equipment model schedule from drawing A-501"},
        {"quantity": 3, "source": "automated door model schedule from drawing A-601"},
        {"quantity": 6, "source": "AI-501 drawing note"},
        {"takeoff": {"value": 8}, "evidence": [{"sheet_number": "A-201", "region": "detail 3"}]},
    ]

    result = ar.validate_release_gate_report(report)

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


@pytest.mark.parametrize(
    "lineage_payload",
    [
        {"results": [{"quantity": 12}]},
        {"results": [{"quantityValue": "12", "evidence": []}]},
        {"results": [{"measuredQuantity": 4, "source": ""}]},
        {"projects": [{"takeoffQuantity": 6, "provenance": {}}]},
        {"results": [{"measurement": 9, "reference": None}]},
        {"components": [{"quantity": 12}]},
        {"projects": [{"aggregate": {"components": [{"quantity": 12}]}}]},
    ],
)
def test_validate_release_gate_report_rejects_quantity_rows_without_source_lineage(lineage_payload):
    report = _release_gate_report()
    report.update(lineage_payload)

    result = ar.validate_release_gate_report(report)

    assert result == {
        "ok": False,
        "reason": "release gate report contains quantity rows without source/document lineage",
    }


def test_validate_release_gate_report_allows_explicit_not_ready_customer_delivery_text():
    report = _release_gate_report()
    report["logs"] = "estimate is not ready for customer delivery"

    result = ar.validate_release_gate_report(report)

    assert result == {"ok": True, "reason": "release gate report passed wrapper validation"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_count", True),
        ("project_count", -1),
        ("project_count", 1.5),
        ("project_count", "1.0"),
        ("project_count", ""),
        ("project_count", None),
    ],
)
def test_validate_release_gate_report_rejects_malformed_counts(field, value):
    result = ar.validate_release_gate_report(_release_gate_report(**{field: value}))

    assert result["ok"] is False
    assert result["reason"] == "release gate report has malformed/missing counts"
    assert field in result["fields"]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {
                "benchmark_eligible_count": 0,
                "benchmark_ineligible_count": 1,
                "evaluated_benchmark_eligible_count": 0,
                "evaluated_benchmark_ineligible_count": 1,
            },
            "release gate has zero evaluated benchmark-eligible projects",
        ),
        ({"skipped_count": 1, "project_count": 2, "benchmark_ineligible_count": 1}, "release gate has skipped project results"),
        ({"evaluated_benchmark_eligible_key_quantity_total": 0}, "release gate lacks complete key-quantity evidence"),
        ({"evaluation_passed_count": 0}, "release gate has unevaluated or failed project results"),
        ({"evaluated_benchmark_eligible_key_quantity_evidence_pass_count": 0}, "release gate lacks complete key-quantity evidence"),
        ({"evaluated_benchmark_eligible_document_text_extraction_pass_count": 0}, "release gate document text extraction coverage is incomplete"),
        ({"evaluated_count": 2, "evaluation_passed_count": 2}, "release gate aggregate counts are inconsistent"),
    ],
)
def test_validate_release_gate_report_fails_closed_for_unsafe_release_evidence(overrides, reason):
    result = ar.validate_release_gate_report(_release_gate_report(**overrides))

    assert result["ok"] is False
    assert result["reason"] == reason


def test_compute_score_uses_weighted_formula():
    result = ar.compute_score(_report())
    # 100*.25 + 100*.5 + 50*(2/4) + 25*(3/4) - 20*1 = 98.75
    assert result["score"] == 98.75
    assert result["components"] == {
        "scope_keyword_coverage_micro": 25.0,
        "trade_recall_micro": 50.0,
        "key_quantity_pass_rate": 25.0,
        "key_quantity_evidence_pass_rate": 18.75,
        "unexpected_false_positive_penalty": -20.0,
        "safety_violation_penalty": -0.0,
        "harness_failed_penalty": -0.0,
    }
    assert result["metrics"]["key_quantity_pass_rate"] == 0.5
    assert result["metrics"]["aggregate_present"] is True
    assert result["schema_version"] == "mobi-autoresearch-score-v1"


def test_compute_score_missing_aggregate_is_flagged_but_safe():
    result = ar.compute_score({})
    assert result["metrics"]["aggregate_present"] is False
    assert result["score"] == 75.0


def test_compute_score_zero_quantity_denominator_defaults_to_not_penalized():
    result = ar.compute_score(
        _report(
            key_quantity_pass_count=0,
            key_quantity_evidence_pass_count=0,
            key_quantity_total=0,
            scope_keyword_coverage_micro=0,
            trade_recall_micro=0,
            trade_unexpected_false_positive_total=0,
        )
    )
    assert result["metrics"]["key_quantity_pass_rate"] == 1.0
    assert result["metrics"]["key_quantity_evidence_pass_rate"] == 1.0
    assert result["score"] == 75.0


def test_compute_score_penalizes_safety_and_harness_failures():
    result = ar.compute_score(_report(safety_violation_count=1, harness_failed_count=2))
    assert result["components"]["safety_violation_penalty"] == -1000.0
    assert result["components"]["harness_failed_penalty"] == -200.0
    assert result["score"] == -1101.25


def test_normalize_repo_path_preserves_dotfile_names():
    assert ar._normalize_repo_path("./.github/workflows/ci.yml") == ".github/workflows/ci.yml"


def test_evaluate_guard_allows_only_allowed_paths():
    result = ar.evaluate_guard(
        [
            "mobi-estimating-phase1/app/extraction/rules.json",
            "mobi-estimating-phase1/app/extraction/prompts/drawing.md",
        ],
        ["mobi-estimating-phase1/app/extraction/"],
    )
    assert result["ok"] is True
    assert result["locked_violations"] == []
    assert result["outside_allowed_violations"] == []


def test_evaluate_guard_rejects_outside_allowed_paths():
    result = ar.evaluate_guard(
        [
            "mobi-estimating-phase1/app/extraction/rules.json",
            "mobi-estimating-phase1/app/main.py",
        ],
        ["mobi-estimating-phase1/app/extraction/"],
    )
    assert result["ok"] is False
    assert result["outside_allowed_violations"] == ["mobi-estimating-phase1/app/main.py"]


def test_evaluate_guard_rejects_locked_paths_even_if_allowed():
    changed = [
        "mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json",
        "mobi-estimating-phase1/scripts/golden_set_extraction_eval.py",
        "mobi-estimating-phase1/data/golden_set_v2/documents/example.pdf",
    ]
    result = ar.evaluate_guard(
        changed,
        [
            "mobi-estimating-phase1/data/golden_set_v2/",
            "mobi-estimating-phase1/scripts/",
        ],
    )
    assert result["ok"] is False
    assert result["locked_violations"] == changed
    assert result["outside_allowed_violations"] == []


def test_append_ledger_writes_jsonl_record(tmp_path):
    score_path = tmp_path / "score.json"
    score_payload = ar.compute_score(_report())
    score_path.write_text(json.dumps(score_payload), encoding="utf-8")
    ledger = tmp_path / "experiments.jsonl"

    record = ar.append_ledger(
        ledger,
        experiment_id="baseline-001",
        score_json=score_path,
        status="baseline",
        notes="initial score",
    )

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed == record
    assert parsed["experiment_id"] == "baseline-001"
    assert parsed["status"] == "baseline"
    assert parsed["score"]["score"] == 98.75


def test_compute_score_records_release_gate_validation():
    baseline_score = ar.compute_score(_report())
    release_score = ar.compute_score(_release_gate_report())

    assert baseline_score["release_gate_validation"] == {
        "ok": False,
        "reason": "release gate report does not prove it came from a strict release-gate run",
    }
    assert release_score["release_gate_validation"] == {
        "ok": True,
        "reason": "release gate report passed wrapper validation",
    }


@pytest.mark.parametrize("score_payload", [ar.compute_score(_report()), {"score": 98.75}])
def test_append_ledger_rejects_accepted_status_without_release_gate_evidence(tmp_path, score_payload):
    score_path = tmp_path / "score.json"
    score_path.write_text(json.dumps(score_payload), encoding="utf-8")

    with pytest.raises(ValueError, match="strict release-gate validation evidence"):
        ar.append_ledger(
            tmp_path / "ledger.jsonl",
            experiment_id="unsafe-accepted",
            score_json=score_path,
            status="accepted",
            notes="must not promote baseline or legacy score evidence",
        )


@pytest.mark.parametrize("status", ["rejected", "baseline"])
def test_append_ledger_allows_nonpromotion_status_without_release_gate_evidence(tmp_path, status):
    score_path = tmp_path / "score.json"
    score_path.write_text(json.dumps(ar.compute_score(_report())), encoding="utf-8")

    record = ar.append_ledger(
        tmp_path / "ledger.jsonl",
        experiment_id=f"{status}-nonpromotion",
        score_json=score_path,
        status=status,
        notes="non-promotion ledger evidence can be retained for diagnostics",
    )

    assert record["status"] == status


def test_append_ledger_accepts_strict_release_gate_evidence(tmp_path):
    score_path = tmp_path / "score.json"
    score_path.write_text(json.dumps(ar.compute_score(_release_gate_report())), encoding="utf-8")
    ledger = tmp_path / "experiments.jsonl"

    record = ar.append_ledger(
        ledger,
        experiment_id="release-accepted",
        score_json=score_path,
        status="accepted",
        notes="strict release gate passed",
    )

    assert record["status"] == "accepted"
    assert record["score"]["release_gate_validation"]["ok"] is True
    assert ledger.exists()


def test_append_ledger_rejects_bad_status(tmp_path):
    score_path = tmp_path / "score.json"
    score_path.write_text(json.dumps(ar.compute_score(_report())), encoding="utf-8")
    with pytest.raises(ValueError, match="status"):
        ar.append_ledger(
            tmp_path / "ledger.jsonl",
            experiment_id="bad",
            score_json=score_path,
            status="kept",
            notes="bad status",
        )


def test_cli_score_writes_json_output(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    score_path = tmp_path / "score.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")

    exit_code = ar.main(["score", "--report", str(report_path), "--output", str(score_path)])

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out)
    written = json.loads(score_path.read_text(encoding="utf-8"))
    assert stdout["score"] == 98.75
    assert written["score"] == 98.75


def test_cli_guard_returns_nonzero_on_locked_violation(monkeypatch, capsys):
    monkeypatch.setattr(
        ar,
        "collect_changed_paths",
        lambda base_ref: ["mobi-estimating-phase1/data/golden_set_v2/sources.v2.json"],
    )
    exit_code = ar.main(
        [
            "guard",
            "--base-ref",
            "main",
            "--allowed",
            "mobi-estimating-phase1/data/golden_set_v2/",
        ]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["locked_violations"] == [
        "mobi-estimating-phase1/data/golden_set_v2/sources.v2.json"
    ]


def test_collect_changed_paths_reads_committed_staged_unstaged_and_untracked(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.PIPE)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "committed.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, stdout=subprocess.PIPE)

    (repo / "committed.txt").write_text("head", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=repo, check=True, stdout=subprocess.PIPE)

    (repo / "staged.txt").write_text("staged", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=repo, check=True)
    (repo / "unstaged.txt").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "unstaged.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "unstaged base"], cwd=repo, check=True, stdout=subprocess.PIPE)
    (repo / "unstaged.txt").write_text("changed", encoding="utf-8")
    (repo / "untracked.txt").write_text("new", encoding="utf-8")

    changed = ar.collect_changed_paths("HEAD~2", repo_root=repo)

    assert changed == ["committed.txt", "staged.txt", "unstaged.txt", "untracked.txt"]


def test_baseline_cli_resolves_repo_relative_paths_and_scores(monkeypatch, tmp_path, capsys):
    report_payload = _report(
        scope_keyword_coverage_micro=1.0,
        trade_recall_micro=1.0,
        key_quantity_pass_count=1,
        key_quantity_evidence_pass_count=1,
        key_quantity_total=1,
        trade_unexpected_false_positive_total=0,
    )
    commands = []

    def fake_run(command, *, cwd):
        commands.append((command, cwd))
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report_payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="eval ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = Path("reports/out.json")
    workdir = Path("work/run")

    exit_code = ar.main(
        [
            "baseline",
            "--manifest",
            "manifest.json",
            "--output",
            str(output),
            "--workdir",
            str(workdir),
            "--python",
            "python3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["score"]["score"] == 275.0
    command, cwd = commands[0]
    assert cwd == ar.ENGINE_ROOT
    assert command[command.index("--manifest") + 1] == str(manifest.resolve())
    assert command[command.index("--output") + 1] == str((tmp_path / output).resolve())
    assert command[command.index("--workdir") + 1] == str((tmp_path / workdir).resolve())
    assert "--no-fail-on-accuracy" in command
    assert "--report-only-baseline" in command
    assert "--release-gate" not in command


def test_release_gate_uses_strict_evaluator_without_accuracy_bypass(tmp_path, monkeypatch, capsys):
    report_payload = _release_gate_report()
    commands: list[tuple[list[str], Path]] = []

    def fake_run(command, *, cwd):
        commands.append((command, cwd))
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report_payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="release gate ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    output = Path("reports/release-gate.json")
    workdir = Path("work/release")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            str(output),
            "--workdir",
            str(workdir),
            "--python",
            "python3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["release_gate"] is True
    command, cwd = commands[0]
    assert cwd == ar.ENGINE_ROOT
    assert command[command.index("--manifest") + 1] == str(manifest.resolve())
    assert command[command.index("--output") + 1] == str((tmp_path / output).resolve())
    assert command[command.index("--workdir") + 1] == str((tmp_path / workdir).resolve())
    assert "--release-gate" in command
    assert "--no-fail-on-accuracy" not in command
    assert "--report-only-baseline" not in command
    assert "--allow-missing-documents" not in command
    assert payload["release_gate_validation"]["ok"] is True


def test_release_gate_rejects_stale_report_when_evaluator_writes_nothing(tmp_path, monkeypatch, capsys):
    """A prior report at the output path must not be re-used as release evidence."""
    output = tmp_path / "reports/release-gate.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_release_gate_report()), encoding="utf-8")

    def fake_run(command, *, cwd):
        assert Path(command[command.index("--output") + 1]) == output
        return subprocess.CompletedProcess(command, 0, stdout="stale evaluator ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            str(output),
            "--workdir",
            "work/release",
            "--python",
            "python3",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["release_gate"] is True
    assert "score" not in payload
    assert payload["release_gate_validation"] == {
        "ok": False,
        "reason": "evaluator exited 0 without writing a release gate report",
    }
    assert not output.exists()


def test_release_gate_wrapper_rejects_zero_eligible_success_report(tmp_path, monkeypatch, capsys):
    """A stale/mocked evaluator exit 0 cannot promote zero eligible evidence."""
    report_payload = _release_gate_report(
        project_count=1,
        evaluated_count=1,
        benchmark_eligible_count=0,
        benchmark_ineligible_count=1,
        evaluated_benchmark_eligible_count=0,
        evaluated_benchmark_ineligible_count=1,
        evaluated_benchmark_eligible_key_quantity_total=0,
        evaluated_benchmark_eligible_key_quantity_pass_count=0,
        evaluated_benchmark_eligible_key_quantity_evidence_pass_count=0,
        evaluated_benchmark_eligible_document_text_extraction_pass_count=0,
    )

    def fake_run(command, *, cwd):
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report_payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="stale evaluator ok", stderr="")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            "reports/release-gate.json",
            "--workdir",
            "work/release",
            "--python",
            "python3",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["release_gate"] is True
    assert payload["release_gate_validation"]["ok"] is False
    assert payload["release_gate_validation"]["reason"] == "release gate has zero evaluated benchmark-eligible projects"


def test_release_gate_propagates_strict_failure_without_score_file(tmp_path, monkeypatch, capsys):
    commands: list[list[str]] = []

    def fake_run(command, *, cwd):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="zero eligible projects")

    monkeypatch.setattr(ar, "_run", fake_run)
    monkeypatch.chdir(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    exit_code = ar.main(
        [
            "release-gate",
            "--manifest",
            "manifest.json",
            "--output",
            "reports/release-gate.json",
            "--workdir",
            "work/release",
            "--python",
            "python3",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["release_gate"] is True
    assert payload["exit_code"] == 1
    assert payload["stderr"] == "zero eligible projects"
    command = commands[0]
    assert "--release-gate" in command
    assert "--no-fail-on-accuracy" not in command
    assert not (tmp_path / "reports/release-gate.json").exists()
