"""Truthful capability registry + final delivery lock tests (audit P0-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

from app import capability_registry as cr


PROJECT_ID = "project-delivery-lock"
OWNER_APPROVAL = {
    "approved": True,
    "approved_by": "moses",
    "approved_at": "2026-07-10T00:00:00Z",
    "approval_scope": "final_customer_delivery",
    "approval_project_id": PROJECT_ID,
}


def _delivery_ready_fixture_kwargs() -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "owner_approval": OWNER_APPROVAL,
        "delivery_sources": [
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        "unsupported_scope": {
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        "expected_scope_item_count": 1,
        "expected_scope_item_ids": ["s1"],
        "required_capabilities": ("scope_coverage",),
    }


def test_registry_labels_are_truthful_and_not_delivery_grade():
    registry = cr.get_capability_registry()
    assert registry["all_required_delivery_grade"] is False
    for name, entry in registry["capabilities"].items():
        assert entry["stage"] in cr.CAPABILITY_STAGES, name
        assert entry["delivery_grade"] == cr.is_delivery_grade(entry["stage"]), name
        # Nothing in this internal engine is production/accuracy-validated yet.
        assert entry["delivery_grade"] is False, name


def test_is_delivery_grade_only_for_production_verified_and_validated():
    assert cr.is_delivery_grade("production_verified") is True
    assert cr.is_delivery_grade("accuracy_validated") is True
    for stage in ("planned", "source", "source_implemented", "staging", "staging_verified", "production", None, "bogus"):
        assert cr.is_delivery_grade(stage) is False


def test_complete_delivery_evidence_requires_source_and_document_coordinates():
    valid = {
        "source_artifact_ref": "customer_plan_sha256_2026",
        "verified_sheet_number": "E-101",
        "pdf_page_number": 1,
        "evidence_type": "plan_note",
    }
    assert cr.is_complete_delivery_evidence_row(valid) is True

    for invalid in (
        {**valid, "source_artifact_ref": ""},
        {**valid, "source_artifact_ref": "test_fixture_plan"},
        {**valid, "source": "test_fixture_quantity"},
        {**valid, "source": ""},
        {**valid, "verified_sheet_number": ""},
        {**valid, "pdf_page_number": 0},
        {**valid, "pdf_page_number": True},
        {**valid, "evidence_type": ""},
        {"metadata": {"reviewed": True}},
        {**valid, "metadata": {"test_only": "true"}},
        [],
    ):
        assert cr.is_complete_delivery_evidence_row(invalid) is False, invalid


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
        "qa_verified_quantity",
        "uatSupplierQuote",
        "staging_pricing_basis",
        "preprod-takeoff",
        "preproductionPricingBasis",
        "testfixturequantity",
        "mockestimateprice",
        "seedquantitysource",
        "evalpricingsource",
        "demodataquantity",
        "reviewedtestplan",
        "clienttestdata",
        "supplierquotetest2026",
        "staffverifieddemotakeoff",
        "verifiedseedquantity",
        "batcheval99",
        "postevalreview",
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
    assert classification["supported_scope_items"] == [
        {"scope_item_id": "scope-ok", "trade_code": "electrical", "category_code": "generic_scope"}
    ]


def test_supported_scope_rejects_duplicate_scope_item_ids(monkeypatch):
    monkeypatch.setattr(cr, "SUPPORTED_CUSTOMER_DELIVERY_TRADES", frozenset({"electrical"}))
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    classification = cr.classify_supported_scope([
        {"id": "scope-dup", "trade_code": "electrical", "category_code": "generic_scope"},
        {"id": "scope-dup", "trade_code": "electrical", "category_code": "generic_scope"},
    ])

    assert classification["supported_scope"] is False
    assert classification["supported_scope_item_count"] == 1
    assert classification["unsupported_scope_item_count"] == 1
    assert classification["unsupported_scope_items"] == [
        {
            "scope_item_id": "scope-dup",
            "trade_code": "electrical",
            "category_code": "generic_scope",
            "reason": "Scope item ID is duplicated; supported delivery scope cannot be verified.",
        }
    ]

    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "scope-dup", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "scope-dup", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        unsupported_scope=classification,
        expected_scope_item_count=1,
        expected_scope_item_ids=["scope-dup"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False

def test_delivery_lock_blocks_duplicate_supported_scope_rows_even_when_counts_claim_ready(monkeypatch):
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "expected-scope", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "expected-scope", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "expected-scope", "trade_code": "electrical", "category_code": "generic_scope"},
                {"scope_item_id": "expected-scope", "trade_code": "electrical", "category_code": "generic_scope"},
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["expected-scope"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_malformed_expected_scope_id_container(monkeypatch):
    """A string/dict of expected IDs must not be treated as an iterable of IDs."""
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids="s",  # type: ignore[arg-type]
        required_capabilities=("scope_coverage",),
    )

    assert lock["expected_scope_item_ids_container_valid"] is False
    assert lock["expected_scope_item_ids_valid"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert "Expected scope item IDs collection is malformed" in "; ".join(lock["reasons"])
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_rejects_unordered_expected_scope_id_containers(monkeypatch):
    """set/frozenset can hide duplicate lineage before the lock can audit it."""
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    base_kwargs = _delivery_ready_fixture_kwargs()
    for unordered_expected_scope_item_ids in (
        cast(Any, {"s1"}),
        cast(Any, frozenset({"s1"})),
    ):
        lock = cr.evaluate_delivery_lock(
            evidence_complete=True,
            required_reviews_complete=True,
            **{
                **base_kwargs,
                "expected_scope_item_ids": unordered_expected_scope_item_ids,
            },
        )

        assert lock["expected_scope_item_ids_container_valid"] is False
        assert lock["expected_scope_item_ids_valid"] is False
        assert lock["requirements"]["source_scope_coverage_complete"] is False
        assert "Expected scope item IDs collection is malformed" in "; ".join(lock["reasons"])
        assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_mismatched_supported_scope_ids(monkeypatch):
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "expected-scope", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "expected-scope", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "other-scope", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["expected-scope"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False


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


def test_owner_approval_requires_authorized_owner_scope_and_auditable_timestamp():
    future_timestamp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    cases = (
        (
            {
                "approved": True,
                "approved_by": "staff reviewer",
                "approved_at": "2026-07-10T00:00:00Z",
                "approval_scope": "final_customer_delivery",
            },
            "approved_by:authorized_owner",
        ),
        (
            {
                "approved": True,
                "approved_by": "moses",
                "approved_at": "2026-07-10",
                "approval_scope": "final_customer_delivery",
            },
            "approved_at:valid_iso8601_timezone",
        ),
        (
            {
                "approved": True,
                "approved_by": "moses",
                "approved_at": future_timestamp,
                "approval_scope": "final_customer_delivery",
            },
            "approved_at:not_future",
        ),
        (
            {
                "approved": True,
                "approved_by": "moses",
                "approved_at": "2026-07-10T00:00:00Z",
                "approval_scope": "internal_review",
            },
            "approval_scope:final_customer_delivery",
        ),
        (
            {
                "approved": "true",
                "approved_by": "moses",
                "approved_at": "2026-07-10T00:00:00Z",
                "approval_scope": "final_customer_delivery",
            },
            "approved",
        ),
        (
            {
                "approved": True,
                "approved_by": True,
                "approved_at": "2026-07-10T00:00:00Z",
                "approval_scope": "final_customer_delivery",
            },
            "approved_by",
        ),
    )

    for approval, missing_marker in cases:
        result = cr.classify_owner_approval(approval)  # type: ignore[arg-type]
        assert result["valid"] is False
        assert missing_marker in result["missing_fields"]

    missing_project = cr.classify_owner_approval({
        "approved": True,
        "approved_by": "Moses Cervantes",
        "approved_at": "2026-07-10T00:00:00Z",
        "approval_scope": "final_customer_delivery",
    }, expected_project_id=PROJECT_ID)
    assert missing_project["valid"] is False
    assert "approval_project_id" in missing_project["missing_fields"]
    assert missing_project["project_binding_verified"] is False

    mismatched_project = cr.classify_owner_approval(
        {
            "approved": True,
            "approved_by": "Moses Cervantes",
            "approved_at": "2026-07-10T00:00:00Z",
            "approval_scope": "final_customer_delivery",
            "approval_project_id": "other-project",
        },
        expected_project_id=PROJECT_ID,
    )
    assert mismatched_project["valid"] is False
    assert "approval_project_id:project_match" in mismatched_project["missing_fields"]

    valid = cr.classify_owner_approval({
        "approved": True,
        "approved_by": "Moses Cervantes",
        "approved_at": "2026-07-10T00:00:00Z",
        "approval_scope": "final_customer_delivery",
        "approval_project_id": PROJECT_ID,
    }, expected_project_id=PROJECT_ID)
    assert valid["valid"] is True
    assert valid["approved_by_authorized"] is True
    assert valid["approval_timestamp_valid"] is True
    assert valid["project_binding_verified"] is True


def test_delivery_lock_requires_literal_true_evidence_and_review_flags(monkeypatch):
    """Truthy status labels must not satisfy final-delivery audit gates."""
    monkeypatch.setattr(cr, "SUPPORTED_CUSTOMER_DELIVERY_TRADES", frozenset({"electrical"}))
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )

    base_kwargs = _delivery_ready_fixture_kwargs()
    unlocked = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        **base_kwargs,
    )
    assert unlocked["delivery_unlocked"] is True

    for field, value in (
        ("evidence_complete", "true"),
        ("evidence_complete", 1),
        ("evidence_complete", {"complete": True}),
        ("required_reviews_complete", "complete"),
        ("required_reviews_complete", 1),
        ("required_reviews_complete", ["owner_review"]),
    ):
        kwargs = {
            "evidence_complete": True,
            "required_reviews_complete": True,
            **base_kwargs,
        }
        kwargs[field] = value
        lock = cr.evaluate_delivery_lock(**kwargs)
        assert lock["requirements"][field] is False, field
        assert lock["delivery_unlocked"] is False, field


def test_delivery_lock_blocks_test_only_source_metadata_even_with_real_source_name(monkeypatch):
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {
                "scope_item_id": "s1",
                "kind": "quantity_input",
                "source": "staff_verified_takeoff",
                "internal_testing_only": True,
            },
            {
                "scope_item_id": "s1",
                "kind": "pricing_basis",
                "source": "supplier_quote_2026",
                "is_test_only": True,
            },
            {
                "scope_item_id": "s1",
                "kind": "cost_component_source",
                "source": "supplier_component_quote_2026",
                "is_testing_only": True,
            },
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 3
    for row in lock["source_check"]["test_only_sources"]:
        assert row["reason"] == "Source metadata marks this row as test-only scaffolding."
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_nested_test_only_source_metadata(monkeypatch):
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {
                "scope_item_id": "s1",
                "kind": "quantity_input",
                "source": "staff_verified_takeoff",
                "metadata": {"provenance_metadata": {"synthetic_only": True}},
            },
            {
                "scope_item_id": "s1",
                "kind": "quantity_input",
                "source": "staff_verified_takeoff_2",
                "metadata": {"source_metadata": {"internal_testing_only": True}},
            },
            {
                "scope_item_id": "s1",
                "kind": "pricing_basis",
                "source": "supplier_quote_2026",
                "source_metadata": {"audit_metadata": {"fixture_only": True}},
            },
            {
                "scope_item_id": "s1",
                "kind": "cost_component_source",
                "source": "supplier_quote_2026_alt",
                "metadata": [{"provenance_metadata": {"test_only": True}}],
            },
            {
                "scope_item_id": "s1",
                "kind": "quantity_input",
                "source": "staff_verified_takeoff_3",
                "metadata": {"test_only": "true"},
            },
            {
                "scope_item_id": "s1",
                "kind": "pricing_basis",
                "source": "supplier_quote_2026_third",
                "source_metadata": {"internal_testing_only": 1},
            },
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 6
    assert {row["source"] for row in lock["source_check"]["test_only_sources"]} == {
        "staff_verified_takeoff",
        "staff_verified_takeoff_2",
        "staff_verified_takeoff_3",
        "supplier_quote_2026",
        "supplier_quote_2026_alt",
        "supplier_quote_2026_third",
    }
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_over_deep_metadata_as_unverifiable(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    quantity_source: dict[str, Any] = {
        "scope_item_id": "s1",
        "kind": "quantity_input",
        "source": "staff_verified_takeoff",
    }
    cursor = quantity_source
    for _ in range(9):
        cursor["metadata"] = {}
        cursor = cast(dict[str, Any], cursor["metadata"])
    cursor["synthetic_only"] = True

    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            quantity_source,
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 1
    assert lock["source_check"]["real_source_scope_item_ids_by_kind"] == {"quantity": [], "pricing": ["s1"]}
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_cyclic_metadata_as_unverifiable(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    quantity_source: dict[str, Any] = {
        "scope_item_id": "s1",
        "kind": "quantity_input",
        "source": "staff_verified_takeoff",
    }
    quantity_source["metadata"] = quantity_source

    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            quantity_source,
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}
            ],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["source_check"]["test_only_source_count"] == 1
    assert lock["source_check"]["real_source_scope_item_ids_by_kind"] == {"quantity": [], "pricing": ["s1"]}
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False


def test_delivery_source_classifier_blocks_unknown_nested_metadata_shapes():
    nested_flag = {
        "scope_item_id": "s1",
        "kind": "quantity_input",
        "source": "staff_verified_takeoff",
        "metadata": {"other": {"synthetic_only": True}},
    }
    cyclic_metadata: dict[str, Any] = {}
    cyclic_metadata["other"] = cyclic_metadata
    cyclic = {
        "scope_item_id": "s2",
        "kind": "quantity_input",
        "source": "staff_verified_takeoff",
        "metadata": cyclic_metadata,
    }
    over_deep_metadata: dict[str, Any] = {}
    cursor = over_deep_metadata
    for _ in range(20):
        cursor["other"] = {}
        cursor = cast(dict[str, Any], cursor["other"])
    over_deep = {
        "scope_item_id": "s3",
        "kind": "pricing_basis",
        "source": "supplier_quote_2026",
        "metadata": over_deep_metadata,
    }

    classification = cr.classify_delivery_sources([nested_flag, cyclic, over_deep])

    assert classification["test_only_source_count"] == 3
    assert classification["no_test_only_delivery_evidence"] is False
    assert classification["real_source_scope_item_ids"] == []


def test_delivery_source_row_builder_preserves_unknown_nested_metadata_shapes():
    """The canonical row builder must not strip hidden fixture/synthetic flags."""
    nested_flag = cr.build_delivery_source_row(
        scope_item_id="s1",
        kind="quantity_input",
        source="staff_verified_takeoff",
        metadata={"provenance": {"synthetic_only": True}},
    )
    cyclic_metadata: dict[str, Any] = {}
    cyclic_metadata["provenance"] = cyclic_metadata
    cyclic = cr.build_delivery_source_row(
        scope_item_id="s2",
        kind="quantity_input",
        source="staff_verified_takeoff",
        metadata=cyclic_metadata,
    )
    over_deep_metadata: dict[str, Any] = {}
    cursor = over_deep_metadata
    for _ in range(20):
        cursor["takeoff_metadata"] = {}
        cursor = cast(dict[str, Any], cursor["takeoff_metadata"])
    over_deep = cr.build_delivery_source_row(
        scope_item_id="s3",
        kind="pricing_basis",
        source="supplier_quote_2026",
        metadata=over_deep_metadata,
    )

    classification = cr.classify_delivery_sources([nested_flag, cyclic, over_deep])

    assert classification["test_only_source_count"] == 3
    assert classification["no_test_only_delivery_evidence"] is False
    assert classification["real_source_scope_item_ids"] == []


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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval={"approved": True},
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        project_id=PROJECT_ID,
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
        "approval_project_id",
    }


def test_delivery_lock_blocks_non_string_owner_approval_metadata(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
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
        "approval_project_id",
    }
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_non_owner_final_delivery_approval(monkeypatch):
    """A staff/reviewer approval cannot satisfy Moses' owner-only delivery gate."""
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    reviewer_approval = {
        **OWNER_APPROVAL,
        "approved_by": "senior_estimator",
    }
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=reviewer_approval,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["owner_approval_present"] is False
    assert lock["owner_approval_check"]["approved_by_present"] is True
    assert lock["owner_approval_check"]["approved_by_authorized"] is False
    assert "approved_by:authorized_owner" in lock["owner_approval_check"]["missing_fields"]
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_malformed_owner_approval_timestamp(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
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
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
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


def test_delivery_lock_blocks_claimed_support_for_unvalidated_trade(monkeypatch):
    """A caller-supplied classification cannot claim an unvalidated trade lane.

    ``unsupported_scope`` arrives from upstream surfaces. If the lock trusted its
    verdict, a stale or forged classification could unlock final delivery for a
    trade that never passed accuracy validation.
    """
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    monkeypatch.setattr(cr, "SUPPORTED_CUSTOMER_DELIVERY_TRADES", frozenset({"electrical"}))

    for forged_trade_code in ("plumbing", "", None, 260000, " electrical "[:-1] + "x"):
        base_kwargs = _delivery_ready_fixture_kwargs()
        base_kwargs["unsupported_scope"]["supported_scope_items"] = [
            {"scope_item_id": "s1", "trade_code": forged_trade_code, "category_code": "generic_scope"}
        ]
        lock = cr.evaluate_delivery_lock(
            evidence_complete=True,
            required_reviews_complete=True,
            **base_kwargs,
        )

        assert lock["unsupported_trade_scope_item_ids"] == ["s1"], forged_trade_code
        assert lock["requirements"]["supported_scope"] is False, forged_trade_code
        assert lock["delivery_unlocked"] is False, forged_trade_code
        assert (
            "Claimed supported scope items include a trade that is not accuracy-validated"
            in "; ".join(lock["reasons"])
        ), forged_trade_code


def test_delivery_lock_unlocks_only_when_every_requirement_is_met(monkeypatch):
    monkeypatch.setattr(cr, "SUPPORTED_CUSTOMER_DELIVERY_TRADES", frozenset({"electrical"}))
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["delivery_unlocked"] is True
    assert lock["state"] == "unlocked"
    assert lock["reasons"] == []


def test_delivery_lock_blocks_unknown_required_source_kind(monkeypatch):
    """A caller typo/future source-kind requirement cannot be silently ignored."""
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
        required_source_kinds=("quantity", "pricing", "signed_reviewer_measurement"),
    )

    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["required_source_kinds"] == ["quantity", "pricing"]
    assert lock["unknown_required_source_kinds"] == ["signed_reviewer_measurement"]
    assert lock["delivery_unlocked"] is False
    assert any("Required source-kind requirements are unknown" in reason for reason in lock["reasons"])


