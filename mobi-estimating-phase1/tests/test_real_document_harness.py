"""Real document harness tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import fitz


def test_harness_testclient_reports_server_errors_instead_of_raising():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "real_document_harness.py").read_text()
    assert "TestClient(app, raise_server_exceptions=False)" in script


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "ELECTRICAL LIGHTING PLAN\nPANEL SCHEDULE\nLIGHT FIXTURES AND OUTLETS", fontsize=10)
    page.insert_text((480, 744), "E-101", fontsize=11)
    page.insert_text((400, 768), "ELECTRICAL PLAN", fontsize=9)
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "PLUMBING FIXTURE SCHEDULE\nSANITARY WATER GAS LINE", fontsize=10)
    page.insert_text((480, 744), "P-201", fontsize=11)
    page.insert_text((400, 768), "PLUMBING PLAN", fontsize=9)
    doc.save(path)
    doc.close()


def test_real_document_harness_runs_pipeline(tmp_path):
    pdf_path = tmp_path / "sample_bid_set.pdf"
    output_path = tmp_path / "report.json"
    workdir = tmp_path / "harness"
    _make_pdf(pdf_path)

    script = Path(__file__).resolve().parents[1] / "scripts" / "real_document_harness.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(pdf_path),
            "--project-name",
            "Harness Test",
            "--workdir",
            str(workdir),
            "--output",
            str(output_path),
            "--apply-test-inputs",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
    )
    assert output_path.exists(), proc.stdout + proc.stderr
    report = json.loads(output_path.read_text())
    assert report["project_id"]
    assert report["stages"]["upload"]["ok"] is True
    assert report["stages"]["process"]["ok"] is True
    assert report["stages"]["coverage_draft"]["ok"] is True
    assert report["stages"]["readiness"]["ok"] is True
    assert report["stages"]["readiness"]["body"]["customer_delivery_ready"] is False
    assert report["stages"]["readiness_after_test_inputs"]["ok"] is True
    assert report["stages"]["readiness_after_test_inputs"]["body"]["status"] == "blocked"
    assert report["stages"]["owner_review_after_test_inputs"]["ok"] is True
    assert report["stages"]["owner_review_after_test_inputs"]["body"]["status"] == "blocked"
    assert report["stages"]["clarification_package_after_test_inputs"]["ok"] is True
    assert report["stages"]["owner_review_after_test_inputs"]["body"]["customer_delivery_ready"] is False
    assert report["stages"]["readiness_after_test_inputs"]["body"]["customer_delivery_ready"] is False
    clarification = report["stages"]["clarification_package_after_test_inputs"]["body"]
    assert clarification["customer_message_ready"] is False
    assert clarification["send_ready"] is False
    blocker_codes = {
        blocker["code"]
        for blocker in report["stages"]["readiness_after_test_inputs"]["body"]["blockers"]
    }
    assert "missing_extraction_provenance" in blocker_codes
    assert report["safety"]["customer_delivery"] is False
    assert report["safety"]["test_inputs_only"] is True
    assert report["summary"]["stage_count"] >= 10
    assert report["summary"]["failed_stage_count"] == 0
    assert report["summary"]["stage_success_rate"] == 1
    assert report["summary"]["outputs"]["sheet_count"] == 2
    assert report["summary"]["outputs"]["document_source_type_counts"]["drawing"] == 2
    assert report["summary"]["outputs"]["sheet_processing_status_counts"]["complete"] == 2
    assert report["summary"]["outputs"]["sheet_requires_ocr_count"] >= 0
    assert report["summary"]["outputs"]["sheet_requires_review_count"] >= 0
    assert report["summary"]["outputs"]["sheet_low_information_text_layer_count"] >= 0
    assert report["summary"]["outputs"]["sheet_very_low_information_text_layer_count"] >= 0
    assert report["summary"]["outputs"]["sheet_text_detail_missing_count"] == 0
    assert report["summary"]["outputs"]["sheet_text_char_count_min"] is not None
    assert report["summary"]["outputs"]["sheet_text_char_count_avg"] is not None
    assert report["summary"]["outputs"]["sheet_text_char_count_max"] is not None
    assert report["summary"]["outputs"]["sheet_detection_confidence_avg"] is not None
    assert report["summary"]["outputs"]["trade_quality_summary"]
    assert report["summary"]["outputs"]["coverage_finding_count"] >= 0
    assert report["summary"]["outputs"]["scope_items_with_trusted_evidence_count"] >= 0
    assert report["summary"]["outputs"]["scope_items_missing_trusted_evidence_count"] >= 0
    assert report["summary"]["outputs"]["generic_pricing_scope_item_count"] > 0
    assert report["summary"]["outputs"]["pricing_method_assigned_count"] > 0
    assert report["summary"]["outputs"]["pricing_method_unassigned_count"] == 0
    assert report["summary"]["outputs"]["pricing_ready_scope_item_count"] >= 0
    assert report["summary"]["outputs"]["pricing_not_ready_scope_item_count"] >= 0
    assert report["summary"]["outputs"]["priced_scope_item_count"] >= 0
    assert report["summary"]["outputs"]["unpriced_scope_item_count"] >= 0
    assert "unit_rate_needed" in report["summary"]["outputs"]["pricing_method_counts"]
    assert report["summary"]["outputs"]["formula_check_scope_item_count"] > 0
    assert report["summary"]["outputs"]["formula_check_ready_count"] >= 0
    assert report["summary"]["outputs"]["formula_check_blocked_count"] >= 0
    assert (
        report["summary"]["outputs"]["formula_check_ready_count"]
        + report["summary"]["outputs"]["formula_check_blocked_count"]
        == report["summary"]["outputs"]["formula_check_scope_item_count"]
    )
    assert report["summary"]["outputs"]["formula_check_ready_rate"] >= 0
    assert "unit_rate_needed" in report["summary"]["outputs"]["formula_check_method_counts"]
    assert isinstance(report["summary"]["outputs"]["formula_check_blocker_counts"], dict)
    assert report["summary"]["outputs"]["formula_check_by_trade"]
    assert report["summary"]["outputs"]["missing_quantity_pricing_blocker_count"] >= 0
    assert report["summary"]["outputs"]["missing_unit_rate_pricing_blocker_count"] >= 0
    assert report["summary"]["outputs"]["missing_subcontract_quote_pricing_blocker_count"] >= 0
    assert report["summary"]["outputs"]["missing_allowance_basis_pricing_blocker_count"] >= 0
    assert report["summary"]["outputs"]["low_confidence_item_count"] >= 0
    assert report["summary"]["outputs"]["quantity_basis_unclear_count"] >= 0
    assert report["summary"]["outputs"]["trusted_evidence_coverage_rate"] >= 0
    assert report["summary"]["outputs"]["scope_items_with_evidence_quote_count"] >= 0
    assert report["summary"]["outputs"]["scope_items_missing_evidence_quote_count"] >= 0
    assert report["summary"]["outputs"]["evidence_quote_count"] >= 0
    assert report["summary"]["outputs"]["evidence_quote_coverage_rate"] >= 0
    assert isinstance(report["summary"]["outputs"]["evidence_quote_by_trade"], list)
    assert report["summary"]["outputs"]["quantity_scope_item_count"] == report["summary"]["outputs"]["scope_item_count"]
    assert report["summary"]["outputs"]["quantity_present_count"] >= 0
    assert report["summary"]["outputs"]["quantity_missing_count"] >= 0
    assert report["summary"]["outputs"]["quantity_traceable_count"] >= 0
    assert report["summary"]["outputs"]["quantity_test_input_count"] >= 0
    assert report["summary"]["outputs"]["quantity_traceable_rate"] >= 0
    assert report["summary"]["outputs"]["quantity_confidence_by_trade"]
    assert report["summary"]["outputs"]["quantity_extraction_candidate_count"] >= 0
    assert isinstance(report["summary"]["outputs"]["quantity_extraction_candidates"], list)
    assert isinstance(report["summary"]["outputs"]["quantity_extraction_candidate_by_trade"], list)
    assert report["summary"]["outputs"]["manual_quantity_input_count"] >= 0
    assert report["summary"]["outputs"]["quantity_extraction_test_input_count"] >= 0
    assert report["summary"]["outputs"]["assumption_count"] >= 0
    assert report["summary"]["outputs"]["exclusion_count"] >= 0
    assert report["summary"]["outputs"]["open_question_count"] >= 0
    assert report["summary"]["outputs"]["register_blocking_entry_count"] >= 0
    assert report["summary"]["outputs"]["clarification_candidate_count"] >= 0
    assert report["summary"]["outputs"]["blocking_clarification_candidate_count"] >= 0
    assert report["summary"]["outputs"]["customer_safe_clarification_candidate_count"] >= 0
    assert report["summary"]["outputs"]["clarification_customer_message_ready"] is False
    assert report["summary"]["outputs"]["clarification_send_ready"] is False
    assert "coverage_validate" in report["summary"]["per_stage"]
    assert "clarification_package" in report["summary"]["per_stage"]
    assert report["summary"]["outputs"]["readiness_status"] == "blocked"
    assert report["summary"]["outputs"]["customer_delivery_ready"] is False
    review_package = report["summary"]["outputs"]["automation_review_package"]
    assert review_package["status"] == "blocked_before_customer_delivery"
    assert review_package["customer_delivery_ready"] is False
    assert review_package["final_estimate_approved"] is False
    assert review_package["external_messages"] is False
    assert review_package["payments"] is False
    assert isinstance(review_package["ready"], dict)
    assert isinstance(review_package["human_review_needed"], dict)
    assert isinstance(review_package["blocked"], dict)
    assert isinstance(review_package["top_followups"], dict)
    assert report["summary"]["per_stage"]["process"]["duration_ms"] >= 0


def test_real_document_harness_summary_prefers_post_test_input_stages():
    from scripts import real_document_harness

    report = {
        "stages": {
            "readiness": {
                "ok": True,
                "status_code": 200,
                "body": {"status": "initial", "customer_delivery_ready": True, "details": {}},
            },
            "owner_review": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "status": "initial",
                    "review_packet": {
                        "assumptions_register": {
                            "summary": {
                                "assumption_count": 1,
                                "exclusion_count": 1,
                                "open_question_count": 1,
                                "blocking_entry_count": 1,
                            }
                        }
                    },
                },
            },
            "readiness_after_test_inputs": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "status": "after",
                    "customer_delivery_ready": False,
                    "details": {
                        "provenance_confidence": {
                            "items_with_trusted_evidence_count": 1,
                            "items_missing_trusted_evidence_count": 2,
                            "low_confidence_item_count": 1,
                            "quantity_basis_unclear_count": 1,
                            "trusted_evidence_coverage_rate": 0.25,
                            "items_with_trusted_evidence": [{"scope_item_id": "scope-1", "trade_code": "electrical"}],
                            "missing_extraction_provenance": [
                                {"scope_item_id": "scope-2", "trade_code": "plumbing"},
                                {"scope_item_id": "scope-4", "trade_code": "electrical"},
                            ],
                            "low_extraction_confidence": [{"scope_item_id": "scope-2", "trade_code": "plumbing"}],
                            "quantity_basis_unclear": [{"scope_item_id": "scope-4", "trade_code": "electrical"}],
                        }
                    },
                },
            },
            "owner_review_after_test_inputs": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "status": "after",
                    "review_packet": {
                        "assumptions_register": {
                            "summary": {
                                "assumption_count": 2,
                                "exclusion_count": 3,
                                "open_question_count": 4,
                                "blocking_entry_count": 5,
                            }
                        },
                        "clarification_package": {
                            "customer_message_ready": True,
                            "send_ready": True,
                            "summary": {
                                "candidate_count": 99,
                                "blocking_candidate_count": 98,
                                "critical_candidate_count": 97,
                                "customer_safe_candidate_count": 96,
                            },
                        },
                    },
                },
            },
            "sheets": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "items": [
                        {
                            "detected_sheet_number": "E-101",
                            "detected_sheet_title": "ELECTRICAL PLAN",
                            "detection_confidence": 0.92,
                            "requires_ocr": False,
                            "requires_review": False,
                            "processing_status": "complete",
                            "text_char_count": 450,
                        },
                        {
                            "detected_sheet_number": "S-001",
                            "detected_sheet_title": "SPECIFICATION SCHEDULE",
                            "detection_confidence": 0.7,
                            "requires_ocr": True,
                            "requires_review": True,
                            "processing_status": "complete",
                            "text_char_count": 40,
                        },
                    ]
                },
            },
            "scope_items_after_test_inputs": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "items": [
                        {
                            "id": "scope-1",
                            "trade_code": "electrical",
                            "category_code": "generic_scope",
                            "extraction_confidence": 0.82,
                            "quantity": "10",
                            "unit": "EA",
                            "quantity_basis": "sheet_count",
                            "raw_quantity_inputs": {"manual_takeoff_v1": {"source": "sheet E-101"}},
                            "trade_data": {
                                "pricing_method": "unit_rate_needed",
                                "pricing_ready": True,
                                "pricing_basis": {"amount": "100", "source": "harness_test_only_pricing"},
                            },
                            "blocking_issues": [],
                            "evidence": [
                                {
                                    "extracted_text_quote": "E-101 ELECTRICAL LIGHTING PLAN - 12 fixtures",
                                    "requires_human_verification": True,
                                }
                            ],
                        },
                        {
                            "id": "scope-2",
                            "trade_code": "plumbing",
                            "category_code": "generic_scope",
                            "extraction_confidence": 0.44,
                            "quantity": "10",
                            "unit": "EA",
                            "quantity_basis": "takeoff_or_schedule_count",
                            "raw_quantity_inputs": {"verified_quantity_input_v1": {"source": "harness_test_only_quantity"}},
                            "trade_data": {"pricing_method": "quote_based", "pricing_ready": False},
                            "blocking_issues": [{"code": "missing_subcontract_quote"}],
                            "evidence": [
                                {
                                    "extracted_text_quote": "PLUMBING FIXTURE SCHEDULE",
                                    "requires_human_verification": False,
                                }
                            ],
                        },
                        {
                            "id": "scope-3",
                            "trade_code": "plumbing",
                            "category_code": "generic_scope",
                            "quantity": "5",
                            "unit": "LS",
                            "quantity_basis": "unknown",
                            "trade_data": {"pricing_method": "allowance", "pricing_ready": False},
                            "blocking_issues": [{"code": "missing_allowance_basis"}],
                        },
                        {
                            "id": "scope-4",
                            "trade_code": "electrical",
                            "category_code": "generic_scope",
                            "trade_data": {"pricing_method": "unit_rate_needed", "pricing_ready": False},
                            "blocking_issues": [{"code": "missing_quantity"}, {"code": "missing_unit_rate"}],
                        },
                    ]
                },
            },
            "quantity_requirements_after_test_inputs": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "items": [
                        {"id": "qr-1", "scope_item_id": "scope-4", "trade_code": "electrical", "status": "open"},
                        {"id": "qr-2", "scope_item_id": "scope-2", "trade_code": "plumbing", "status": "resolved"},
                    ]
                },
            },
            "generic_estimate_draft_after_test_inputs": {
                "ok": True,
                "status_code": 201,
                "body": {
                    "summary": {
                        "ready_scope_item_count": 1,
                        "blocked_scope_item_count": 3,
                        "line_item_count": 1,
                        "customer_delivery_ready": False,
                        "final_estimate_approved": False,
                        "external_messages": False,
                        "payments": False,
                    }
                },
            },
            "generic_proposal_preview_after_test_inputs": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "customer_safe_preview": {
                        "summary": {
                            "scope_line_count": 1,
                            "blocked_scope_item_count": 3,
                            "customer_delivery_ready": False,
                            "final_estimate_approved": False,
                            "external_messages": False,
                            "payments": False,
                        },
                        "safety_flags": {
                            "proposal_created": False,
                            "proposal_issued": False,
                        },
                    }
                },
            },
            "clarification_package_after_test_inputs": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "customer_message_ready": False,
                    "send_ready": False,
                    "summary": {
                        "candidate_count": 6,
                        "blocking_candidate_count": 5,
                        "critical_candidate_count": 4,
                        "customer_safe_candidate_count": 6,
                        "urgent_candidate_count": 2,
                        "high_candidate_count": 3,
                        "top_candidate_ids": ["clarification_a", "clarification_b"],
                    },
                    "groups": {
                        "by_trade": [
                            {"key": "electrical", "count": 4, "blocking_count": 4, "critical_count": 2, "highest_priority_score": 130},
                            {"key": "plumbing", "count": 2, "blocking_count": 1, "critical_count": 2, "highest_priority_score": 120},
                        ],
                        "by_source_code": [
                            {"key": "missing_quantity", "count": 3, "blocking_count": 3, "critical_count": 2, "highest_priority_score": 130},
                        ],
                    },
                },
            },
        }
    }

    summary = real_document_harness._build_stage_summary(report)

    assert summary["outputs"]["readiness_status"] == "after"
    assert summary["outputs"]["owner_review_status"] == "after"
    assert summary["outputs"]["customer_delivery_ready"] is False
    assert summary["outputs"]["document_source_type_counts"] == {"drawing": 1, "spec_or_schedule": 1}
    assert summary["outputs"]["sheet_processing_status_counts"] == {"complete": 2}
    assert summary["outputs"]["sheet_requires_ocr_count"] == 1
    assert summary["outputs"]["sheet_requires_review_count"] == 1
    assert summary["outputs"]["sheet_low_information_text_layer_count"] == 0
    assert summary["outputs"]["sheet_very_low_information_text_layer_count"] == 0
    assert summary["outputs"]["sheet_text_detail_missing_count"] == 0
    assert summary["outputs"]["sheet_text_layer_quality_counts"] == {"unknown": 2}
    assert summary["outputs"]["sheet_recommended_extraction_route_counts"] == {}
    assert summary["outputs"]["table_schedule_extraction_candidate_count"] == 1
    assert summary["outputs"]["table_schedule_extraction_candidate_quality_counts"] == {"unknown": 1}
    assert summary["outputs"]["table_schedule_extraction_candidates"][0]["sheet_number"] == "S-001"
    assert summary["outputs"]["table_schedule_extraction_candidates"][0]["candidate_reasons"] == ["title_contains_schedule"]
    assert summary["outputs"]["table_schedule_extraction_candidates"][0]["final_quantity_extraction"] is False
    assert summary["outputs"]["sheet_text_char_count_min"] == 40
    assert summary["outputs"]["sheet_text_char_count_avg"] == 245.0
    assert summary["outputs"]["sheet_text_char_count_max"] == 450
    assert summary["outputs"]["sheet_detection_confidence_min"] == 0.7
    assert summary["outputs"]["sheet_detection_confidence_avg"] == 0.81
    assert summary["outputs"]["sheet_detection_confidence_max"] == 0.92
    assert summary["outputs"]["generic_pricing_scope_item_count"] == 4
    assert summary["outputs"]["pricing_method_assigned_count"] == 4
    assert summary["outputs"]["pricing_method_unassigned_count"] == 0
    assert summary["outputs"]["pricing_ready_scope_item_count"] == 1
    assert summary["outputs"]["pricing_not_ready_scope_item_count"] == 3
    assert summary["outputs"]["priced_scope_item_count"] == 1
    assert summary["outputs"]["unpriced_scope_item_count"] == 3
    assert summary["outputs"]["pricing_method_counts"] == {
        "unit_rate_needed": 2,
        "quote_based": 1,
        "allowance": 1,
    }
    assert summary["outputs"]["formula_check_scope_item_count"] == 4
    assert summary["outputs"]["formula_check_ready_count"] == 1
    assert summary["outputs"]["formula_check_blocked_count"] == 3
    assert summary["outputs"]["formula_check_ready_rate"] == 0.25
    assert summary["outputs"]["formula_check_method_counts"] == {
        "unit_rate_needed": 2,
        "quote_based": 1,
        "allowance": 1,
    }
    assert summary["outputs"]["formula_check_blocker_counts"] == {
        "missing_quantity": 1,
        "test_quantity_only": 1,
        "unclear_quantity_basis": 1,
    }
    assert summary["outputs"]["formula_check_by_trade"][0]["trade_code"] == "plumbing"
    assert summary["outputs"]["formula_check_by_trade"][0]["formula_check_blocked_count"] == 2
    assert summary["outputs"]["formula_check_by_trade"][0]["formula_check_ready_count"] == 0
    assert summary["outputs"]["formula_check_by_trade"][0]["formula_check_test_input_count"] == 1
    assert summary["outputs"]["formula_check_by_trade"][1]["trade_code"] == "electrical"
    assert summary["outputs"]["formula_check_by_trade"][1]["formula_check_ready_count"] == 1
    assert summary["outputs"]["formula_check_by_trade"][1]["formula_check_blocked_count"] == 1
    assert summary["outputs"]["generic_estimate_draft_ready_scope_item_count"] == 1
    assert summary["outputs"]["generic_estimate_draft_blocked_scope_item_count"] == 3
    assert summary["outputs"]["generic_estimate_draft_line_item_count"] == 1
    assert summary["outputs"]["generic_estimate_draft_customer_delivery_ready"] is False
    assert summary["outputs"]["generic_estimate_draft_final_estimate_approved"] is False
    assert summary["outputs"]["generic_estimate_draft_external_messages"] is False
    assert summary["outputs"]["generic_estimate_draft_payments"] is False
    assert summary["outputs"]["generic_proposal_preview_scope_line_count"] == 1
    assert summary["outputs"]["generic_proposal_preview_blocked_scope_item_count"] == 3
    assert summary["outputs"]["generic_proposal_preview_customer_delivery_ready"] is False
    assert summary["outputs"]["generic_proposal_preview_final_estimate_approved"] is False
    assert summary["outputs"]["generic_proposal_preview_external_messages"] is False
    assert summary["outputs"]["generic_proposal_preview_payments"] is False
    assert summary["outputs"]["generic_proposal_preview_proposal_created"] is False
    assert summary["outputs"]["generic_proposal_preview_proposal_issued"] is False
    assert summary["outputs"]["missing_quantity_pricing_blocker_count"] == 1
    assert summary["outputs"]["missing_unit_rate_pricing_blocker_count"] == 1
    assert summary["outputs"]["missing_subcontract_quote_pricing_blocker_count"] == 1
    assert summary["outputs"]["missing_allowance_basis_pricing_blocker_count"] == 1
    assert summary["outputs"]["scope_items_with_trusted_evidence_count"] == 1
    assert summary["outputs"]["scope_items_missing_trusted_evidence_count"] == 2
    assert summary["outputs"]["low_confidence_item_count"] == 1
    assert summary["outputs"]["quantity_basis_unclear_count"] == 1
    assert summary["outputs"]["trusted_evidence_coverage_rate"] == 0.25
    assert summary["outputs"]["scope_items_with_evidence_quote_count"] == 2
    assert summary["outputs"]["scope_items_missing_evidence_quote_count"] == 2
    assert summary["outputs"]["evidence_quote_count"] == 2
    assert summary["outputs"]["evidence_human_verification_required_count"] == 1
    assert summary["outputs"]["evidence_quote_coverage_rate"] == 0.5
    assert summary["outputs"]["evidence_quote_by_trade"][0]["trade_code"] == "electrical"
    assert summary["outputs"]["evidence_quote_by_trade"][0]["items_missing_evidence_quote_count"] == 1
    assert summary["outputs"]["evidence_quote_by_trade"][1]["trade_code"] == "plumbing"
    assert summary["outputs"]["evidence_quote_by_trade"][1]["evidence_quote_count"] == 1
    assert summary["outputs"]["trade_quality_summary"][0]["trade_code"] == "electrical"
    assert summary["outputs"]["trade_quality_summary"][0]["quality_blocker_count"] == 4
    assert summary["outputs"]["trade_quality_summary"][1]["trade_code"] == "plumbing"
    assert summary["outputs"]["trade_quality_summary"][1]["quality_blocker_count"] == 4
    assert summary["outputs"]["quantity_scope_item_count"] == 4
    assert summary["outputs"]["quantity_present_count"] == 3
    assert summary["outputs"]["quantity_missing_count"] == 1
    assert summary["outputs"]["quantity_traceable_count"] == 1
    assert summary["outputs"]["quantity_unclear_basis_count"] == 1
    assert summary["outputs"]["quantity_test_input_count"] == 1
    assert summary["outputs"]["open_quantity_requirement_count"] == 1
    assert summary["outputs"]["resolved_quantity_requirement_count"] == 1
    assert summary["outputs"]["quantity_traceable_rate"] == 0.25
    assert summary["outputs"]["quantity_confidence_by_trade"][0]["trade_code"] == "plumbing"
    assert summary["outputs"]["quantity_confidence_by_trade"][0]["quantity_gap_count"] == 2
    assert summary["outputs"]["quantity_confidence_by_trade"][1]["trade_code"] == "electrical"
    assert summary["outputs"]["quantity_confidence_by_trade"][1]["quantity_gap_count"] == 1
    assert summary["outputs"]["quantity_extraction_candidate_count"] == 1
    assert summary["outputs"]["quantity_extraction_candidates"][0]["quantity_candidate_text"] == "12 fixtures"
    assert summary["outputs"]["quantity_extraction_candidates"][0]["requires_human_review"] is True
    assert summary["outputs"]["quantity_extraction_candidates"][0]["final_quantity_extraction"] is False
    assert summary["outputs"]["quantity_extraction_candidates"][0]["estimate_ready"] is False
    assert summary["outputs"]["quantity_extraction_candidate_by_trade"][0]["trade_code"] == "electrical"
    assert summary["outputs"]["manual_quantity_input_count"] == 1
    assert summary["outputs"]["quantity_extraction_test_input_count"] == 1
    assert summary["outputs"]["assumption_count"] == 2
    assert summary["outputs"]["exclusion_count"] == 3
    assert summary["outputs"]["open_question_count"] == 4
    assert summary["outputs"]["register_blocking_entry_count"] == 5
    assert summary["outputs"]["clarification_candidate_count"] == 6
    assert summary["outputs"]["blocking_clarification_candidate_count"] == 5
    assert summary["outputs"]["critical_clarification_candidate_count"] == 4
    assert summary["outputs"]["customer_safe_clarification_candidate_count"] == 6
    assert summary["outputs"]["urgent_clarification_candidate_count"] == 2
    assert summary["outputs"]["high_clarification_candidate_count"] == 3
    assert summary["outputs"]["top_clarification_candidate_ids"] == ["clarification_a", "clarification_b"]
    assert summary["outputs"]["top_clarification_groups_by_trade"][0]["key"] == "electrical"
    assert summary["outputs"]["top_clarification_groups_by_source_code"][0]["key"] == "missing_quantity"
    assert summary["outputs"]["clarification_customer_message_ready"] is False
    assert summary["outputs"]["clarification_send_ready"] is False
    review_package = summary["outputs"]["automation_review_package"]
    assert review_package["status"] == "blocked_before_customer_delivery"
    assert review_package["customer_delivery_ready"] is False
    assert review_package["blocked"]["readiness_blocker_count"] == 0
    assert review_package["blocked"]["pricing_not_ready_scope_item_count"] == 3
    assert review_package["blocked"]["formula_check_blocked_count"] == 3
    assert review_package["blocked"]["quantity_missing_count"] == 1
    assert review_package["human_review_needed"]["table_schedule_extraction_candidate_count"] == 1
    assert review_package["human_review_needed"]["quantity_extraction_candidate_count"] == 1
    assert review_package["top_followups"]["quantity_extraction_candidates"][0]["quantity_candidate_text"] == "12 fixtures"


def test_sheet_source_summary_flags_low_information_text_layers():
    from scripts import real_document_harness

    stage = {
        "ok": True,
        "body": {
            "items": [
                {
                    "detected_sheet_title": "DSA IDENTIFICATION STAMP",
                    "detection_confidence": 1.0,
                    "requires_ocr": False,
                    "requires_review": True,
                    "processing_status": "complete",
                    "text_char_count": 262,
                    "text_layer_quality": "low_information_text_layer",
                    "recommended_extraction_routes": ["ocr", "vision", "table_schedule_extraction"],
                },
                {
                    "detected_sheet_title": "ISSUE DATE",
                    "detection_confidence": 1.0,
                    "requires_ocr": False,
                    "requires_review": True,
                    "processing_status": "complete",
                    "text_char_count": 30,
                    "text_layer_quality": "very_low_information_text_layer",
                    "recommended_extraction_routes": ["ocr", "vision", "table_schedule_extraction"],
                },
                {
                    "detected_sheet_title": "STRUCTURAL SITE PLAN",
                    "detection_confidence": 0.91,
                    "requires_ocr": False,
                    "requires_review": False,
                    "processing_status": "complete",
                    "text_char_count": 900,
                    "text_layer_quality": "usable_text_layer",
                    "recommended_extraction_routes": ["text_extraction"],
                },
            ]
        },
    }

    summary = real_document_harness._sheet_source_summary(stage)

    assert summary["sheet_low_information_text_layer_count"] == 2
    assert summary["sheet_very_low_information_text_layer_count"] == 1
    assert summary["sheet_text_detail_missing_count"] == 0
    assert summary["sheet_text_layer_quality_counts"] == {
        "low_information_text_layer": 1,
        "usable_text_layer": 1,
        "very_low_information_text_layer": 1,
    }
    assert summary["sheet_recommended_extraction_route_counts"] == {
        "ocr": 2,
        "table_schedule_extraction": 2,
        "text_extraction": 1,
        "vision": 2,
    }
    assert summary["table_schedule_extraction_candidate_count"] == 2
    assert summary["table_schedule_extraction_candidate_quality_counts"] == {
        "low_information_text_layer": 1,
        "very_low_information_text_layer": 1,
    }
    assert [item["pdf_page_number"] for item in summary["table_schedule_extraction_candidates"]] == [None, None]
    assert summary["table_schedule_extraction_candidates"][0]["candidate_reasons"] == ["recommended_route"]
    assert summary["table_schedule_extraction_candidates"][0]["requires_human_review"] is True
    assert summary["table_schedule_extraction_candidates"][0]["final_quantity_extraction"] is False
    assert summary["sheet_text_char_count_min"] == 30
    assert summary["sheet_text_char_count_avg"] == 397.33
    assert summary["sheet_text_char_count_max"] == 900


def test_generic_formula_check_maps_supported_methods_and_blocks_unknown():
    from scripts import real_document_harness

    scope_stage = {
        "ok": True,
        "status_code": 200,
        "body": {
            "items": [
                # Supported unit-rate method, clear non-test quantity => ready.
                {
                    "id": "s1",
                    "trade_code": "painting",
                    "category_code": "generic_scope",
                    "quantity": "120",
                    "quantity_basis": "takeoff_or_schedule_count",
                    "raw_quantity_inputs": {"manual_takeoff_v1": {"source": "sheet A-1"}},
                    "trade_data": {"pricing_method": "unit_rate_needed"},
                },
                # Supported quote-based method but missing quantity => blocked.
                {
                    "id": "s2",
                    "trade_code": "painting",
                    "category_code": "generic_scope",
                    "trade_data": {"pricing_method": "quote_based"},
                },
                # Supported allowance method but unclear basis => blocked.
                {
                    "id": "s3",
                    "trade_code": "demo",
                    "category_code": "generic_scope",
                    "quantity": "1",
                    "quantity_basis": "unknown",
                    "trade_data": {"pricing_method": "allowance"},
                },
                # Unsupported pricing method must remain blocked even with a clean quantity.
                {
                    "id": "s4",
                    "trade_code": "demo",
                    "category_code": "generic_scope",
                    "quantity": "5",
                    "quantity_basis": "takeoff_or_schedule_count",
                    "raw_quantity_inputs": {"manual_takeoff_v1": {"source": "sheet D-1"}},
                    "trade_data": {"pricing_method": "cost_plus_experimental"},
                },
                # Generic scope with no pricing method assigned must remain blocked.
                {
                    "id": "s5",
                    "trade_code": "general_trade",
                    "category_code": "generic_scope",
                    "quantity": "5",
                    "quantity_basis": "takeoff_or_schedule_count",
                    "raw_quantity_inputs": {"manual_takeoff_v1": {"source": "sheet G-1"}},
                    "trade_data": {},
                },
            ]
        },
    }

    summary = real_document_harness._generic_formula_check_summary(scope_stage)

    assert summary["formula_check_scope_item_count"] == 5
    assert summary["formula_check_ready_count"] == 1
    assert summary["formula_check_blocked_count"] == 4
    assert summary["formula_check_ready_rate"] == 0.2
    assert summary["formula_check_method_counts"] == {
        "allowance": 1,
        "cost_plus_experimental": 1,
        "quote_based": 1,
        "unassigned": 1,
        "unit_rate_needed": 1,
    }
    assert summary["formula_check_blocker_counts"]["missing_quantity"] == 1
    assert summary["formula_check_blocker_counts"]["unclear_quantity_basis"] == 1
    assert summary["formula_check_blocker_counts"]["unsupported_pricing_method"] == 2

    checks = {
        check["scope_item_id"]: check
        for check in (real_document_harness._generic_formula_check_for_item(item) for item in scope_stage["body"]["items"])
    }
    assert checks["s1"]["formula_check"] == "quantity_times_unit_rate_check"
    assert checks["s1"]["ready"] is True
    assert checks["s2"]["formula_check"] == "lump_sum_or_scope_quantity_check"
    assert checks["s2"]["blockers"] == ["missing_quantity"]
    assert checks["s3"]["formula_check"] == "allowance_basis_check"
    assert checks["s3"]["blockers"] == ["unclear_quantity_basis"]
    assert checks["s4"]["formula_check"] == "unsupported"
    assert checks["s4"]["blockers"] == ["unsupported_pricing_method"]
    assert checks["s5"]["formula_check"] == "unsupported"
    assert checks["s5"]["blockers"] == ["unsupported_pricing_method"]


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


class _PagingScopeItemsClient:
    """Fake client whose /scope-items endpoint paginates like the real API (limit<=200)."""

    def __init__(self, items, details=None):
        self._items = items
        self._details = details or {}

    def get(self, path):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(path)
        if "/scope-items/" in parsed.path and not parsed.path.endswith("/scope-items"):
            item_id = parsed.path.rsplit("/", 1)[-1]
            payload = self._details.get(item_id)
            return _FakeResponse(payload if payload is not None else {"detail": "not found"}, 200 if payload is not None else 404)

        query = parse_qs(parsed.query)
        limit = int(query.get("limit", ["50"])[0])
        offset = int(query.get("offset", ["0"])[0])
        page = self._items[offset:offset + limit]
        return _FakeResponse(
            {"items": page, "total": len(self._items), "limit": limit, "offset": offset}
        )


def test_get_all_scope_items_pages_past_200_item_limit():
    from scripts import real_document_harness

    # 201 items; only item 201 carries the trade/keyword/quantity we care about.
    items = [
        {"id": f"scope-{i}", "trade_code": "general_trade", "description": "filler"}
        for i in range(200)
    ]
    items.append(
        {
            "id": "scope-201",
            "trade_code": "demo_concrete",
            "description": "Sidewalk concrete flatwork",
            "quantity": "1200",
            "unit": "SF",
        }
    )
    client = _PagingScopeItemsClient(items)

    stage = real_document_harness._get_all_scope_items(client, "/api/v1/projects/p1")

    fetched = stage["body"]["items"]
    assert len(fetched) == 201
    assert stage["body"]["fetched_item_count"] == 201
    tail = fetched[-1]
    assert tail["id"] == "scope-201"
    assert tail["trade_code"] == "demo_concrete"
    assert "concrete" in tail["description"].lower()
    assert tail["quantity"] == "1200"


def test_get_all_scope_items_with_details_adds_evidence_quotes():
    from scripts import real_document_harness

    items = [
        {"id": "scope-1", "trade_code": "electrical", "description": "summary"},
        {"id": "scope-2", "trade_code": "plumbing", "description": "summary"},
    ]
    details = {
        "scope-1": {
            "scope_item": {
                "id": "scope-1",
                "trade_code": "electrical",
                "description": "detailed electrical scope",
            },
            "trade_data": {"pricing_method": "unit_rate_needed"},
            "evidence": [
                {
                    "extracted_text_quote": "E-101 ELECTRICAL LIGHTING PLAN",
                    "requires_human_verification": True,
                }
            ],
        },
        "scope-2": {
            "scope_item": {
                "id": "scope-2",
                "trade_code": "plumbing",
                "description": "detailed plumbing scope",
            },
            "evidence": [],
        },
    }
    client = _PagingScopeItemsClient(items, details=details)

    stage = real_document_harness._get_all_scope_items_with_details(
        client,
        "/api/v1/projects/p1",
        quantity_inputs_by_scope={
            "scope-1": {
                "verified_quantity_input_v1": {
                    "source": "harness_test_only_quantity",
                },
            },
        },
    )
    hydrated = stage["body"]["items"]
    summary = real_document_harness._scope_evidence_quote_summary(stage)

    assert stage["body"]["detail_fetched_item_count"] == 2
    assert stage["body"]["detail_fetch_failure_count"] == 0
    assert hydrated[0]["description"] == "detailed electrical scope"
    assert hydrated[0]["trade_data"]["pricing_method"] == "unit_rate_needed"
    assert hydrated[0]["raw_quantity_inputs"]["verified_quantity_input_v1"]["source"] == "harness_test_only_quantity"
    assert hydrated[0]["evidence"][0]["extracted_text_quote"] == "E-101 ELECTRICAL LIGHTING PLAN"
    assert summary["scope_items_missing_evidence_quote_count"] == 1
    assert summary["evidence_quote_count"] == 1
    assert summary["evidence_human_verification_required_count"] == 1
    assert summary["evidence_quote_coverage_rate"] == 0.5
    assert summary["evidence_quote_by_trade"][0]["trade_code"] == "plumbing"
    assert summary["evidence_quote_by_trade"][0]["items_missing_evidence_quote_count"] == 1


def test_real_document_harness_main_returns_nonzero_when_stage_fails(tmp_path, monkeypatch):
    import sys

    from scripts import real_document_harness

    pdf = tmp_path / "input.pdf"
    output = tmp_path / "report.json"
    workdir = tmp_path / "work"
    pdf.write_bytes(b"%PDF-1.4\n%fake\n")

    def failed_harness(*args, **kwargs):
        return {
            "project_id": "project",
            "stages": {},
            "summary": {"failed_stage_count": 1},
        }

    monkeypatch.setattr(real_document_harness, "run_harness", failed_harness)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "real_document_harness.py",
            str(pdf),
            "--workdir",
            str(workdir),
            "--output",
            str(output),
        ],
    )

    assert real_document_harness.main() == 1
    assert output.exists()
    assert json.loads(output.read_text())["summary"]["failed_stage_count"] == 1
