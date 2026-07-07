"""Internal clarification package v1.

Packages unresolved register entries into internal clarification candidates.
This module is read-only: it does not approve, price, message, bill, send, or
deliver a customer-facing construction estimate.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.assumptions_register import build_assumptions_register

_WORD_RE = re.compile(r"[^a-zA-Z0-9]+")

_CODE_GUIDANCE: dict[str, tuple[str, str]] = {
    "missing_quantity": (
        "measurement",
        "Please confirm the measurement or count we should use for this {trade_label} scope item.",
    ),
    "open_quantity_requirement": (
        "measurement",
        "Please confirm the measurement or count we should use for this {trade_label} scope item.",
    ),
    "quantity_basis_unclear": (
        "measurement_basis",
        "Please confirm the measurement basis for this {trade_label} scope item.",
    ),
    "missing_pricing_basis": (
        "basis_confirmation",
        "Please confirm what basis or allowance should be used for this {trade_label} scope item.",
    ),
    "missing_unit_rate": (
        "basis_confirmation",
        "Please confirm what basis or allowance should be used for this {trade_label} scope item.",
    ),
    "missing_subcontract_quote": (
        "document_or_quote",
        "Please confirm whether a separate subcontractor quote will be provided for this {trade_label} scope item.",
    ),
    "missing_allowance_basis": (
        "basis_confirmation",
        "Please confirm what allowance basis should be used for this {trade_label} scope item.",
    ),
    "missing_extraction_provenance": (
        "source_reference",
        "Please confirm which plan sheet or document section supports this {trade_label} scope item.",
    ),
    "low_extraction_confidence": (
        "scope_confirmation",
        "Please confirm the {trade_label} scope shown in the plans.",
    ),
    "included_without_basis": (
        "scope_confirmation",
        "Please confirm whether this {trade_label} scope should be included.",
    ),
    "undispositioned_trade": (
        "scope_confirmation",
        "Please confirm whether this {trade_label} scope should be included.",
    ),
    "blocked_without_blockers": (
        "scope_confirmation",
        "Please confirm what is still needed for the {trade_label} scope.",
    ),
}

_DEFAULT_RESPONSE_TYPE = "scope_confirmation"
_DEFAULT_QUESTION = "Please clarify the {trade_label} scope so the estimate can be completed accurately."
_SEVERITY_PRIORITY = {
    "critical": 100,
    "major": 70,
    "minor": 30,
    "info": 10,
}
_CODE_PRIORITY = {
    "missing_quantity": 20,
    "open_quantity_requirement": 20,
    "missing_pricing_basis": 18,
    "missing_unit_rate": 18,
    "missing_subcontract_quote": 18,
    "missing_allowance_basis": 18,
    "missing_extraction_provenance": 16,
    "low_extraction_confidence": 14,
    "quantity_basis_unclear": 12,
    "included_without_basis": 10,
    "undispositioned_trade": 10,
    "blocked_without_blockers": 8,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trade_label(trade_code: str | None) -> str:
    if not trade_code:
        return "project"
    normalized = _WORD_RE.sub(" ", str(trade_code)).strip().lower()
    if not normalized:
        return "project"
    if normalized in {"general trade", "generic scope"}:
        return "general"
    return normalized


def _candidate_id(entry: dict[str, Any]) -> str:
    raw = "|".join(
        str(entry.get(key) or "")
        for key in (
            "kind",
            "code",
            "severity",
            "trade_code",
            "scope_item_id",
            "coverage_row_id",
            "qa_finding_id",
            "source",
            "message",
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"clarification_{digest}"


def _safe_question(entry: dict[str, Any]) -> tuple[str, str]:
    code = str(entry.get("code") or "")
    response_type, template = _CODE_GUIDANCE.get(code, (_DEFAULT_RESPONSE_TYPE, _DEFAULT_QUESTION))
    return response_type, template.format(trade_label=_trade_label(entry.get("trade_code")))


def _candidate_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    response_type, question = _safe_question(entry)
    severity = entry.get("severity") or "major"
    priority_score = _priority_score(entry)
    return {
        "id": _candidate_id(entry),
        "source_entry_kind": entry.get("kind"),
        "source_entry_code": entry.get("code"),
        "severity": severity,
        "priority_score": priority_score,
        "priority_bucket": _priority_bucket(priority_score),
        "trade_code": entry.get("trade_code"),
        "scope_item_id": entry.get("scope_item_id"),
        "coverage_row_id": entry.get("coverage_row_id"),
        "qa_finding_id": entry.get("qa_finding_id"),
        "source": entry.get("source"),
        "internal_reason": entry.get("message") or "Unresolved estimating input requires clarification.",
        "customer_safe_question": question,
        "required_response_type": response_type,
        "blocks_delivery": bool(entry.get("blocks_delivery")),
        "customer_visible_candidate": bool(entry.get("customer_visible_candidate", True)),
        "human_approval_required": True,
    }


def _priority_score(entry: dict[str, Any]) -> int:
    severity = str(entry.get("severity") or "major").lower()
    code = str(entry.get("code") or "")
    score = _SEVERITY_PRIORITY.get(severity, _SEVERITY_PRIORITY["major"])
    score += _CODE_PRIORITY.get(code, 0)
    if entry.get("blocks_delivery"):
        score += 25
    if entry.get("kind") == "open_question":
        score += 5
    return score


def _priority_bucket(score: int) -> str:
    if score >= 115:
        return "urgent"
    if score >= 90:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def _group_key(value: Any) -> str:
    if value is None:
        return "unspecified"
    text = str(value).strip()
    return text or "unspecified"


def _group_counts(candidates: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = _group_key(candidate.get(field))
        item = grouped.setdefault(key, {
            "key": key,
            "count": 0,
            "blocking_count": 0,
            "critical_count": 0,
            "highest_priority_score": 0,
        })
        item["count"] += 1
        if candidate.get("blocks_delivery"):
            item["blocking_count"] += 1
        if candidate.get("severity") == "critical":
            item["critical_count"] += 1
        item["highest_priority_score"] = max(item["highest_priority_score"], int(candidate.get("priority_score") or 0))
    return sorted(
        grouped.values(),
        key=lambda item: (-item["highest_priority_score"], -item["blocking_count"], -item["count"], item["key"]),
    )


def _priority_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -int(candidate.get("priority_score") or 0),
            str(candidate.get("trade_code") or ""),
            str(candidate.get("source_entry_code") or ""),
            str(candidate.get("id") or ""),
        ),
    )
    by_bucket = {"urgent": 0, "high": 0, "medium": 0, "low": 0}
    for candidate in candidates:
        bucket = str(candidate.get("priority_bucket") or "low")
        by_bucket[bucket] = by_bucket.get(bucket, 0) + 1
    top = ordered[0] if ordered else None
    return {
        "highest_priority_score": int(top.get("priority_score") or 0) if top else 0,
        "highest_priority_bucket": top.get("priority_bucket") if top else None,
        "urgent_candidate_count": by_bucket.get("urgent", 0),
        "high_candidate_count": by_bucket.get("high", 0),
        "medium_candidate_count": by_bucket.get("medium", 0),
        "low_candidate_count": by_bucket.get("low", 0),
        "top_candidate_ids": [candidate["id"] for candidate in ordered[:5]],
    }


def build_clarification_package(project_id: UUID, *, register: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an internal clarification package from the assumptions register.

    The package is deterministic and read-only. It can be used by staff/owner
    review workflows to decide which questions may later become customer-facing,
    but it never sends or marks a message as ready to send.
    """
    assumptions_register = register or build_assumptions_register(project_id)
    entries = list(assumptions_register.get("open_questions") or [])
    for entry in assumptions_register.get("assumptions") or []:
        if entry.get("blocks_delivery"):
            entries.append(entry)
    for entry in assumptions_register.get("exclusions") or []:
        if entry.get("blocks_delivery"):
            entries.append(entry)

    candidates = [_candidate_from_entry(entry) for entry in entries]
    candidates = sorted(
        candidates,
        key=lambda candidate: (
            -int(candidate.get("priority_score") or 0),
            str(candidate.get("trade_code") or ""),
            str(candidate.get("source_entry_code") or ""),
            str(candidate.get("id") or ""),
        ),
    )
    for priority_rank, candidate in enumerate(candidates, start=1):
        candidate["priority_rank"] = priority_rank
    blocking = [candidate for candidate in candidates if candidate["blocks_delivery"]]
    critical = [candidate for candidate in candidates if candidate["severity"] == "critical"]
    customer_safe = [candidate for candidate in candidates if candidate["customer_visible_candidate"]]
    priority = _priority_summary(candidates)

    return {
        "project_id": str(project_id),
        "generated_at": _now(),
        "package_type": "internal_clarification_package_v1",
        "customer_delivery_ready": False,
        "customer_message_ready": False,
        "send_ready": False,
        "send_gate": "Clarification candidates require human approval and a separate messaging workflow before any external communication.",
        "summary": {
            "candidate_count": len(candidates),
            "blocking_candidate_count": len(blocking),
            "critical_candidate_count": len(critical),
            "customer_safe_candidate_count": len(customer_safe),
            **priority,
        },
        "groups": {
            "by_priority_bucket": _group_counts(candidates, "priority_bucket"),
            "by_severity": _group_counts(candidates, "severity"),
            "by_trade": _group_counts(candidates, "trade_code"),
            "by_source_code": _group_counts(candidates, "source_entry_code"),
            "by_source": _group_counts(candidates, "source"),
        },
        "candidates": candidates,
    }