def test_delivery_lock_blocks_malformed_required_source_kind_container(monkeypatch):
    """Malformed caller requirement containers must fail closed instead of crashing."""
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
        required_source_kinds=cast(Any, {"quantity", "pricing"}),
    )

    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["required_source_kinds"] == ["quantity", "pricing"]
    assert lock["unknown_required_source_kinds"] == [cr._MALFORMED_REQUIRED_SOURCE_KINDS]
    assert lock["delivery_unlocked"] is False
    assert any("Required source-kind requirements are unknown" in reason for reason in lock["reasons"])


def test_delivery_lock_blocks_malformed_required_capability_container(monkeypatch):
    """Malformed capability requirements must not bypass the truthful registry."""
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=cast(Any, {"scope_coverage"}),
    )

    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["capabilities_delivery_grade"] is False
    assert cr._MALFORMED_REQUIRED_CAPABILITIES in lock["required_capabilities"]
    assert any(gap["capability"] == cr._MALFORMED_REQUIRED_CAPABILITIES for gap in lock["capability_gaps"])
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_blocks_malformed_expected_scope_count(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=cast("int", True),
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["expected_scope_item_count_valid"] is False
    assert lock["requirements"]["supported_scope"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False
    assert any("Expected scope item count is malformed" in reason for reason in lock["reasons"])


def test_delivery_lock_blocks_malformed_expected_scope_ids_even_when_sources_match(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1", None],
        required_capabilities=("scope_coverage",),
    )

    assert lock["expected_scope_item_ids"] == ["s1"]
    assert lock["expected_scope_item_ids_valid"] is False
    assert lock["malformed_expected_scope_item_ids"] == [None]
    assert lock["requirements"]["supported_scope"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False
    assert any("Expected scope item IDs are missing, malformed, or duplicated" in reason for reason in lock["reasons"])


def test_delivery_lock_blocks_duplicate_expected_scope_ids_even_when_sources_match(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        expected_scope_item_ids=["s1", " s1 "],
        required_capabilities=("scope_coverage",),
    )

    assert lock["expected_scope_item_ids"] == ["s1"]
    assert lock["expected_scope_item_ids_valid"] is False
    assert lock["duplicate_expected_scope_item_ids"] == ["s1"]
    assert lock["requirements"]["supported_scope"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False
    assert any("Expected scope item IDs are missing, malformed, or duplicated" in reason for reason in lock["reasons"])


def test_delivery_lock_requires_supported_scope_classification_even_if_flag_is_true(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "production_verified", "summary": "x"}},
    )
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        unsupported_scope=None,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False
    assert any("not in an accuracy-validated supported" in reason for reason in lock["reasons"])


def test_delivery_lock_requires_at_least_one_real_source():
    # No sources at all -> cannot affirmatively prove real evidence -> stays closed.
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval=OWNER_APPROVAL,
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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


def test_delivery_lock_does_not_coerce_missing_expected_scope_ids_to_none_string(monkeypatch):
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "None", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "None", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        expected_scope_item_count=1,
        expected_scope_item_ids=[None],
        required_capabilities=("scope_coverage",),
    )
    assert lock["expected_scope_item_ids"] == []
    assert lock["extra_source_scope_item_ids"] == []
    assert lock["source_check"]["real_source_scope_item_ids"] == []
    assert lock["source_check"]["unscoped_source_count"] == 2
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["requirements"]["source_scope_coverage_complete"] is False
    assert lock["requirements"]["source_kind_coverage_complete"] is False
    assert lock["delivery_unlocked"] is False


def test_delivery_lock_rejects_string_sentinel_scope_ids_even_when_sources_match(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    for sentinel in ("None", " null ", "UNDEFINED", "NaN"):
        lock = cr.evaluate_delivery_lock(
            evidence_complete=True,
            required_reviews_complete=True,
            owner_approval=OWNER_APPROVAL,
            delivery_sources=[
                {"scope_item_id": sentinel, "kind": "quantity_input", "source": "staff_verified_takeoff"},
                {"scope_item_id": sentinel, "kind": "pricing_basis", "source": "supplier_quote_2026"},
            ],
            supported_scope=True,
            expected_scope_item_count=1,
            expected_scope_item_ids=[sentinel],
            required_capabilities=("scope_coverage",),
        )
        assert lock["expected_scope_item_ids"] == []
        assert lock["source_check"]["real_source_scope_item_ids"] == []
        assert lock["source_check"]["unscoped_source_count"] == 2
        assert lock["requirements"]["no_test_only_delivery_evidence"] is False
        assert lock["requirements"]["source_scope_coverage_complete"] is False
        assert lock["requirements"]["source_kind_coverage_complete"] is False
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
        project_id=PROJECT_ID,
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
    monkeypatch.setattr(cr, "SUPPORTED_CUSTOMER_DELIVERY_TRADES", frozenset({"electrical"}))
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s2", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            {"scope_item_id": "s2", "kind": "quantity_input", "source": "staff_verified_takeoff"},
        ],
        supported_scope=True,
        unsupported_scope={
            "supported_scope": True,
            "evaluated_scope_item_count": 2,
            "supported_scope_item_count": 2,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [
                {"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"},
                {"scope_item_id": "s2", "trade_code": "electrical", "category_code": "generic_scope"},
            ],
            "unsupported_scope_items": [],
        },
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
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
        project_id=PROJECT_ID,
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        supported_scope=unsupported["supported_scope"],
        unsupported_scope=unsupported,
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["capabilities_delivery_grade"] is True
    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False
    assert lock["unsupported_scope"]["unsupported_scope_item_count"] == 1


def test_delivery_lock_ignores_supported_scope_flag_when_classification_contradicts_it(monkeypatch):
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
        project_id=PROJECT_ID,
        delivery_sources=[
            {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
            {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
        ],
        supported_scope=True,
        unsupported_scope=unsupported,
        expected_scope_item_count=1,
        expected_scope_item_ids=["s1"],
        required_capabilities=("scope_coverage",),
    )

    assert lock["requirements"]["capabilities_delivery_grade"] is True
    assert lock["requirements"]["no_test_only_delivery_evidence"] is True
    assert lock["requirements"]["source_scope_coverage_complete"] is True
    assert lock["requirements"]["source_kind_coverage_complete"] is True
    assert lock["requirements"]["owner_approval_present"] is True
    assert lock["requirements"]["supported_scope"] is False
    assert lock["delivery_unlocked"] is False
    assert any("not in an accuracy-validated supported" in reason for reason in lock["reasons"])


def test_delivery_lock_requires_affirmative_nonempty_supported_scope_classification(monkeypatch):
    monkeypatch.setattr(cr, "REQUIRED_DELIVERY_CAPABILITIES", ("scope_coverage",))
    monkeypatch.setattr(
        cr,
        "CAPABILITY_REGISTRY",
        {"scope_coverage": {"stage": "accuracy_validated", "summary": "x"}},
    )
    empty_or_malformed_classifications = [
        {"supported_scope": True, "unsupported_scope_item_count": 0, "unsupported_scope_items": []},
        {
            "supported_scope": True,
            "evaluated_scope_item_count": 0,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        {
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 0,
            "supported_scope_items": [{"scope_item_id": "s1", "trade_code": "electrical", "category_code": "generic_scope"}],
            "unsupported_scope_items": [],
        },
        {
            "supported_scope": True,
            "evaluated_scope_item_count": 1,
            "supported_scope_item_count": 1,
            "unsupported_scope_item_count": 0,
            "malformed_scope_collection_count": 1,
            "unsupported_scope_items": [],
        },
        ["not", "a", "classification"],
    ]

    for classification in empty_or_malformed_classifications:
        lock = cr.evaluate_delivery_lock(
            evidence_complete=True,
            required_reviews_complete=True,
            owner_approval=OWNER_APPROVAL,
            delivery_sources=[
                {"scope_item_id": "s1", "kind": "quantity_input", "source": "staff_verified_takeoff"},
                {"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"},
            ],
            supported_scope=True,
            unsupported_scope=cast("dict[str, Any]", classification),
            expected_scope_item_count=2,
            expected_scope_item_ids=["s1", "s2"],
            required_capabilities=("scope_coverage",),
        )

        assert lock["requirements"]["supported_scope"] is False
        assert lock["delivery_unlocked"] is False
