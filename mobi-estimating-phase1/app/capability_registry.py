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
        "evidence": [
            "app/generic_scope.py",
            "app/routers_estimate_bridge.py",
            "tests/test_generic_estimate_bridge.py",
        ],
    },
    "quantity_takeoff": {
        "stage": "staging",
        "summary": "Quantity requirement backbone with reviewer-applied quantities.",
        "evidence": [
            "app/quantity_requirements.py",
            "app/generic_estimate_bridge.py",
            "tests/test_quantity_requirements.py",
        ],
    },
    "pricing_basis": {
        "stage": "staging",
        "summary": "Generic pricing-basis capture; not a final pricing engine.",
        "evidence": [
            "app/generic_pricing_inputs.py",
            "app/generic_estimate_bridge.py",
            "tests/test_pricing_e2e.py",
        ],
    },
    "evidence_provenance": {
        "stage": "staging",
        "summary": "Verified-sheet evidence and extraction confidence gating.",
        "evidence": [
            "app/capability_registry.py",
            "app/estimate_readiness.py",
            "tests/test_capability_registry_api.py",
        ],
    },
    "final_customer_delivery": {
        "stage": "planned",
        "summary": "Final customer estimate delivery is not built or enabled.",
        "evidence": [
            "app/capability_registry.py",
            "app/routers_pricing.py",
            "app/proposals/service.py",
            "tests/test_capability_registry_api.py",
        ],
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

# Final construction-estimate delivery is an owner-only business action. Keep the
# authorized approver list explicit so an internal reviewer/staff status cannot
# masquerade as Moses' final customer-delivery approval.
AUTHORIZED_FINAL_DELIVERY_APPROVERS: frozenset[str] = frozenset({
    "moses",
    "moses cervantes",
    "owner:moses",
})

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

_TEST_ONLY_METADATA_FLAGS: frozenset[str] = frozenset({
    "internal_testing_only",
    "is_internal_testing_only",
    "test_only",
    "is_test_only",
    "testing_only",
    "is_testing_only",
    "fixture_only",
    "is_fixture",
    "synthetic_only",
    "is_synthetic",
})

_TEST_ONLY_METADATA_CONTAINERS: tuple[str, ...] = (
    "metadata",
    "source_metadata",
    "provenance_metadata",
    "audit_metadata",
)

# Compact provenance strings sometimes arrive without separators/camel case. Keep
# these known safe words from causing false positives while still failing closed
# on embedded test/demo/seed markers such as ``supplierquotetest2026``.
_COMPACT_TEST_MARKER_SAFE_WORDS: tuple[str, ...] = ("latest", "contest", "demolition")

_MALFORMED_SCOPE_ID_SENTINELS: frozenset[str] = frozenset({
    "none",
    "null",
    "undefined",
    "nan",
})


def normalize_scope_item_id(value: Any) -> str:
    """Return a durable scope item ID or ``""`` when the value is malformed.

    Scope IDs are delivery-lock evidence join keys. They must never be created by
    coercing missing values or common null sentinels into plausible strings such
    as ``"None"``/``"null"``/``"nan"``. Treat those values exactly like missing
    IDs so both expected scope and source evidence fail closed consistently.
    """
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    if not normalized:
        return ""
    if normalized.lower() in _MALFORMED_SCOPE_ID_SENTINELS:
        return ""
    return normalized


def build_delivery_source_row(
    *,
    scope_item_id: Any,
    kind: str,
    source: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical row consumed by ``classify_delivery_sources``.

    Delivery-source callers must preserve both flat test-only flags and nested
    provenance envelopes. Otherwise a real-looking source string such as
    ``supplier_quote_2026`` could hide ``metadata.test_only=true`` and be counted
    as real customer-delivery evidence. Keep this row shape in the registry so
    every delivery surface forwards the same safety-critical metadata.
    """
    metadata = metadata if isinstance(metadata, dict) else {}
    return {
        "scope_item_id": scope_item_id,
        "kind": kind,
        "source": source,
        **{key: metadata.get(key) for key in _TEST_ONLY_METADATA_FLAGS},
        **{key: metadata.get(key) for key in _TEST_ONLY_METADATA_CONTAINERS},
    }


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
    # Match whole provenance tokens first. Substring matching made common real
    # words look test-only (for example ``latest`` contains ``test`` and
    # ``demolition`` starts with ``demo``), which could later turn a legitimate
    # supported-lane delivery source into a false blocker. Snake/kebab/camel case
    # harness markers are caught as separate tokens.
    if any(token in _TEST_ONLY_MARKERS for token in tokens if token):
        return True

    # Still fail closed on compact all-lowercase test provenance where markers
    # were concatenated without delimiters/camel case. Strip only specific safe
    # words that previously caused false positives, then catch embedded markers
    # anywhere else in the compact provenance string.
    compact = re.sub(r"[^a-z0-9]+", "", normalized.lower())
    unambiguous_compact_markers = _TEST_ONLY_MARKERS - {"test", "demo", "seed"}
    if any(marker in compact for marker in unambiguous_compact_markers):
        return True
    compact_without_safe_words = compact
    for safe_word in _COMPACT_TEST_MARKER_SAFE_WORDS:
        compact_without_safe_words = compact_without_safe_words.replace(safe_word, "")
    if any(marker in compact_without_safe_words for marker in ("test", "demo", "seed")):
        return True
    return False


def _entry_has_test_only_metadata(entry: dict[str, Any]) -> bool:
    """True when provenance metadata explicitly marks a row as test-only.

    Source strings are not the only way harness/test evidence can be labeled. A
    row with a real-looking source such as ``staff_verified_takeoff`` must still
    be blocked if its structured metadata says it is an internal test fixture.
    Only literal ``True`` is treated as the flag; malformed strings/numbers are
    handled by the normal source-provenance checks instead of being coerced.

    Some upstream surfaces store these flags inside nested metadata envelopes.
    Walk the structured metadata recursively so an export/readiness path cannot
    hide a test-only flag by wrapping it inside ``metadata.provenance_metadata``
    or another known envelope. Lists are supported for serialized evidence arrays;
    a depth and visited guard keep malformed/cyclic metadata fail-safe.
    """
    return _value_has_test_only_metadata(entry)


def has_test_only_metadata(value: Any) -> bool:
    """Public fail-closed test-only metadata check for delivery surfaces.

    Customer-facing export/proposal gates also need to inspect non-source rows
    such as evidence lists. Reuse the same recursive metadata semantics as
    quantity/pricing sources so a fixture flag cannot be hidden in a nested
    evidence envelope and then counted as complete final-delivery evidence.
    """
    return _value_has_test_only_metadata(value)


def is_complete_delivery_evidence_row(row: Any) -> bool:
    """Return True only for concrete, non-test final-delivery evidence.

    Final estimate exports and proposal surfaces must not treat an arbitrary
    non-empty evidence object as complete evidence. A delivery-grade row needs a
    real provenance reference plus the minimum document coordinates needed for a
    reviewer/customer audit trail: verified sheet number, PDF page number, and
    evidence type. Missing or test-like provenance fails closed.
    """
    if not isinstance(row, dict):
        return False
    if has_test_only_metadata(row):
        return False
    provenance_ref = row.get("source_artifact_ref") or row.get("source")
    if is_test_only_source(provenance_ref):
        return False
    sheet = row.get("verified_sheet_number")
    evidence_type = row.get("evidence_type")
    page_number = row.get("pdf_page_number")
    return (
        isinstance(sheet, str)
        and bool(sheet.strip())
        and isinstance(evidence_type, str)
        and bool(evidence_type.strip())
        and isinstance(page_number, int)
        and not isinstance(page_number, bool)
        and page_number > 0
    )


def _metadata_flag_marks_test_only(value: Any) -> bool:
    """Return True when a known metadata flag cannot be delivery-grade.

    Test-only flags are safety-critical provenance. Accept only explicit negative
    values as clean; literal true, common serialized true values, and malformed
    non-empty flag values all fail closed so ``test_only=\"true\"`` or
    ``internal_testing_only=1`` cannot pass as real customer evidence.
    """
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "n"}
    return True


def _value_has_test_only_metadata(value: Any, *, depth: int = 0, visited: set[int] | None = None) -> bool:
    """Recursively inspect structured metadata for test-only flags."""
    if depth > 8:
        # Over-deep structured provenance cannot be audited safely. Treat it as
        # blocked/test-only rather than letting a wrapped flag disappear into
        # real customer-delivery evidence.
        return True
    if visited is None:
        visited = set()

    if isinstance(value, dict):
        value_id = id(value)
        if value_id in visited:
            # Cyclic provenance cannot be audited safely; block it instead of
            # treating it as clean real customer-delivery evidence.
            return True
        visited.add(value_id)
        try:
            if any(_metadata_flag_marks_test_only(value.get(flag)) for flag in _TEST_ONLY_METADATA_FLAGS):
                return True
            for child_value in value.values():
                if _value_has_test_only_metadata(child_value, depth=depth + 1, visited=visited):
                    return True
            return False
        finally:
            visited.remove(value_id)

    if isinstance(value, list):
        value_id = id(value)
        if value_id in visited:
            # Cyclic provenance cannot be audited safely; block it instead of
            # treating it as clean real customer-delivery evidence.
            return True
        visited.add(value_id)
        try:
            return any(
                _value_has_test_only_metadata(item, depth=depth + 1, visited=visited)
                for item in value
            )
        finally:
            visited.remove(value_id)

    return False


def classify_delivery_sources(sources: list[dict[str, Any]] | Any) -> dict[str, Any]:
    """Split provided quantity/pricing sources into real vs blocked evidence.

    Fail-closed: a real-looking source without an explicit scope item is invalid
    customer-delivery provenance. Otherwise stale/unscoped quantity or pricing
    rows can be silently ignored while the lock opens on the remaining rows. A
    malformed container (for example ``None`` or a dict instead of a list) is also
    treated as unverifiable provenance instead of crashing or being ignored.
    """
    test_only: list[dict[str, Any]] = []
    unscoped: list[dict[str, Any]] = []
    unsupported_kind: list[dict[str, Any]] = []
    malformed_container_count = 0
    real_scope_item_ids: set[str] = set()
    real_scope_item_ids_by_kind: dict[str, set[str]] = {
        kind: set() for kind in REQUIRED_DELIVERY_SOURCE_KINDS
    }
    accepted_source_kinds = frozenset().union(*_SOURCE_KIND_GROUPS.values())
    if isinstance(sources, list):
        source_rows = sources
    else:
        malformed_container_count = 1
        source_rows = []
        test_only.append({
            "scope_item_id": None,
            "kind": None,
            "source": sources,
            "reason": "Source collection is malformed; provenance cannot be verified.",
        })
    for entry in source_rows:
        if not isinstance(entry, dict):
            test_only.append({
                "scope_item_id": None,
                "kind": None,
                "source": entry,
                "reason": "Source row is malformed; provenance cannot be verified.",
            })
            continue
        source = entry.get("source")
        scope_item_id = entry.get("scope_item_id")
        normalized_scope_item_id = normalize_scope_item_id(scope_item_id)
        entry_kind = str(entry.get("kind") or "")
        if _entry_has_test_only_metadata(entry):
            test_only.append({
                "scope_item_id": scope_item_id,
                "kind": entry.get("kind"),
                "source": source,
                "reason": "Source metadata marks this row as test-only scaffolding.",
            })
        elif is_test_only_source(source):
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
        "evaluated_source_count": len(source_rows),
        "malformed_source_collection_count": malformed_container_count,
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
            and len(source_rows) > 0
        ),
        "all_delivery_sources_scoped": all_delivery_sources_scoped,
        "all_delivery_sources_supported_kind": all_delivery_sources_supported_kind,
        "test_only_sources": test_only,
        "unscoped_sources": unscoped,
        "unsupported_kind_sources": unsupported_kind,
    }


def classify_supported_scope(scope_items: list[dict[str, Any]] | Any) -> dict[str, Any]:
    """Return final-delivery support classification for scope items.

    Fail-closed: until a trade is explicitly listed in
    ``SUPPORTED_CUSTOMER_DELIVERY_TRADES``, every scope item for that trade is an
    unsupported customer-delivery scope and must abstain rather than produce a
    final estimate. A malformed scope collection is treated as one unsupported
    row so callers cannot accidentally unlock delivery by passing the wrong data
    shape.
    """
    unsupported: list[dict[str, Any]] = []
    supported: list[dict[str, Any]] = []
    malformed_container_count = 0
    if isinstance(scope_items, list):
        scope_rows = scope_items
    else:
        malformed_container_count = 1
        scope_rows = []
        unsupported.append({
            "scope_item_id": None,
            "trade_code": None,
            "category_code": None,
            "reason": "Scope item collection is malformed; supported delivery scope cannot be verified.",
        })
    seen_scope_item_ids: set[str] = set()
    for item in scope_rows:
        if not isinstance(item, dict):
            unsupported.append({
                "scope_item_id": None,
                "trade_code": None,
                "category_code": None,
                "reason": "Scope item row is malformed; supported delivery scope cannot be verified.",
            })
            continue
        raw_scope_item_id = item.get("id")
        scope_item_id = normalize_scope_item_id(raw_scope_item_id)
        raw_trade_code = item.get("trade_code")
        trade_code = raw_trade_code.strip() if isinstance(raw_trade_code, str) else ""
        row = {
            "scope_item_id": raw_scope_item_id,
            "trade_code": trade_code or None,
            "category_code": item.get("category_code"),
        }
        if not scope_item_id:
            unsupported.append({
                **row,
                "reason": "Scope item is missing durable scope_item_id; supported delivery scope cannot be verified.",
            })
        elif scope_item_id in seen_scope_item_ids:
            unsupported.append({
                **row,
                "reason": "Scope item ID is duplicated; supported delivery scope cannot be verified.",
            })
        elif not trade_code:
            seen_scope_item_ids.add(scope_item_id)
            unsupported.append({
                **row,
                "reason": "Scope item is missing a valid trade_code; supported delivery scope cannot be verified.",
            })
        elif trade_code in SUPPORTED_CUSTOMER_DELIVERY_TRADES:
            seen_scope_item_ids.add(scope_item_id)
            supported.append(row)
        else:
            seen_scope_item_ids.add(scope_item_id)
            unsupported.append({
                **row,
                "reason": "Trade/project lane is not accuracy-validated for customer delivery.",
            })
    return {
        "supported_customer_delivery_trades": sorted(SUPPORTED_CUSTOMER_DELIVERY_TRADES),
        "evaluated_scope_item_count": len(scope_rows),
        "malformed_scope_collection_count": malformed_container_count,
        "supported_scope_item_count": len(supported),
        "unsupported_scope_item_count": len(unsupported),
        "supported_scope": len(scope_rows) > 0 and len(unsupported) == 0,
        "supported_scope_items": supported,
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


def _non_empty_string(value: Any) -> str:
    """Return stripped text only for real strings.

    Approval metadata is audit evidence. Numbers, booleans, lists, or objects must
    not be coerced into plausible-looking approver/scope values.
    """
    return value.strip() if isinstance(value, str) else ""


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

    approved_by = _non_empty_string(owner_approval.get("approved_by"))
    raw_approved_at = _non_empty_string(owner_approval.get("approved_at"))
    approval_scope = _non_empty_string(owner_approval.get("approval_scope"))
    approved_by_authorized = approved_by.lower() in AUTHORIZED_FINAL_DELIVERY_APPROVERS
    if not approved_by:
        missing_fields.append("approved_by")
    elif not approved_by_authorized:
        missing_fields.append("approved_by:authorized_owner")
    if not raw_approved_at:
        missing_fields.append("approved_at")
    if not approval_scope:
        missing_fields.append("approval_scope")

    approval_datetime = _parse_owner_approval_datetime(raw_approved_at)
    approval_timestamp = approval_datetime.isoformat() if approval_datetime else None
    approval_timestamp_valid = approval_datetime is not None
    if raw_approved_at and not approval_timestamp_valid:
        missing_fields.append("approved_at:valid_iso8601_timezone")

    approval_timestamp_not_future = False
    if approval_datetime is not None:
        approval_timestamp_not_future = approval_datetime <= datetime.now(timezone.utc)
        if not approval_timestamp_not_future:
            missing_fields.append("approved_at:not_future")

    valid_scope = approval_scope == "final_customer_delivery"
    if approval_scope and not valid_scope:
        missing_fields.append("approval_scope:final_customer_delivery")

    valid = (
        approved
        and approved_by_authorized
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
        "approved_by_present": bool(approved_by),
        "approved_by_authorized": approved_by_authorized,
        "authorized_approvers": sorted(AUTHORIZED_FINAL_DELIVERY_APPROVERS),
        "approved_at_present": bool(raw_approved_at),
        "approval_timestamp_valid": approval_timestamp_valid,
        "approval_timestamp_not_future": approval_timestamp_not_future,
        "approval_timestamp": approval_timestamp,
        "reason": None if valid else "Explicit final-customer-delivery owner approval is incomplete.",
    }


def _nonnegative_int_count(value: Any, *, default: int | None = None) -> int | None:
    """Return an exact non-negative integer count or a supplied default.

    Delivery-lock proof counts are safety evidence. Booleans, floats, strings,
    and missing values must not be coerced into plausible-looking counts.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    if value is None:
        return default
    return None


def _explicit_true(value: Any) -> bool:
    """Return True only for a literal boolean True.

    Delivery-lock booleans are audit evidence, not convenience flags. Strings such
    as ``"true"``/``"complete"``, integers, or truthy containers must never be
    coerced into completed evidence/review gates.
    """
    return value is True


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
            "evidence": list(entry.get("evidence") or []),
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
    """Return canonical source-kind requirements for customer delivery.

    Callers may add future evidence-kind groups, but they cannot weaken the P0
    lock by omitting the canonical quantity/pricing pair. A final estimate needs
    real quantity lineage and real pricing lineage for every expected scope item.
    Unknown caller-supplied kinds are reported separately and fail closed instead
    of being silently ignored.
    """
    normalized: list[str] = []
    for kind in (*REQUIRED_DELIVERY_SOURCE_KINDS, *required_source_kinds):
        if kind in _SOURCE_KIND_GROUPS and kind not in normalized:
            normalized.append(kind)
    return tuple(normalized)


def _unknown_required_source_kinds(required_source_kinds: tuple[str, ...]) -> list[str]:
    """Return caller-supplied source-kind requirements the registry cannot verify.

    A typo or future source-kind name must not be treated as satisfied by the
    canonical quantity/pricing checks. Keep canonical kinds separate from unknown
    extras so default callers stay stable while custom requirements fail closed.
    """
    unknown: list[str] = []
    for kind in required_source_kinds:
        if kind not in _SOURCE_KIND_GROUPS and kind not in unknown:
            unknown.append(kind)
    return unknown


def _canonical_required_capabilities(required_capabilities: tuple[str, ...]) -> tuple[str, ...]:
    """Return fail-closed capability requirements for customer delivery.

    Callers may add future capability requirements for narrower release lanes, but
    they must never weaken the P0 lock by passing an empty or partial tuple. Final
    customer delivery always requires the canonical capability set from the
    truthful registry, including the currently planned/locked final-delivery
    capability.
    """
    normalized: list[str] = []
    for capability in (*REQUIRED_DELIVERY_CAPABILITIES, *required_capabilities):
        if capability not in normalized:
            normalized.append(capability)
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
    expected_scope_item_ids: list[Any] | tuple[Any, ...] | None = None,
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
    canonical_required_capabilities = _canonical_required_capabilities(required_capabilities)
    gaps = capability_gaps(canonical_required_capabilities)
    capabilities_delivery_grade = len(gaps) == 0
    canonical_required_source_kinds = _canonical_required_source_kinds(required_source_kinds)
    unknown_required_source_kinds = _unknown_required_source_kinds(required_source_kinds)

    source_classification = classify_delivery_sources(delivery_sources)
    no_test_only_delivery_evidence = source_classification["no_test_only_delivery_evidence"]
    expected_scope_count = _nonnegative_int_count(expected_scope_item_count)
    expected_scope_count_valid = expected_scope_item_count is None or expected_scope_count is not None
    if isinstance(expected_scope_item_ids, (list, tuple)):
        expected_scope_item_ids_container_valid = True
        raw_expected_scope_item_ids = list(expected_scope_item_ids)
    else:
        expected_scope_item_ids_container_valid = False
        raw_expected_scope_item_ids = []
    expected_scope_ids_list = [
        normalize_scope_item_id(scope_item_id)
        for scope_item_id in raw_expected_scope_item_ids
    ]
    malformed_expected_scope_item_ids = [
        scope_item_id
        for scope_item_id, normalized_scope_item_id in zip(
            raw_expected_scope_item_ids,
            expected_scope_ids_list,
            strict=False,
        )
        if not normalized_scope_item_id
    ]
    expected_scope_ids = {
        normalized_scope_item_id
        for normalized_scope_item_id in expected_scope_ids_list
        if normalized_scope_item_id
    }
    duplicate_expected_scope_item_ids = sorted({
        normalized_scope_item_id
        for normalized_scope_item_id in expected_scope_ids_list
        if normalized_scope_item_id and expected_scope_ids_list.count(normalized_scope_item_id) > 1
    })
    expected_scope_ids_valid = (
        expected_scope_item_ids_container_valid
        and bool(raw_expected_scope_item_ids)
        and len(malformed_expected_scope_item_ids) == 0
        and len(duplicate_expected_scope_item_ids) == 0
        and len(expected_scope_ids) == len(raw_expected_scope_item_ids)
    )
    real_scope_ids = set(source_classification["real_source_scope_item_ids"])
    source_scope_coverage_complete = (
        expected_scope_ids_valid
        and real_scope_ids == expected_scope_ids
    )
    if expected_scope_item_count is not None:
        source_scope_coverage_complete = (
            source_scope_coverage_complete
            and expected_scope_count_valid
            and len(expected_scope_ids) == expected_scope_count
        )
    real_scope_ids_by_kind = {
        kind: set(source_classification["real_source_scope_item_ids_by_kind"].get(kind, []))
        for kind in canonical_required_source_kinds
    }
    missing_source_scope_item_ids_by_kind = {
        kind: sorted(expected_scope_ids - scope_ids)
        for kind, scope_ids in real_scope_ids_by_kind.items()
    }
    source_kind_coverage_complete = bool(expected_scope_ids) and not unknown_required_source_kinds and all(
        not missing_ids for missing_ids in missing_source_scope_item_ids_by_kind.values()
    )

    supported_scope_verified = False
    if unsupported_scope is not None:
        if isinstance(unsupported_scope, dict):
            evaluated_scope_item_count = _nonnegative_int_count(
                unsupported_scope.get("evaluated_scope_item_count")
            )
            unsupported_scope_item_count = _nonnegative_int_count(
                unsupported_scope.get("unsupported_scope_item_count")
            )
            supported_scope_item_count = _nonnegative_int_count(
                unsupported_scope.get("supported_scope_item_count")
            )
            malformed_scope_collection_count = _nonnegative_int_count(
                unsupported_scope.get("malformed_scope_collection_count"),
                default=0,
            )
            expected_scope_count_verified = (
                expected_scope_item_count is None
                or (
                    expected_scope_count_valid
                    and evaluated_scope_item_count == expected_scope_count
                )
            )
            supported_scope_items = unsupported_scope.get("supported_scope_items")
            unsupported_scope_items = unsupported_scope.get("unsupported_scope_items")
            supported_scope_item_ids: set[str] = set()
            duplicate_supported_scope_item_ids: set[str] = set()
            supported_scope_items_valid = isinstance(supported_scope_items, list)
            if isinstance(supported_scope_items, list):
                for row in supported_scope_items:
                    if not isinstance(row, dict):
                        supported_scope_items_valid = False
                        break
                    normalized_scope_item_id = normalize_scope_item_id(row.get("scope_item_id"))
                    if not normalized_scope_item_id:
                        supported_scope_items_valid = False
                        break
                    if normalized_scope_item_id in supported_scope_item_ids:
                        duplicate_supported_scope_item_ids.add(normalized_scope_item_id)
                    supported_scope_item_ids.add(normalized_scope_item_id)
            supported_scope_items_count_matches = (
                isinstance(supported_scope_items, list)
                and supported_scope_item_count is not None
                and evaluated_scope_item_count is not None
                and len(supported_scope_items) == supported_scope_item_count
                and supported_scope_item_count == evaluated_scope_item_count
            )
            supported_scope_ids_match_expected = (
                expected_scope_ids_valid
                and supported_scope_item_ids == expected_scope_ids
                and len(supported_scope_item_ids) == supported_scope_item_count
                and len(duplicate_supported_scope_item_ids) == 0
            )
            supported_scope_verified = (
                unsupported_scope.get("supported_scope") is True
                and evaluated_scope_item_count is not None
                and evaluated_scope_item_count > 0
                and expected_scope_count_verified
                and supported_scope_items_count_matches
                and supported_scope_item_count == evaluated_scope_item_count
                and unsupported_scope_item_count == 0
                and malformed_scope_collection_count == 0
                and supported_scope_items_valid
                and supported_scope_ids_match_expected
                and isinstance(unsupported_scope_items, list)
                and len(unsupported_scope_items) == 0
            )

    owner_approval_check = classify_owner_approval(owner_approval)
    owner_approval_present = owner_approval_check["valid"]

    evidence_complete_verified = _explicit_true(evidence_complete)
    required_reviews_complete_verified = _explicit_true(required_reviews_complete)

    requirements = {
        "capabilities_delivery_grade": capabilities_delivery_grade,
        "supported_scope": supported_scope_verified,
        "evidence_complete": evidence_complete_verified,
        "required_reviews_complete": required_reviews_complete_verified,
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
        if not expected_scope_count_valid:
            reasons.append("Expected scope item count is malformed; delivery evidence coverage cannot be verified.")
        elif not expected_scope_item_ids_container_valid:
            reasons.append("Expected scope item IDs collection is malformed; delivery evidence coverage cannot be verified.")
        elif not expected_scope_ids_valid:
            reasons.append("Expected scope item IDs are missing, malformed, or duplicated; delivery evidence coverage cannot be verified.")
        else:
            reasons.append("Real delivery evidence sources do not cover every expected scope item.")
    if not requirements["source_kind_coverage_complete"]:
        if unknown_required_source_kinds:
            reasons.append("Required source-kind requirements are unknown; delivery evidence coverage cannot be verified.")
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
        "required_capabilities": list(canonical_required_capabilities),
        "source_check": source_classification,
        "expected_scope_item_count": expected_scope_item_count,
        "expected_scope_item_count_valid": expected_scope_count_valid,
        "expected_scope_item_ids_container_valid": expected_scope_item_ids_container_valid,
        "expected_scope_item_ids": sorted(expected_scope_ids),
        "expected_scope_item_ids_valid": expected_scope_ids_valid,
        "malformed_expected_scope_item_ids": malformed_expected_scope_item_ids,
        "duplicate_expected_scope_item_ids": duplicate_expected_scope_item_ids,
        "missing_source_scope_item_ids": sorted(expected_scope_ids - real_scope_ids),
        "extra_source_scope_item_ids": sorted(real_scope_ids - expected_scope_ids),
        "required_source_kinds": list(canonical_required_source_kinds),
        "unknown_required_source_kinds": unknown_required_source_kinds,
        "missing_source_scope_item_ids_by_kind": missing_source_scope_item_ids_by_kind,
        "unsupported_scope": unsupported_scope or {
            "supported_scope": bool(supported_scope),
            "unsupported_scope_items": [],
        },
        "owner_approval_check": owner_approval_check,
        "owner_approval_present": owner_approval_present,
    }
