"""Truthful capability registry + final delivery lock tests (audit P0-1)."""

from __future__ import annotations

from typing import Any, cast

from app import capability_registry as cr


OWNER_APPROVAL = {
    "approved": True,
    "approved_by": "moses",
    "approved_at": "2026-07-10T00:00:00Z",
    "approval_scope": "final_customer_delivery",
}


def test_registry_labels_are_truthful_and_not_delivery_grade():
    registry = cr.get_capability_registry()
    assert registry["all_required_delivery_grade"] is False
    for name, entry in registry["capabilities"].items():
        assert entry["stage"] in cr.CAPABILITY_STAGES, name
        assert entry["delivery_grade"] == cr.is_delivery_grade(entry["stage"]), name
        # Nothing in this internal engine is production/accuracy-validated yet.
        assert entry["delivery_grade"] is False, name


def test_is_delivery_grade_only_for_production_and_validated():
    assert cr.is_delivery_grade("production") is True
    assert cr.is_delivery_grade("accuracy_validated") is True
    for stage in ("planned", "source", "staging", None, "bogus"):
        assert cr.is_delivery_grade(stage) is False


def test_test_only_source_detection():
    for source in (
        "test_verified_quantity",
        "TEST-pricing",
        "sample_takeoff",
        "mock",
        "golden_set_v2_harness",
        "benchmark_generated_quantity",
        "autoresearch_eval_output",
        "testVerifiedQuantity",
        "harnessTestOnlyPricing",
        "benchmarkGeneratedQuantity",
        "syntheticDemoPricing",
        "testfixturequantity",
        "mockestimateprice",
        "demodataquantity",
        None,
        "",
        "   ",
        False,
        0,
        [],
        {"source": "supplier_quote"},
    ):
        assert cr.is_test_only_source(source) is True, source
    for source in (
        "staff_verified_takeoff",
        "verified_internal_unit_rate",
        "supplier_quote_2026",
        "latest_addendum_verified_quantity",
        "staff_verified_demolition_takeoff",
        "contest_won_supplier_quote",
    ):
        assert cr.is_test_only_source(source) is False, source


def test_supported_scope_requires_durable_id_and_valid_trade_even_for_supported_lane(monkeypatch):
    monkeypatch.setattr(cr, "SUPPORTED_CUSTOMER_DELIVERY_TRADES", frozenset({"electrical"}))
    classification = cr.classify_supported_scope([
        {"id": "scope-ok", "trade_code": "electrical", "category_code": "generic_scope"},
        {"id": None, "trade_code": "electrical", "category_code": "generic_scope"},
        {"id": "scope-no-trade", "trade_code": None, "category_code": "generic_scope"},
        {"id": "scope-numeric-trade", "trade_code": 260000, "category_code": "generic_scope"},
    ])

    assert classification["supported_scope"] is False
    assert classification["supported_scope_item_count"] == 1
    assert classification["unsupported_scope_item_count"] == 3
    reasons = {row["scope_item_id"]: row["reason"] for row in classification["unsupported_scope_items"]}
    assert reasons[None] == "Scope item is missing durable scope_item_id; supported delivery scope cannot be verified."
    assert reasons["scope-no-trade"] == "Scope item is missing a valid trade_code; supported delivery scope cannot be verified."
    assert reasons["scope-numeric-trade"] == "Scope item is missing a valid trade_code; supported delivery scope cannot be verified."


def test_delivery_lock_fail_closed_by_default():
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=None,
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote"}],
    )
    # Capabilities are not delivery-grade and owner approval is absent.
    assert lock["delivery_unlocked"] is False
    assert lock["fail_closed"] is True
    assert lock["requirements"]["capabilities_delivery_grade"] is False
    assert lock["requirements"]["owner_approval_present"] is False


def test_delivery_lock_blocks_test_only_sources_even_if_all_else_ready(monkeypatch):
    # Force every required capability to be delivery-grade for this scenario.
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[{"scope_item_id": "s1", "kind": "quantity_input", "source": "test_seed"}],
        supported_scope=True,
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["capabilities_delivery_grade"] is True
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["delivery_unlocked"] is False
    assert lock["source_check"]["test_only_source_count"] == 1


