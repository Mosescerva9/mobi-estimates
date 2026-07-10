"""Truthful capability registry + final delivery lock tests (audit P0-1)."""

from __future__ import annotations

from app import capability_registry as cr


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
    for source in ("test_verified_quantity", "TEST-pricing", "sample_takeoff", "mock", None, ""):
        assert cr.is_test_only_source(source) is True, source
    for source in ("staff_verified_takeoff", "verified_internal_unit_rate", "supplier_quote_2026"):
        assert cr.is_test_only_source(source) is False, source


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
        owner_approval={"approved": True},
        delivery_sources=[{"scope_item_id": "s1", "kind": "quantity_input", "source": "test_seed"}],
        required_capabilities=("scope_coverage",),
    )
    assert lock["requirements"]["capabilities_delivery_grade"] is True
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["delivery_unlocked"] is False
    assert lock["source_check"]["test_only_source_count"] == 1


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
        owner_approval={"approved": True},
        delivery_sources=[{"scope_item_id": "s1", "kind": "pricing_basis", "source": "supplier_quote_2026"}],
        required_capabilities=("scope_coverage",),
    )
    assert lock["delivery_unlocked"] is True
    assert lock["state"] == "unlocked"
    assert lock["reasons"] == []


def test_delivery_lock_requires_at_least_one_real_source():
    # No sources at all -> cannot affirmatively prove real evidence -> stays closed.
    lock = cr.evaluate_delivery_lock(
        evidence_complete=True,
        required_reviews_complete=True,
        owner_approval={"approved": True},
        delivery_sources=[],
    )
    assert lock["requirements"]["no_test_only_delivery_evidence"] is False
    assert lock["delivery_unlocked"] is False
