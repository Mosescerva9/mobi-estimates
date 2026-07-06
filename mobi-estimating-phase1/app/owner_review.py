"""Internal owner-review package v1.

Builds a deterministic review packet from readiness + BOE state. This is not a
customer proposal, not a final construction estimate, and not a delivery action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.boe import draft_boe
from app.estimate_readiness import evaluate_estimate_readiness


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_owner_review_package(project_id: UUID) -> dict[str, Any]:
    readiness = evaluate_estimate_readiness(project_id)
    boe = draft_boe(project_id)
    ready = bool(readiness.get("ready_for_owner_review"))
    register = boe.get("assumptions_register") or {}
    return {
        "project_id": str(project_id),
        "generated_at": _now(),
        "package_type": "internal_owner_review_v1",
        "status": "ready_for_owner_review" if ready else "blocked",
        "ready_for_owner_review": ready,
        "customer_delivery_ready": False,
        "customer_delivery_gate": "Final construction estimate delivery requires explicit approval and a separate customer-delivery workflow.",
        "review_decision_options": [
            "approve_for_customer_delivery_prep",
            "return_to_pricing_or_quantity_inputs",
            "request_customer_clarification",
            "hold_blocked",
        ],
        "executive_summary": {
            "readiness_status": readiness.get("status"),
            "scope_item_count": readiness.get("summary", {}).get("scope_item_count", 0),
            "open_quantity_requirement_count": readiness.get("summary", {}).get("open_quantity_requirement_count", 0),
            "missing_pricing_input_count": readiness.get("summary", {}).get("missing_pricing_input_count", 0),
            "critical_qa_finding_count": readiness.get("summary", {}).get("critical_qa_finding_count", 0),
            "assumption_count": register.get("summary", {}).get("assumption_count", 0),
            "exclusion_count": register.get("summary", {}).get("exclusion_count", 0),
            "open_question_count": register.get("summary", {}).get("open_question_count", 0),
            "boe_status": boe.get("status"),
        },
        "blockers": readiness.get("blockers", []),
        "review_packet": {
            "readiness": readiness,
            "basis_of_estimate": boe,
            "assumptions_register": register,
            "owner_notes": [
                "Review scope coverage, assumptions, exclusions, quantities, pricing basis, and unresolved blockers before any customer-facing package is prepared.",
                "This packet is generated for internal owner review only.",
            ],
        },
    }
