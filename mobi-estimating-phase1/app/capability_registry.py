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
from datetime import datetime, timezone
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

# Final customer delivery needs both real measurement/quantity lineage and real
# pricing/cost lineage for every expected scope item. A single real-looking
# source row must not unlock delivery for an otherwise uncovered quantity or
# pricing basis.
REQUIRED_DELIVERY_SOURCE_KINDS: tuple[str, ...] = ("quantity", "pricing")

_SOURCE_KIND_GROUPS: dict[str, frozenset[str]] = {
    "quantity": frozenset({
        "quantity_input",
        "estimate_line_quantity_source",
    }),
    "pricing": frozenset({
        "pricing_basis",
        "cost_component_source",
        "estimate_line_component_source",
    }),
}

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
    we cannot prove it is real customer evidence. The provenance marker must be a
    non-empty string; booleans/numbers/containers are malformed metadata, not
    auditable customer-delivery evidence.
    """
    if not isinstance(source, str):
        return True
    normalized = source.strip()
    if not normalized:
        return True
    camel_spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normalized)
    tokens = re.split(r"[^a-z0-9]+", camel_spaced.lower())
    compact = re.sub(r"[^a-z0-9]+", "", normalized.lower())
    return any(
        token in _TEST_ONLY_MARKERS
        or (len(marker) >= 4 and marker in compact)
        for token in tokens
        if token
        for marker in _TEST_ONLY_MARKERS
    )


def classify_delivery_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Split provided quantity/pricing sources into real vs blocked evidence.

    Fail-closed: a real-looking source without an explicit scope item is invalid
    customer-delivery provenance. Otherwise stale/unscoped quantity or pricing
    rows can be silently ignored while the lock opens on the remaining rows.
    """
    test_only: list[dict[str, Any]] = []
    unscoped: list[dict[str, Any]] = []
    unsupported_kind: list[dict[str, Any]] = []
    real_scope_item_ids: set[str] = set()
    real_scope_item_ids_by_kind: dict[str, set[str]] = {
        kind: set() for kind in REQUIRED_DELIVERY_SOURCE_KINDS
    }
    accepted_source_kinds = frozenset().union(*_SOURCE_KIND_GROUPS.values())
    for entry in sources:
        source = entry.get("source")
        scope_item_id = entry.get("scope_item_id")
        normalized_scope_item_id = str(scope_item_id).strip() if scope_item_id not in (None, "") else ""
        entry_kind = str(entry.get("kind") or "")
        if is_test_only_source(source):
            test_only.append({
                "scope_item_id": scope_item_id,
                "kind": entry.get("kind"),
                "source": source,
                "reason": "Source is test-only scaffolding or has unknown provenance."
                if source not in (None, "")
                else "Source is missing; provenance cannot be verified.",
            })
        elif not normalized_scope_item_id:
            unscoped.append({
                "scope_item_id": scope_item_id,
                "kind": entry.get("kind"),
                "source": source,
                "reason": "Source is missing scope_item_id; provenance cannot be tied to expected scope.",
            })
        elif entry_kind not in accepted_source_kinds:
            unsupported_kind.append({
                "scope_item_id": scope_item_id,
                "kind": entry.get("kind"),
                "source": source,
                "reason": "Source kind is not accepted as quantity or pricing delivery evidence.",
            })
        else:
            scope_id = normalized_scope_item_id
            real_scope_item_ids.add(scope_id)
            for required_kind, accepted_kinds in _SOURCE_KIND_GROUPS.items():
                if entry_kind in accepted_kinds:
                    real_scope_item_ids_by_kind.setdefault(required_kind, set()).add(scope_id)
    all_delivery_sources_scoped = len(unscoped) == 0
    all_delivery_sources_supported_kind = len(unsupported_kind) == 0
    return {
        "evaluated_source_count": len(sources),
        "test_only_source_count": len(test_only),
        "unscoped_source_count": len(unscoped),
        "unsupported_source_kind_count": len(unsupported_kind),
        "real_source_scope_item_count": len(real_scope_item_ids),
        "real_source_scope_item_ids": sorted(real_scope_item_ids),
        "required_source_kinds": list(REQUIRED_DELIVERY_SOURCE_KINDS),
        "accepted_source_kinds": sorted(accepted_source_kinds),
        "real_source_scope_item_ids_by_kind": {
            kind: sorted(scope_ids) for kind, scope_ids in real_scope_item_ids_by_kind.items()
        },
        "no_test_only_delivery_evidence": (
            len(test_only) == 0
            and all_delivery_sources_scoped
            and all_delivery_sources_supported_kind
            and len(sources) > 0
        ),
        "all_delivery_sources_scoped": all_delivery_sources_scoped,
        "all_delivery_sources_supported_kind": all_delivery_sources_supported_kind,
        "test_only_sources": test_only,
        "unscoped_sources": unscoped,
        "unsupported_kind_sources": unsupported_kind,
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


def _parse_owner_approval_datetime(value: Any) -> datetime | None:
    """Return parsed owner-approval datetime when the value is auditable.

    A final-delivery owner approval must be a real timestamp, not a status label,
    free-text note, or date-only placeholder. Require an ISO-8601 datetime with
    timezone information so the approval can be audited later.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _parse_owner_approval_timestamp(value: Any) -> str | None:
    """Return normalized ISO timestamp when owner approval time is valid."""
    parsed = _parse_owner_approval_datetime(value)
    if parsed is None:
        return None
    return parsed.isoformat()


def classify_owner_approval(owner_approval: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the explicit owner approval required for customer delivery.

    Fail-closed: a bare ``{"approved": True}`` is not enough to expose a final
    estimate. The approval must be an explicit final-customer-delivery approval
    with an approver and auditable timestamp so status labels, partial review
    events, or malformed date placeholders cannot masquerade as owner
    authorization.
    """
    required_fields = ("approved", "approved_by", "approved_at", "approval_scope")
    missing_fields: list[str] = []
    if not isinstance(owner_approval, dict):
        return {
            "approved": False,
            "valid": False,
            "required_fields": list(required_fields),
            "missing_fields": list(required_fields),
            "approval_timestamp_valid": False,
            "reason": "Owner approval record is absent or invalid.",
        }

    approved = owner_approval.get("approved") is True
    if not approved:
        missing_fields.append("approved")
    for field in ("approved_by", "approved_at", "approval_scope"):
        if not str(owner_approval.get(field) or "").strip():
            missing_fields.append(field)

    approval_datetime = _parse_owner_approval_datetime(owner_approval.get("approved_at"))
    approval_timestamp = approval_datetime.isoformat() if approval_datetime else None
    approval_timestamp_valid = approval_datetime is not None
    if owner_approval.get("approved_at") not in (None, "") and not approval_timestamp_valid:
        missing_fields.append("approved_at:valid_iso8601_timezone")

    approval_timestamp_not_future = False
    if approval_datetime is not None:
        approval_timestamp_not_future = approval_datetime <= datetime.now(timezone.utc)
        if not approval_timestamp_not_future:
            missing_fields.append("approved_at:not_future")

    approval_scope = str(owner_approval.get("approval_scope") or "").strip()
    valid_scope = approval_scope == "final_customer_delivery"
    if approval_scope and not valid_scope:
        missing_fields.append("approval_scope:final_customer_delivery")

    valid = (
        approved
        and valid_scope
        and approval_timestamp_valid
        and approval_timestamp_not_future
        and not missing_fields
    )
    return {
        "approved": approved,
        "valid": valid,
        "required_fields": list(required_fields),
        "missing_fields": missing_fields,
        "approval_scope": approval_scope or None,
        "approved_by_present": bool(str(owner_approval.get("approved_by") or "").strip()),
        "approved_at_present": bool(str(owner_approval.get("approved_at") or "").strip()),
        "approval_timestamp_valid": approval_timestamp_valid,
        "approval_timestamp_not_future": approval_timestamp_not_future,
        "approval_timestamp": approval_timestamp,
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


def _canonical_required_source_kinds(required_source_kinds: tuple[str, ...]) -> tuple[str, ...]:
    """Return fail-closed source-kind requirements for customer delivery.

    Callers may add future evidence-kind groups, but they cannot weaken the P0
    lock by omitting the canonical quantity/pricing pair. A final estimate needs
    real quantity lineage and real pricing lineage for every expected scope item.
    """
    normalized: list[str] = []
    for kind in (*REQUIRED_DELIVERY_SOURCE_KINDS, *required_source_kinds):
        if kind in _SOURCE_KIND_GROUPS and kind not in normalized:
            normalized.append(kind)
    return tuple(normalized)


def evaluate_delivery_lock(
    *,
    evidence_complete: bool,
    required_reviews_complete: bool,
    owner_approval: dict[str, Any] | None,
    delivery_sources: list[dict[str, Any]],
    supported_scope: bool = False,
    unsupported_scope: dict[str, Any] | None = None,
    expected_scope_item_count: int | None = None,
    expected_scope_item_ids: list[Any] | tuple[Any, ...] | set[Any] | frozenset[Any] | None = None,
    required_source_kinds: tuple[str, ...] = REQUIRED_DELIVERY_SOURCE_KINDS,
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
    canonical_required_source_kinds = _canonical_required_source_kinds(required_source_kinds)

    source_classification = classify_delivery_sources(delivery_sources)
    no_test_only_delivery_evidence = source_classification["no_test_only_delivery_evidence"]
    expected_scope_ids = {
        normalized_scope_item_id
        for scope_item_id in (expected_scope_item_ids or [])
        for normalized_scope_item_id in [str(scope_item_id).strip()]
        if normalized_scope_item_id
    }
    real_scope_ids = set(source_classification["real_source_scope_item_ids"])
    source_scope_coverage_complete = bool(expected_scope_ids) and real_scope_ids == expected_scope_ids
    if expected_scope_item_count is not None:
        source_scope_coverage_complete = (
            source_scope_coverage_complete and len(expected_scope_ids) == expected_scope_item_count
        )
    real_scope_ids_by_kind = {
        kind: set(source_classification["real_source_scope_item_ids_by_kind"].get(kind, []))
        for kind in canonical_required_source_kinds
    }
    missing_source_scope_item_ids_by_kind = {
        kind: sorted(expected_scope_ids - scope_ids)
        for kind, scope_ids in real_scope_ids_by_kind.items()
    }
    source_kind_coverage_complete = bool(expected_scope_ids) and all(
        not missing_ids for missing_ids in missing_source_scope_item_ids_by_kind.values()
    )

    owner_approval_check = classify_owner_approval(owner_approval)
    owner_approval_present = owner_approval_check["valid"]

    requirements = {
        "capabilities_delivery_grade": capabilities_delivery_grade,
        "supported_scope": bool(supported_scope),
        "evidence_complete": bool(evidence_complete),
        "required_reviews_complete": bool(required_reviews_complete),
        "owner_approval_present": owner_approval_present,
        "no_test_only_delivery_evidence": no_test_only_delivery_evidence,
        "source_scope_coverage_complete": source_scope_coverage_complete,
        "source_kind_coverage_complete": source_kind_coverage_complete,
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
    if not requirements["source_scope_coverage_complete"]:
        reasons.append("Real delivery evidence sources do not cover every expected scope item.")
    if not requirements["source_kind_coverage_complete"]:
        reasons.append("Every expected scope item must have real quantity and pricing evidence sources.")

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
        "expected_scope_item_count": expected_scope_item_count,
        "expected_scope_item_ids": sorted(expected_scope_ids),
        "missing_source_scope_item_ids": sorted(expected_scope_ids - real_scope_ids),
        "extra_source_scope_item_ids": sorted(real_scope_ids - expected_scope_ids),
        "required_source_kinds": list(canonical_required_source_kinds),
        "missing_source_scope_item_ids_by_kind": missing_source_scope_item_ids_by_kind,
        "unsupported_scope": unsupported_scope or {
            "supported_scope": bool(supported_scope),
            "unsupported_scope_items": [],
        },
        "owner_approval_check": owner_approval_check,
        "owner_approval_present": owner_approval_present,
    }
