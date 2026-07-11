"""Truthful Capability Registry + Final Delivery Lock v1 (audit P0-1).

Every estimating capability is labeled with its *real* maturity stage so no
downstream gate can silently treat an in-progress capability as delivery-grade.
This module also owns the fail-closed final customer-delivery lock: it decides
whether a final customer estimate may be exposed at all.

Fail-closed contract: a final estimate can only be unlocked when *every* named
requirement is affirmatively satisfied. Anything unknown, missing, in-progress,
or test-only leaves the lock closed. This module never sends messages, prices,
approves, or delivers estimates; it only reports capability truth and whether the
delivery lock may open.
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = "capability_registry_v1"

# Capability maturity stages, ordered least -> most mature.
CAPABILITY_STAGES: tuple[str, ...] = (
    "planned",
    "source",
    "staging",
    "production",
    "accuracy_validated",
)

# Only these stages are trustworthy enough to back a final customer estimate.
DELIVERY_GRADE_STAGES: frozenset[str] = frozenset({"production", "accuracy_validated"})

# Truthful current state of each estimating capability. These are intentionally
# conservative: the engine is internal Phase-0 tooling, so nothing is labeled
# delivery-grade. Raising a stage here is an explicit, auditable claim that the
# capability has actually reached that maturity.
CAPABILITY_REGISTRY: dict[str, dict[str, Any]] = {
    "scope_coverage": {
        "stage": "staging",
        "summary": "Scope coverage drafting from extracted documents.",
    },
    "quantity_takeoff": {
        "stage": "staging",
        "summary": "Quantity requirement backbone with reviewer-applied quantities.",
    },
    "pricing_basis": {
        "stage": "staging",
        "summary": "Generic pricing-basis capture; not a final pricing engine.",
    },
    "evidence_provenance": {
        "stage": "staging",
        "summary": "Verified-sheet evidence and extraction confidence gating.",
    },
    "final_customer_delivery": {
        "stage": "planned",
        "summary": "Final customer estimate delivery is not built or enabled.",
    },
}

# Capabilities that must all be delivery-grade before a final estimate may be
# exposed to a customer.
REQUIRED_DELIVERY_CAPABILITIES: tuple[str, ...] = (
    "scope_coverage",
    "quantity_takeoff",
    "pricing_basis",
    "evidence_provenance",
    "final_customer_delivery",
)

# No trade/project lane has passed the audit-required accuracy-validation gate yet.
# This set must remain empty until a narrow supported stratum has measured holdout
# evidence, qualified review policy, and owner approval. Detection or source code
# support alone is not customer-delivery support.
SUPPORTED_CUSTOMER_DELIVERY_TRADES: frozenset[str] = frozenset()

# Source markers that mean a quantity/pricing input is test-only scaffolding and
# can never be treated as real customer-delivery evidence.
_TEST_ONLY_MARKERS: frozenset[str] = frozenset({
    "test", "tests", "testing", "fixture", "fixtures", "sample", "samples",
    "dummy", "mock", "mocked", "placeholder", "synthetic", "demo", "example",
    "examples", "seed", "seeded", "faker", "stub", "sandbox", "fake",
    # Audit-reset harness outputs are useful engineering evidence but must never
    # become customer-delivery evidence unless re-adjudicated into a real,
    # owner-approved evidence source.
    "harness", "golden", "benchmark", "autoresearch", "generated", "simulated",
    "training", "evaluation", "eval",
})


def stage_rank(stage: str | None) -> int:
    try:
        return CAPABILITY_STAGES.index(str(stage))
    except ValueError:
        return -1


def is_delivery_grade(stage: str | None) -> bool:
    """Delivery-grade requires an explicit production/accuracy-validated label."""
    return str(stage) in DELIVERY_GRADE_STAGES


def is_test_only_source(source: Any) -> bool:
    """True when a quantity/pricing source is test-only or has unknown provenance.

    Fail-closed: an empty/unknown source is treated as non-delivery-grade because
    we cannot prove it is real customer evidence.
    """
    if source in (None, ""):
        return True
    tokens = re.split(r"[^a-z0-9]+", str(source).lower())
    return any(token in _TEST_ONLY_MARKERS for token in tokens if token)


def classify_delivery_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Split provided quantity/pricing sources into real vs test-only/unknown."""
    test_only: list[dict[str, Any]] = []
    for entry in sources:
        source = entry.get("source")
        if is_test_only_source(source):
            test_only.append({
                "scope_item_id": entry.get("scope_item_id"),
                "kind": entry.get("kind"),
                "source": source,
                "reason": "Source is test-only scaffolding or has unknown provenance."
                if source not in (None, "")
                else "Source is missing; provenance cannot be verified.",
            })
    return {
        "evaluated_source_count": len(sources),
        "test_only_source_count": len(test_only),
        "no_test_only_delivery_evidence": len(test_only) == 0 and len(sources) > 0,
        "test_only_sources": test_only,
    }


