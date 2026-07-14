"""Customer-safe internal preview for draft generic estimate versions.

This preview is read-only and intentionally does not create, approve, issue,
send, deliver, bill, or expose final pricing. It is a bridge between internal
draft estimate records and the eventual customer-safe proposal package contract.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app import pricing_db
from app.capability_registry import classify_supported_scope, has_test_only_metadata, is_test_only_source
from app.trades.registry import trade_registry


class DraftPreviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_FORBIDDEN_TEXT = (
    "direct_cost",
    "labor_cost",
    "material_cost",
    "equipment_cost",
    "subcontract_cost",
    "other_direct_cost",
    "gross margin",
    "margin",
    "markup",
    "overhead",
    "profit",
    "loaded_rate",
    "rate",
    "cost_book",
    "pricing_basis",
    "source",
    "generic_pricing_basis",
    "reviewer",
    "readiness",
    "/home/",
    "api_key",
)


def _trade_name(code: str | None) -> str:
    if not code:
        return "General Scope"
    if trade_registry.is_registered(code):
        return trade_registry.get(code).trade_name
    return str(code).replace("_", " ").replace("-", " ").title()


def _safe_text(value: Any, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").split())
    lowered = text.lower()
    if not text:
        return fallback
    if any(term in lowered for term in _FORBIDDEN_TEXT):
        return fallback
    return text


def _safe_list(values: Any, *, fallback_items: list[str] | None = None) -> list[str]:
    if not isinstance(values, list):
        return fallback_items or []
    out = [_safe_text(value) for value in values]
    out = [value for value in out if value]
    return out or (fallback_items or [])


def _iter_quantity_provenance_sources(line: dict[str, Any]) -> list[Any]:
    """Return quantity provenance markers persisted with an estimate line.

    Draft preview is a read surface: it must not trust that every writer used the
    generic bridge's write-time blockers. Quantity values are customer-visible in
    the preview, so re-check every persisted quantity/evidence provenance marker
    available on the line and fail closed when no auditable marker exists.
    """
    direct_sources: list[Any] = []
    for key in ("quantity_source", "quantity_basis", "source"):
        if key in line:
            direct_sources.append(line.get(key))

    override_sources: list[Any] = []
    raw_overrides = line.get("overrides")
    overrides = raw_overrides if isinstance(raw_overrides, list) else []
    for row in overrides:
        if isinstance(row, dict):
            for key in ("quantity_source", "quantity_basis", "source"):
                if key in row:
                    override_sources.append(row.get(key))
            metadata = row.get("metadata")
            if isinstance(metadata, dict):
                for key in ("quantity_source", "quantity_basis", "source"):
                    if key in metadata:
                        override_sources.append(metadata.get(key))

    # Explicit quantity provenance on the line/override is stronger than generic
    # document evidence. Test fixtures may use synthetic PDFs while still testing
    # a real-looking staff-verified quantity source; production must persist the
    # explicit quantity source so preview does not infer from unrelated evidence.
    sources = direct_sources + override_sources
    if sources:
        return sources

    evidence_sources: list[Any] = []
    raw_evidence = line.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, list) else []
    for row in evidence:
        if isinstance(row, dict):
            evidence_sources.append(row.get("source_artifact_ref") or row.get("source"))
    return evidence_sources


def _quantity_must_abstain(line: dict[str, Any], *, supported_scope: bool) -> bool:
    if line.get("quantity") in (None, ""):
        return False
    if not supported_scope:
        return True
    if has_test_only_metadata(line):
        return True
    sources = _iter_quantity_provenance_sources(line)
    if not sources:
        return True
    return any(is_test_only_source(source) for source in sources)


def _scope_row_for_line(line: dict[str, Any]) -> dict[str, Any]:
    """Map persisted estimate line shape back to the delivery-lock scope shape."""
    return {
        "id": line.get("scope_item_id"),
        "trade_code": line.get("trade_code"),
        "category_code": line.get("category_code"),
    }


def _line_to_preview(line: dict[str, Any], *, supported_scope: bool) -> tuple[dict[str, Any], bool, bool]:
    description = _safe_text(line.get("description"), fallback="Scope item pending final wording.")
    location = _safe_text(line.get("location"), fallback="")
    quantity_abstained = _quantity_must_abstain(line, supported_scope=supported_scope)
    quantity = "" if quantity_abstained else _safe_text(line.get("quantity"), fallback="")
    unit = "" if quantity_abstained else _safe_text(line.get("unit"), fallback="")
    scope_note = (
        "Unsupported scope is withheld from this preview until its trade/project lane is accuracy-validated."
        if not supported_scope
        else "Quantity is pending validation and is withheld from this preview."
        if quantity_abstained
        else "Included in the draft scope; final bid package is pending validation."
    )
    item: dict[str, Any] = {
        "section": _trade_name(line.get("trade_code")),
        "description": description,
        "quantity": quantity,
        "unit": unit,
        "scope_note": scope_note,
    }
    if location:
        item["location"] = location
    return item, quantity_abstained, not supported_scope


def build_draft_proposal_preview(
    project_id: UUID,
    estimate_id: UUID,
    estimate_version_id: UUID,
) -> dict[str, Any]:
    """Build a read-only customer-safe preview from an internal draft estimate version."""
    estimate = pricing_db.get_estimate(project_id, estimate_id)
    if estimate is None:
        raise DraftPreviewError("estimate_not_found", "Estimate not found.")
    version = pricing_db.get_estimate_version(estimate_version_id)
    if version is None:
        raise DraftPreviewError("estimate_version_not_found", "Estimate version not found.")
    if version.get("estimate_id") != str(estimate_id) or version.get("project_id") != str(project_id):
        raise DraftPreviewError("estimate_version_not_found", "Estimate version not found.")
    raw_config = version.get("config")
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    if version.get("status") != "draft":
        raise DraftPreviewError(
            "preview_delivery_locked",
            "Draft proposal preview is locked for non-draft estimate versions; final customer delivery requires the full P0 approval gate.",
        )
    if config.get("source") != "generic_estimate_bridge_v1":
        raise DraftPreviewError(
            "preview_delivery_locked",
            "Draft proposal preview is only available for generic-estimate bridge drafts, not final-delivery records.",
        )
    customer_delivery_ready_flag = config.get("customer_delivery_ready")
    if customer_delivery_ready_flag is not None and customer_delivery_ready_flag is not False:
        raise DraftPreviewError(
            "preview_delivery_locked",
            "Draft proposal preview cannot expose a version marked customer-delivery-ready without the explicit final-delivery workflow.",
        )
    delivery_lock = config.get("customer_delivery_lock")
    if delivery_lock is not None and not isinstance(delivery_lock, dict):
        raise DraftPreviewError(
            "preview_delivery_locked",
            "Draft proposal preview cannot trust a malformed final-delivery lock record.",
        )
    if isinstance(delivery_lock, dict) and (
        delivery_lock.get("delivery_unlocked") is not None
        and delivery_lock.get("delivery_unlocked") is not False
    ):
        raise DraftPreviewError(
            "preview_delivery_locked",
            "Draft proposal preview cannot bypass the final-delivery lock.",
        )

    lines = pricing_db.get_line_items(str(estimate_version_id))
    supported_scope = classify_supported_scope([_scope_row_for_line(line) for line in lines])
    supported_line_ids = {
        item["scope_item_id"] for item in supported_scope.get("supported_scope_items", [])
    }
    unsupported_line_ids = {
        item["scope_item_id"] for item in supported_scope.get("unsupported_scope_items", [])
    }
    converted_lines = [
        _line_to_preview(
            line,
            # If any persisted row with this scope ID is unsupported (including a
            # duplicate/manual row), fail closed for every matching line. A set of
            # supported IDs alone would otherwise let the first supported duplicate
            # mask a later unsupported duplicate carrying estimate-like quantity.
            supported_scope=(
                line.get("scope_item_id") in supported_line_ids
                and line.get("scope_item_id") not in unsupported_line_ids
            ),
        )
        for line in lines
    ]
    line_items = [item for item, _quantity_abstained, _unsupported_scope in converted_lines]
    quantity_abstained_count = sum(
        1 for _item, quantity_abstained, _unsupported_scope in converted_lines if quantity_abstained
    )
    unsupported_scope_count = sum(
        1 for _item, _quantity_abstained, unsupported_scope in converted_lines if unsupported_scope
    )
    blocked_count = int(config.get("blocked_scope_item_count") or 0)
    clarifications = []
    if blocked_count:
        clarifications.append(f"{blocked_count} scope item(s) still need clarification or validation before a final bid package can be prepared.")
    if quantity_abstained_count:
        clarifications.append(f"{quantity_abstained_count} draft quantity value(s) were withheld because their provenance is test-only or not delivery-grade.")
    if unsupported_scope_count:
        clarifications.append(f"{unsupported_scope_count} draft scope line(s) were withheld because their trade/project lane is not accuracy-validated for customer delivery.")
    if not line_items:
        clarifications.append("No validated draft scope lines are available yet.")

    preview = {
        "title": _safe_text(estimate.get("name"), fallback="Draft Estimate Preview"),
        "status": "internal_preview_only",
        "summary": {
            "scope_line_count": len(line_items),
            "blocked_scope_item_count": blocked_count,
            "quantity_abstained_count": quantity_abstained_count,
            "unsupported_scope_count": unsupported_scope_count,
            "customer_delivery_ready": False,
            "final_estimate_approved": False,
            "external_messages": False,
            "payments": False,
        },
        "line_items": line_items,
        "inclusions": _safe_list(
            version.get("inclusions"),
            fallback_items=["Validated draft scope lines listed in this preview."],
        ),
        "exclusions": _safe_list(
            version.get("exclusions"),
            fallback_items=["Items still missing validation are excluded from this preview."],
        ),
        "assumptions": _safe_list(
            version.get("assumptions"),
            fallback_items=["This preview is for review only and requires final validation before customer delivery."],
        ),
        "clarifications": clarifications + _safe_list(version.get("clarifications")),
        "safety_flags": {
            "preview_only": True,
            "customer_delivery_ready": False,
            "final_estimate_approved": False,
            "external_messages": False,
            "payments": False,
            "proposal_created": False,
            "proposal_issued": False,
        },
    }
    return {
        "project_id": str(project_id),
        "estimate_id": str(estimate_id),
        "estimate_version_id": str(estimate_version_id),
        "customer_safe_preview": preview,
    }