def test_delivery_lock_blocks_malformed_non_string_sources_even_if_all_else_ready(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "quantity_input", "source": False},
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": 0},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 2
    assert lock["source_check"]["real_source_scope_item_ids"] == []
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_malformed_source_collection_instead_of_erroring(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=cast("list[dict[str, Any]]", None),
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["malformed_source_collection_count"] == 1
    assert lock["source_check"]["test_only_sources"] == [
        {
            "scope_item_id": None,
            "kind": None,
            "source": None,
            "reason": "Source collection is malformed; provenance cannot be verified.",
        }
    ]


def test_delivery_lock_blocks_malformed_source_rows_instead_of_erroring(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    malformed_sources: list[Any] = [
        "staff_verified_takeoff",
        ["pricing_basis", "supplier_quote_2026"],
        {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
    ]
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=cast("list[dict[str, Any]]", malformed_sources),
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 2
    assert lock["source_check"]["test_only_sources"][0]["reason"] == "Source row is malformed; provenance cannot be verified."
    assert lock["source_check"]["test_only_sources"][1]["reason"] == "Source row is malformed; provenance cannot be verified."
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_camelcase_or_concatenated_test_only_sources(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "testVerifiedQuantity"},
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "harnessTestOnlyPricing"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 2
    assert lock["source_check"]["real_source_scope_item_ids"] == []
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_bare_boolean_owner_approval(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval={"approved": True},
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        supported_scope=True,
        required_capabilities=("scope_coverage",),
    )
    assert lock["delivery_unlocked"] is False
    assert lock["requirements"]["owner_approval_present"] is False
    assert lock["owner_approval_check"]["valid"] is False
    assert lock["owner_approval_check"]["approval_timestamp_valid"] is False
    assert set(lock["owner_approval_check"]["missing_fields"]) == {
        "approved_by",
        "approved_at",
        "approval_scope",
    }


def test_delivery_lock_blocks_non_string_owner_approval_metadata(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production", "summary": "x"}},
    )
    malformed_approval = {
        "approved": True,
        "approved_by": 12345,
        "approved_at": 1780000000,
        "approval_scope": ["final_customer_delivery"],
    }
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=malformed_approval,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["owner_approval_present"] is False
    assert lock["owner_approval_check"]["valid"] is False
    assert lock["owner_approval_check"]["approved_by_present"] is False
    assert lock["owner_approval_check"]["approved_at_present"] is False
    assert lock["owner_approval_check"]["approval_scope"] is None
    assert set(lock["owner_approval_check"]["missing_fields"]) == {
        "approved_by",
        "approved_at",
        "approval_scope",
    }
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_malformed_owner_approval_timestamp(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production", "summary": "x"}},
    )
    bad_approval = {
        **OWNER_APPROVAL,
        "approved_at": "2026-07-11 00:00:00",  # no timezone -> not auditable enough
    }
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=bad_approval,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["owner_approval_present"] is False
    assert lock["owner_approval_check"]["valid"] is False
    assert lock["owner_approval_check"]["approval_timestamp_valid"] is False
    assert "approved_at:valid_iso8601_timezone" in lock["owner_approval_check"]["missing_fields"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_future_owner_approval_timestamp(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production", "summary": "x"}},
    )
    future_approval = {
        **OWNER_APPROVAL,
        "approved_at": "2099-01-01T00:00:00Z",
    }
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=future_approval,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["owner_approval_present"] is False
    assert lock["owner_approval_check"]["valid"] is False
    assert lock["owner_approval_check"]["approval_timestamp_valid"] is True
    assert lock["owner_approval_check"]["approval_timestamp_not_future"] is False
    assert "approved_at:not_future" in lock["owner_approval_check"]["missing_fields"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_unlocks_only_when_every_requirement_is_met(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["delivery_unlocked"] is True
    assert lock["state"] == "unlocked"
    assert lock["reasons"] == []


def test_delivery_lock_requires_at_least_one_real_source():
    # No sources at all -> cannot affirmatively prove real evidence -> stays closed.
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[],
        supported_scope=True,
    )
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_requires_explicit_expected_scope_coverage(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        supported_scope=True,
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_incomplete_source_scope_coverage(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        supported_scope=True,
        expected_scope_item_count=2,
        expected_scope_item_ids=["s1", "s2"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["no_test_only_delivery_evidence"] is True
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["source_check"]["real_source_scope_item_count"] == 1
    assert lock["missing_source_scope_item_ids"] == ["s2"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_sources_for_wrong_scope_items(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "stale-extra", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        expected_scope_item_count=2,
        expected_scope_item_ids=["s1", "s2"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["missing_source_scope_item_ids"] == ["s2"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_extra_stale_real_source_ids(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s2", "kind": "pricing_basis", "source": "staff_verified_takeoff"},
            {"scope_item_id": "stale-extra", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        expected_scope_item_count=2,
        expected_scope_item_ids=["s1", "s2"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["missing_source_scope_item_ids"] == []
    assert lock["extra_source_scope_item_ids"] == ["stale-extra"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_unscoped_real_looking_sources(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": None, "kind": "pricing_basis", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["all_delivery_sources_scoped"] is False
    assert lock["source_check"]["unscoped_source_count"] == 1
    assert lock["source_check"]["unscoped_sources"][0]["source"] == "staff_verified_takeoff"
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_treats_whitespace_scope_ids_as_unscoped(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "   ", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=[" s1 "],
        required_capabilities=("scope_coverage",),
    )
    assert lock["expected_scope_item_ids"] == ["s1"]
    assert lock["source_check"]["real_source_scope_item_ids"] == ["s1"]
    assert lock["source_check"]["unscoped_source_count"] == 1
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["missing_source_scope_item_ids_by_kind"] == {"quantity": ["s1"], "pricing": []}
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_unknown_source_kind_as_unverified_evidence(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "unknown_ai_summary", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["source_check"]["all_delivery_sources_supported_kind"] is False
    assert lock["source_check"]["unsupported_source_kind_count"] == 1
    assert lock["source_check"]["unsupported_kind_sources"] == [
        {
            "scope_item_id": "s1",
            "kind": "unknown_ai_summary",
            "source": "staff_verified_takeoff",
            "reason": "Source kind is not accepted as quantity or pricing delivery evidence.",
        }
    ]
    assert "unknown_ai_summary" not in lock["source_check"]["accepted_source_kinds"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_accepts_real_source_coverage_when_every_scope_item_has_source(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s2", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s2", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=2,
        expected_scope_item_ids=["s1", "s2"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["delivery_unlocked"] is True


def test_delivery_lock_cannot_weaken_required_quantity_pricing_sources(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_source_kinds=(),
        required_capabilities=("scope_coverage",),
    )
    assert lock["required_source_kinds"] == ["quantity", "pricing"]
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["missing_source_scope_item_ids_by_kind"] == {"quantity": ["s1"], "pricing": []}
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_scope_items_missing_real_quantity_or_pricing_kind(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s2", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        expected_scope_item_count=2,
        expected_scope_item_ids=["s1", "s2"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["missing_source_scope_item_ids_by_kind"] == {
        "quantity": ["s1"],
        "pricing": ["s2"],
    }
    assert lock["delivery_unlocked"] is False


def test_scope_classifier_abstains_when_trade_is_not_accuracy_validated():
    result = cr.classify_supported_scope([
        {"id": "s1", "trade_code": "electrical", "category_code": "generic_scope"},
        {"id": "s2", "trade_code": "painting", "category_code": "generic_scope"},
    ])
    assert result["supported_customer_delivery_trades"] == []
    assert result["supported_scope"] is False
    assert result["unsupported_scope_item_count"] == 2
    assert {row["scope_item_id"] for row in result["unsupported_scope_items"]} == {"s1", "s2"}


def test_scope_classifier_abstains_on_malformed_scope_collection():
    result = cr.classify_supported_scope(cast("list[dict[str, Any]]", None))
    assert result["supported_scope"] is False
    assert result["evaluated_scope_item_count"] == 0
    assert result["malformed_scope_collection_count"] == 1
    assert result["unsupported_scope_item_count"] == 1
    assert result["unsupported_scope_items"] == [
        {
            "scope_item_id": None,
            "trade_code": None,
            "category_code": None,
            "reason": "Scope item collection is malformed; supported delivery scope cannot be verified.",
        }
    ]


def test_scope_classifier_abstains_on_malformed_scope_rows():
    malformed_scope_items = [
        "electrical",
        ["painting", "s1"],
        {"id": "s2", "trade_code": "painting", "category_code": "generic_scope"},
    ]
    result = cr.classify_supported_scope(cast("list[dict[str, Any]]", malformed_scope_items))
    assert result["supported_scope"] is False
    assert result["evaluated_scope_item_count"] == 3
    assert result["unsupported_scope_item_count"] == 3
    assert result["unsupported_scope_items"][0] == {
        "scope_item_id": None,
        "trade_code": None,
        "category_code": None,
        "reason": "Scope item row is malformed; supported delivery scope cannot be verified.",
    }
    assert result["unsupported_scope_items"][1]["reason"] == (
        "Scope item row is malformed; supported delivery scope cannot be verified."
    )


def test_delivery_lock_blocks_unsupported_scope_even_if_all_else_ready(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    unsupported = cr.classify_supported_scope([
        {"id": "s1", "trade_code": "electrical", "category_code": "generic_scope"},
    ])
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        supported_scope=unsupported["supported_scope"],
        unsupported_scope=unsupported,
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["capabilities_delivery_grade"] is True
    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False
    assert lock["unsupported_scope"]["unsupported_scope_item_count"] == 1