def classify_supported_scope(scope_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return final-delivery support classification for scope items.

    Fail-closed: until a trade is explicitly listed in
    ``SUPPORTED_CUSTOMER_DELIVERY_TRADES``, every scope item for that trade is an
    unsupported customer-delivery scope and must abstain rather than produce a
    final estimate.
    """
    unsupported: list[dict[str, Any]] = []
    supported: list[dict[str, Any]] = []
    for item in scope_items:
        trade_code = str(item.get("trade_code") or "").strip()
        row = {
            "scope_item_id": item.get("id"),
            "trade_code": trade_code or None,
            "category_code": item.get("category_code"),
        }
        if trade_code and trade_code in SUPPORTED_CUSTOMER_DELIVERY_TRADES:
            supported.append(row)
        else:
            unsupported.append({
                **row,
                "reason": "Trade/project lane is not accuracy-validated for customer delivery.",
            })
    return {
        "supported_customer_delivery_trades": sorted(SUPPORTED_CUSTOMER_DELIVERY_TRADES),
        "evaluated_scope_item_count": len(scope_items),
        "supported_scope_item_count": len(supported),
        "unsupported_scope_item_count": len(unsupported),
        "supported_scope": len(scope_items) > 0 and len(unsupported) == 0,
        "unsupported_scope_items": unsupported,
    }


def classify_owner_approval(owner_approval: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the explicit owner approval required for customer delivery.

    Fail-closed: a bare ``{"approved": True}`` is not enough to expose a final
    estimate. The approval must be an explicit final-customer-delivery approval
    with an approver and timestamp so status labels or partial review events
    cannot masquerade as owner authorization.
    """
    required_fields = ("approved", "approved_by", "approved_at", "approval_scope")
    missing_fields: list[str] = []
    if not isinstance(owner_approval, dict):
        return {
            "approved": False,
            "valid": False,
            "required_fields": list(required_fields),
            "missing_fields": list(required_fields),
            "reason": "Owner approval record is absent or invalid.",
        }

    approved = owner_approval.get("approved") is True
    if not approved:
        missing_fields.append("approved")
    for field in ("approved_by", "approved_at", "approval_scope"):
        if not str(owner_approval.get(field) or "").strip():
            missing_fields.append(field)

    approval_scope = str(owner_approval.get("approval_scope") or "").strip()
    valid_scope = approval_scope == "final_customer_delivery"
    if approval_scope and not valid_scope:
        missing_fields.append("approval_scope:final_customer_delivery")

    valid = approved and valid_scope and not missing_fields
    return {
        "approved": approved,
        "valid": valid,
        "required_fields": list(required_fields),
        "missing_fields": missing_fields,
        "approval_scope": approval_scope or None,
        "approved_by_present": bool(str(owner_approval.get("approved_by") or "").strip()),
        "approved_at_present": bool(str(owner_approval.get("approved_at") or "").strip()),
        "reason": None if valid else "Explicit final-customer-delivery owner approval is incomplete.",
    }


def capability_gaps(required: tuple[str, ...] = REQUIRED_DELIVERY_CAPABILITIES) -> list[dict[str, Any]]:
    """Return required capabilities that are not yet delivery-grade."""
    gaps: list[dict[str, Any]] = []
    for name in required:
        entry = CAPABILITY_REGISTRY.get(name)
        stage = entry.get("stage") if entry else None
        if not is_delivery_grade(stage):
            gaps.append({
                "capability": name,
                "stage": stage,
                "required_stages": sorted(DELIVERY_GRADE_STAGES),
                "reason": "Capability is not labeled production or accuracy_validated."
                if entry
                else "Capability is not registered.",
            })
    return gaps


def get_capability_registry() -> dict[str, Any]:
    """Public, truthful snapshot of capability stages."""
    capabilities = {
        name: {
            "stage": entry["stage"],
            "delivery_grade": is_delivery_grade(entry["stage"]),
            "summary": entry["summary"],
        }
        for name, entry in CAPABILITY_REGISTRY.items()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "stages": list(CAPABILITY_STAGES),
        "delivery_grade_stages": sorted(DELIVERY_GRADE_STAGES),
        "capabilities": capabilities,
        "required_delivery_capabilities": list(REQUIRED_DELIVERY_CAPABILITIES),
        "all_required_delivery_grade": len(capability_gaps()) == 0,
    }


def evaluate_delivery_lock(
    *,
    evidence_complete: bool,
    required_reviews_complete: bool,
    owner_approval: dict[str, Any] | None,
    delivery_sources: list[dict[str, Any]],
    supported_scope: bool = False,
    unsupported_scope: dict[str, Any] | None = None,
    required_capabilities: tuple[str, ...] = REQUIRED_DELIVERY_CAPABILITIES,
) -> dict[str, Any]:
    """Fail-closed final customer-delivery lock.

    Returns lock metadata whose ``delivery_unlocked`` is only True when every
    requirement is affirmatively satisfied: required capabilities are
    delivery-grade, the requested scope is supported, complete evidence is
    present, required reviews passed, an owner approval is recorded, and no
    test-only source backs the estimate.
    """
    gaps = capability_gaps(required_capabilities)
    capabilities_delivery_grade = len(gaps) == 0

    source_classification = classify_delivery_sources(delivery_sources)
    no_test_only_delivery_evidence = source_classification["no_test_only_delivery_evidence"]

    owner_approval_check = classify_owner_approval(owner_approval)
    owner_approval_present = owner_approval_check["valid"]

    requirements = {
        "capabilities_delivery_grade": capabilities_delivery_grade,
        "supported_scope": bool(supported_scope),
        "evidence_complete": bool(evidence_complete),
        "required_reviews_complete": bool(required_reviews_complete),
        "owner_approval_present": owner_approval_present,
        "no_test_only_delivery_evidence": no_test_only_delivery_evidence,
    }

    reasons: list[str] = []
    if not requirements["capabilities_delivery_grade"]:
        reasons.append("Required estimating capabilities are not production/accuracy-validated.")
    if not requirements["supported_scope"]:
        reasons.append("Requested scope is not in an accuracy-validated supported customer-delivery lane.")
    if not requirements["evidence_complete"]:
        reasons.append("Complete verified evidence is not present for all scope.")
    if not requirements["required_reviews_complete"]:
        reasons.append("Required internal reviews are not complete.")
    if not requirements["owner_approval_present"]:
        reasons.append("Owner approval for customer delivery is not recorded.")
    if not requirements["no_test_only_delivery_evidence"]:
        reasons.append("Estimate relies on test-only or unverified-provenance sources.")

    delivery_unlocked = all(requirements.values())

    return {
        "schema_version": "customer_delivery_lock_v1",
        "fail_closed": True,
        "delivery_unlocked": delivery_unlocked,
        "state": "unlocked" if delivery_unlocked else "locked",
        "requirements": requirements,
        "reasons": reasons,
        "capability_gaps": gaps,
        "required_capabilities": list(required_capabilities),
        "source_check": source_classification,
        "unsupported_scope": unsupported_scope or {
            "supported_scope": bool(supported_scope),
            "unsupported_scope_items": [],
        },
        "owner_approval_check": owner_approval_check,
        "owner_approval_present": owner_approval_present,
    }
