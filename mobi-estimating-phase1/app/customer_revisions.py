"""Customer Revision Parser / Workflow v1.

Parses customer or reviewer free-text revision feedback into internal request rows.
No external messages are sent and no estimate/proposal is regenerated here.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.database import get_connection
from app.estimate_readiness import evaluate_estimate_readiness
from app.tenant_boundary import build_tenant_project_context

ACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("exclude", re.compile(r"\b(exclude|remove|deduct|delete|take out|omit)\b", re.I)),
    ("include", re.compile(r"\b(include|add|carry|price|provide)\b", re.I)),
    ("revise", re.compile(r"\b(revise|change|update|adjust|swap|replace)\b", re.I)),
    ("clarify", re.compile(r"\b(confirm|clarify|question|verify|is it|does this)\b", re.I)),
)

TRADE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("electrical", ("electrical", "electric", "power", "lighting", "panel", "outlet")),
    ("plumbing", ("plumbing", "plumber", "fixture", "water", "sanitary", "gas line")),
    ("hvac", ("hvac", "mechanical", "duct", "diffuser", "rtu", "air")),
    ("fire_alarm", ("fire alarm", "fa system", "notification", "detector")),
    ("fire_protection", ("sprinkler", "fire protection", "fp system")),
    ("doors_hardware", ("door", "hardware", "frame", "lockset")),
    ("finishes", ("paint", "floor", "finish", "tile", "ceiling")),
    ("sitework", ("site", "civil", "grading", "paving", "asphalt", "concrete walk")),
)

SHEET_RE = re.compile(r"\b([A-Z]{1,3}[- ]?\d{1,4}(?:\.\d+)?)\b")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value in (None, ""):
        return {}
    return json.loads(value)


def _row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["payload"] = _loads(data.get("payload"))
    return data


def _split_items(text: str) -> list[str]:
    candidates: list[str] = []
    for raw in re.split(r"\n+|(?:^|\s)(?:[-*•]|\d+[.)])\s+", text):
        clean = raw.strip(" \t-•*")
        if len(clean) >= 4:
            candidates.append(clean)
    return candidates or [text.strip()]


def _action(text: str) -> str:
    for action, pattern in ACTION_PATTERNS:
        if pattern.search(text):
            return action
    return "review"


def _trade(text: str) -> str | None:
    lower = text.lower()
    for trade_code, keywords in TRADE_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return trade_code
    return None


def _confidence(action: str, trade_code: str | None, sheet_refs: list[str]) -> float:
    score = 0.35
    if action != "review":
        score += 0.2
    if trade_code:
        score += 0.25
    if sheet_refs:
        score += 0.15
    return min(score, 0.95)


def create_revision_requests(
    project_id: UUID,
    *,
    source: str,
    raw_text: str,
    actor: str = "customer",
) -> dict[str, Any]:
    now = _now()
    items = []
    for text in _split_items(raw_text):
        action = _action(text)
        trade_code = _trade(text)
        sheet_refs = SHEET_RE.findall(text)
        payload = {
            "raw_text": text,
            "sheet_refs": sheet_refs,
            "parser": "customer_revision_parser_v1",
        }
        items.append({
            "id": str(uuid4()),
            "project_id": str(project_id),
            "source": source,
            "actor": actor,
            "action": action,
            "trade_code": trade_code,
            "status": "open",
            "summary": text[:500],
            "confidence": _confidence(action, trade_code, sheet_refs),
            "payload": payload,
            "created_at": now,
            "updated_at": now,
        })
    with get_connection() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO customer_revision_requests (id, project_id, source,
                    actor, action, trade_code, status, summary, confidence, payload,
                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"], item["project_id"], item["source"], item["actor"],
                    item["action"], item["trade_code"], item["status"], item["summary"],
                    item["confidence"], _dumps(item["payload"]), item["created_at"],
                    item["updated_at"],
                ),
            )
        conn.commit()
    return {"project_id": str(project_id), "created_count": len(items), "items": items}


def list_revision_requests(project_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM customer_revision_requests WHERE project_id=? "
            "ORDER BY created_at ASC, id ASC",
            (str(project_id),),
        ).fetchall()
    return [_row(row) for row in rows]


SAFE_TRADE_LABELS: dict[str, str] = {
    "general": "general scope",
    "general_trade": "general scope",
    "painting": "painting",
    "paint": "painting",
    "drywall": "drywall",
    "framing": "framing",
    "flooring": "flooring",
    "concrete": "concrete",
    "masonry": "masonry",
    "roofing": "roofing",
    "electrical": "electrical",
    "plumbing": "plumbing",
    "hvac": "HVAC",
    "mechanical": "mechanical",
    "fire_alarm": "fire alarm",
    "fire_protection": "fire protection",
    "doors_hardware": "doors / hardware",
    "doors": "doors",
    "windows": "windows",
    "millwork": "millwork",
    "finishes": "finishes",
    "carpentry": "carpentry",
    "demolition": "demolition",
    "sitework": "sitework",
    "landscaping": "landscaping",
    "insulation": "insulation",
    "tile": "tile",
    "metals": "metals",
    "specialties": "specialties",
}

SAFE_SHEET_RE = re.compile(r"^[A-Z]{1,3}[- ]?\d{1,4}(?:\.\d+)?$")


def _customer_action_label(value: str | None) -> str:
    return {
        "include": "Include",
        "exclude": "Exclude",
        "revise": "Revise",
        "clarify": "Clarify",
    }.get(value or "", "Review")


def _customer_status_label(value: str | None) -> str:
    return {
        "open": "Received",
        "accepted_for_rescope": "Accepted for scope update",
        "rescope_resolved": "Scope update recorded",
        "rejected": "No estimate change",
        "needs_customer_clarification": "Needs clarification",
        "needs_clarification": "Needs clarification",
    }.get(value or "", "In review")


def _customer_follow_up_label(value: str | None) -> str | None:
    if not value:
        return None
    return {
        "rescope_reprice_required": "Scope update in progress",
        "customer_clarification_required": "Clarification needed",
        "no_estimate_change": "No estimate change planned",
    }.get(value, "In review")


def _customer_trade_label(value: str | None) -> str | None:
    if not value:
        return None
    return SAFE_TRADE_LABELS.get(str(value).strip().lower())


def _customer_safe_summary(action: str | None, trade_label: str | None) -> str:
    trade = f" for {trade_label}" if trade_label else ""
    return {
        "include": f"Requested added scope{trade}.",
        "exclude": f"Requested removed scope{trade}.",
        "revise": f"Requested scope update{trade}.",
        "clarify": f"Requested clarification{trade}.",
    }.get(action or "", f"Revision request received{trade}.")


def _customer_sheet_refs(payload: dict[str, Any]) -> list[str]:
    refs = payload.get("sheet_refs") if isinstance(payload, dict) else []
    if not isinstance(refs, list):
        return []
    safe: list[str] = []
    for ref in refs:
        candidate = str(ref).strip().upper()
        if SAFE_SHEET_RE.fullmatch(candidate):
            safe.append(candidate)
    return safe


def _customer_revision_view(row: dict[str, Any], *, version_count: int, latest_version_at: str | None) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    decision = payload.get("review_decision") if isinstance(payload.get("review_decision"), dict) else {}
    trade_label = _customer_trade_label(row.get("trade_code"))
    follow_up_label = _customer_follow_up_label(decision.get("follow_up_task"))
    return {
        "id": row.get("id"),
        "action": _customer_action_label(row.get("action")),
        "status": _customer_status_label(row.get("status")),
        "trade": trade_label or "general",
        "summary": _customer_safe_summary(row.get("action"), trade_label),
        "sheet_refs": _customer_sheet_refs(payload),
        "follow_up": follow_up_label,
        "version_count": int(version_count),
        "latest_version_at": latest_version_at,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def list_customer_safe_revision_history(project_id: UUID) -> dict[str, Any]:
    """Return a customer-safe read-only revision history contract.

    This view intentionally omits raw customer text, parser summaries, reviewers,
    internal notes, blocker payloads, before/after snapshots, readiness internals,
    pricing language, and staff-only controls.
    """
    with get_connection() as conn:
        request_rows = conn.execute(
            "SELECT * FROM customer_revision_requests WHERE project_id=? ORDER BY created_at ASC, id ASC",
            (str(project_id),),
        ).fetchall()
        version_rows = conn.execute(
            """
            SELECT customer_revision_request_id, COUNT(*) AS version_count, MAX(created_at) AS latest_version_at
            FROM customer_revision_rescope_versions
            WHERE project_id=?
            GROUP BY customer_revision_request_id
            """,
            (str(project_id),),
        ).fetchall()
    version_map = {
        row["customer_revision_request_id"]: {
            "version_count": int(row["version_count"]),
            "latest_version_at": row["latest_version_at"],
        }
        for row in version_rows
    }
    items = []
    for request_row in request_rows:
        request = _row(request_row)
        versions = version_map.get(request["id"], {"version_count": 0, "latest_version_at": None})
        items.append(
            _customer_revision_view(
                request,
                version_count=versions["version_count"],
                latest_version_at=versions["latest_version_at"],
            )
        )
    return {
        "history_type": "customer_safe_revision_history_v1",
        "project_id": str(project_id),
        "items": items,
        "total": len(items),
        "read_only": True,
    }


def submit_customer_safe_revision_request(project_id: UUID, *, raw_text: str) -> dict[str, Any]:
    """Log customer-submitted revision text and return only sanitized items.

    This is the customer-facing mutation contract: it records the request for
    internal handling, then returns a customer-safe view. It does not decide,
    rescope, price, approve, send messages, bill, or deliver estimates.
    """
    created = create_revision_requests(
        project_id,
        source="customer_portal",
        actor="customer",
        raw_text=raw_text,
    )
    created_ids = {item["id"] for item in created.get("items", [])}
    history = list_customer_safe_revision_history(project_id)
    items = [item for item in history["items"] if item["id"] in created_ids]
    return {
        "submission_type": "customer_safe_revision_submission_v1",
        "project_id": str(project_id),
        "created_count": len(items),
        "items": items,
        "customer_submission_recorded": True,
    }


class RevisionDecisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _decision_payload(existing: dict[str, Any], *, decision: str, reviewer: str, notes: str | None) -> dict[str, Any]:
    payload = dict(existing.get("payload") or {})
    payload["review_decision"] = {
        "decision": decision,
        "reviewer": reviewer,
        "notes": notes,
        "reviewed_at": _now(),
        "follow_up_task": (
            "rescope_reprice_required" if decision == "accepted" else
            "customer_clarification_required" if decision == "needs_clarification" else
            "no_estimate_change"
        ),
        "delivery_ready": False,
    }
    return payload



def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, sort_keys=True)


def _get_project_identity(conn: Any, project_id: UUID) -> dict[str, str]:
    row = conn.execute(
        "SELECT id, tenant_id, company_id FROM projects WHERE id=?", (str(project_id),)
    ).fetchone()
    if row is None:
        raise RevisionDecisionError("not_found", "Project not found")
    try:
        return build_tenant_project_context(
            tenant_id=row["tenant_id"],
            company_id=row["company_id"],
            project_id=row["id"],
        )
    except PermissionError as exc:
        raise RevisionDecisionError(
            "tenant_unscoped",
            "Customer revision rescope requires tenant-scoped project identity",
        ) from exc


def _create_revision_extraction_run(
    conn: Any,
    project_id: UUID,
    trade_code: str,
    identity: dict[str, str],
) -> str:
    """Create a synthetic completed run to anchor customer-revision scope blockers."""
    run_id = str(uuid4())
    now = _now()
    conn.execute(
        """
        INSERT INTO extraction_runs (id, project_id, tenant_id, company_id, trade_code, status,
            provider, model_identifier, prompt_version, provider_schema_version,
            trade_schema_version, attempt, completed_at, input_sheet_count,
            processed_sheet_count, blocked_sheet_count, failed_sheet_count,
            candidate_count, dry_run, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'needs_review', ?, ?, ?, ?, ?, 1, ?, 0, 0, 0, 0, 1, 0, ?, ?)
        """,
        (
            run_id, str(project_id), identity["tenant_id"], identity["company_id"], trade_code,
            "customer_revision_workflow", "customer_revision_parser_v1",
            "customer_revision_decision_v1", "customer_revision_workflow_v1",
            "customer_revision_workflow_v1", now, now, now,
        ),
    )
    return run_id


def _create_rescope_blocker(conn: Any, project_id: UUID, request: dict[str, Any]) -> dict[str, Any]:
    """Materialize an accepted customer revision as a blocked scope item.

    Accepted customer revisions must become explicit workflow blockers so the
    readiness gate cannot pass until a later rescope/reprice slice resolves the
    customer's requested change. This does not regenerate estimates, deliver
    work, or send messages.
    """
    now = _now()
    request_id = request["id"]
    trade_code = request.get("trade_code") or "general_trade"
    summary = request.get("summary") or "Customer revision requires rescope/reprice."
    payload = request.get("payload") or {}
    identity = _get_project_identity(conn, project_id)
    sheet_refs = payload.get("sheet_refs") if isinstance(payload, dict) else []
    blocker = {
        "code": "customer_revision_rescope_required",
        "message": "Accepted customer revision requires explicit rescope/reprice before readiness can pass.",
        "customer_revision_request_id": request_id,
        "source": "customer_revision_decision_v1",
    }
    if sheet_refs:
        blocker["sheet_refs"] = sheet_refs
    scope_item = {
        "id": str(uuid4()),
        "project_id": str(project_id),
        "tenant_id": identity["tenant_id"],
        "company_id": identity["company_id"],
        "extraction_run_id": _create_revision_extraction_run(conn, project_id, trade_code, identity),
        "trade_code": trade_code,
        "trade_module_version": "customer_revision_workflow_v1",
        "trade_schema_version": "customer_revision_workflow_v1",
        "category_code": "customer_revision_rescope",
        "description": summary,
        "location": None,
        "specification_section": None,
        "assembly_designation": None,
        "material_or_substrate": None,
        "existing_condition": None,
        "proposed_work": "Rescope/reprice accepted customer revision before customer delivery.",
        "quantity": None,
        "unit": None,
        "quantity_basis": "customer_revision_pending_rescope",
        "raw_quantity_inputs": {},
        "extraction_confidence": request.get("confidence"),
        "conflict_status": "blocking",
        "review_status": "blocked",
        "blocking_issues": [blocker],
        "assumptions": [],
        "exclusions": [],
        "trade_data": {
            "customer_revision_request_id": request_id,
            "revision_action": request.get("action"),
            "revision_status": "accepted_for_rescope",
            "pricing_ready": False,
        },
        "original_provider_candidate": {
            "source": "customer_revision_parser_v1",
            "payload": payload,
        },
        "calculation_id": None,
        "calculation_version": None,
        "reviewer_notes": "Created from accepted customer revision; not a regenerated estimate.",
        "created_at": now,
        "updated_at": now,
        "approved_at": None,
    }
    conn.execute(
        """
        INSERT INTO scope_items (id, project_id, tenant_id, company_id, extraction_run_id, trade_code,
            trade_module_version, trade_schema_version, category_code, description,
            location, specification_section, assembly_designation, material_or_substrate,
            existing_condition, proposed_work, quantity, unit, quantity_basis,
            raw_quantity_inputs, extraction_confidence, conflict_status, review_status,
            blocking_issues, assumptions, exclusions, trade_data, original_provider_candidate,
            calculation_id, calculation_version, reviewer_notes, created_at, updated_at, approved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scope_item["id"], scope_item["project_id"], scope_item["tenant_id"], scope_item["company_id"], scope_item["extraction_run_id"],
            scope_item["trade_code"], scope_item["trade_module_version"],
            scope_item["trade_schema_version"], scope_item["category_code"],
            scope_item["description"], scope_item["location"],
            scope_item["specification_section"], scope_item["assembly_designation"],
            scope_item["material_or_substrate"], scope_item["existing_condition"],
            scope_item["proposed_work"], scope_item["quantity"], scope_item["unit"],
            scope_item["quantity_basis"], _json_dumps(scope_item["raw_quantity_inputs"]),
            scope_item["extraction_confidence"], scope_item["conflict_status"],
            scope_item["review_status"], _json_dumps(scope_item["blocking_issues"]),
            _json_dumps(scope_item["assumptions"]), _json_dumps(scope_item["exclusions"]),
            _json_dumps(scope_item["trade_data"]), _json_dumps(scope_item["original_provider_candidate"]),
            scope_item["calculation_id"], scope_item["calculation_version"],
            scope_item["reviewer_notes"], scope_item["created_at"], scope_item["updated_at"],
            scope_item["approved_at"],
        ),
    )
    return scope_item


def decide_revision_request(
    project_id: UUID,
    request_id: UUID,
    *,
    decision: str,
    reviewer: str = "staff",
    notes: str | None = None,
) -> dict[str, Any]:
    allowed = {"accepted", "rejected", "needs_clarification"}
    if decision not in allowed:
        raise RevisionDecisionError("invalid_decision", "Unsupported revision decision")
    now = _now()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM customer_revision_requests WHERE project_id=? AND id=?",
            (str(project_id), str(request_id)),
        ).fetchone()
        if row is None:
            raise RevisionDecisionError("not_found", "Revision request not found")
        existing = _row(row)
        if existing.get("status") != "open":
            raise RevisionDecisionError("already_decided", "Revision request has already been decided")
        status = {
            "accepted": "accepted_for_rescope",
            "rejected": "rejected",
            "needs_clarification": "needs_customer_clarification",
        }[decision]
        payload = _decision_payload(existing, decision=decision, reviewer=reviewer, notes=notes)
        rescope_blocker = None
        if decision == "accepted":
            rescope_blocker = _create_rescope_blocker(conn, project_id, existing)
            payload["review_decision"]["rescope_blocker_scope_item_id"] = rescope_blocker["id"]
        result = conn.execute(
            """
            UPDATE customer_revision_requests
            SET status=?, payload=?, updated_at=?
            WHERE project_id=? AND id=? AND status='open'
            """,
            (status, _dumps(payload), now, str(project_id), str(request_id)),
        )
        if result.rowcount != 1:
            conn.rollback()
            raise RevisionDecisionError("already_decided", "Revision request has already been decided")
        conn.commit()
    return {
        **existing,
        "status": status,
        "payload": payload,
        "rescope_blocker": rescope_blocker,
        "updated_at": now,
        "delivery_ready": False,
        "estimate_regenerated": False,
        "external_message_sent": False,
    }


def _scope_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key in ("raw_quantity_inputs", "blocking_issues", "assumptions", "exclusions", "trade_data", "original_provider_candidate"):
        data[key] = _loads(data.get(key))
    return data


def _get_revision_request(conn: Any, project_id: UUID, request_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM customer_revision_requests WHERE project_id=? AND id=?",
        (str(project_id), str(request_id)),
    ).fetchone()
    return _row(row) if row else None


def _get_scope_item_for_update(conn: Any, project_id: UUID, scope_item_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM scope_items WHERE project_id=? AND id=?",
        (str(project_id), scope_item_id),
    ).fetchone()
    return _scope_row(row) if row else None


def _next_rescope_version_number(conn: Any, request_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(version_number), 0) FROM customer_revision_rescope_versions WHERE customer_revision_request_id=?",
        (request_id,),
    ).fetchone()
    return int(row[0]) + 1


def _rescope_version_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key in ("before_snapshot", "after_snapshot", "changed_items", "readiness_snapshot"):
        data[key] = _loads(data.get(key))
    return data


def _insert_rescope_version(
    conn: Any,
    *,
    project_id: UUID,
    request_id: str,
    blocker_scope_item_id: str,
    actor: str,
    notes: str | None,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    changed_items: list[dict[str, Any]],
    readiness_snapshot: dict[str, Any],
) -> dict[str, Any]:
    version_id = str(uuid4())
    now = _now()
    version_number = _next_rescope_version_number(conn, request_id)
    conn.execute(
        """
        INSERT INTO customer_revision_rescope_versions (
            id, project_id, customer_revision_request_id, blocker_scope_item_id,
            version_number, status, actor, notes, before_snapshot, after_snapshot,
            changed_items, readiness_snapshot, created_at
        ) VALUES (?, ?, ?, ?, ?, 'resolved', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_id, str(project_id), request_id, blocker_scope_item_id, version_number,
            actor, notes, _json_dumps(before_snapshot), _json_dumps(after_snapshot),
            _json_dumps(changed_items), _json_dumps(readiness_snapshot), now,
        ),
    )
    row = conn.execute(
        "SELECT * FROM customer_revision_rescope_versions WHERE id=?",
        (version_id,),
    ).fetchone()
    return _rescope_version_row(row)


def list_revision_rescope_versions(project_id: UUID, request_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM customer_revision_rescope_versions WHERE project_id=? AND customer_revision_request_id=? ORDER BY version_number ASC",
            (str(project_id), str(request_id)),
        ).fetchall()
    return [_rescope_version_row(row) for row in rows]


def _transactional_rescope_readiness_snapshot(
    conn: Any,
    project_id: UUID,
    blocker_scope_item_id: str,
) -> dict[str, Any]:
    """Build a transaction-local readiness snapshot for the just-resolved blocker.

    The full public readiness gate is rerun after commit for the API response, but
    this snapshot is inserted atomically with the blocker/request updates so the
    durable version row is never missing if post-commit readiness evaluation fails.
    """
    open_blocker_count = conn.execute(
        """
        SELECT COUNT(*) FROM scope_items
        WHERE project_id=? AND blocking_issues IS NOT NULL AND blocking_issues NOT IN ('', '[]', '{}')
        """,
        (str(project_id),),
    ).fetchone()[0]
    blocker_row = conn.execute(
        "SELECT id, review_status, conflict_status, blocking_issues FROM scope_items WHERE project_id=? AND id=?",
        (str(project_id), blocker_scope_item_id),
    ).fetchone()
    blocker_state = dict(blocker_row) if blocker_row else {}
    blocker_state["blocking_issues"] = _loads(blocker_state.get("blocking_issues"))
    return {
        "source": "customer_revision_rescope_resolution_v1",
        "generated_at": _now(),
        "project_id": str(project_id),
        "status": "blocked" if open_blocker_count else "no_scope_blockers_from_rescope_snapshot",
        "open_scope_blocker_count": int(open_blocker_count),
        "resolved_blocker_scope_item": blocker_state,
        "customer_delivery_ready": False,
        "customer_delivery_gate": "Final construction estimate delivery remains approval-gated.",
    }


def resolve_revision_rescope(
    project_id: UUID,
    request_id: UUID,
    *,
    actor: str = "staff",
    notes: str | None = None,
) -> dict[str, Any]:
    """Resolve an accepted customer revision blocker and snapshot the rescope version.

    This is an internal workflow action only: it clears the accepted-revision
    blocker after rescope/reprice work is represented, snapshots before/after
    scope state, reruns readiness, and never sends messages, regenerates final
    estimates, or unlocks customer delivery.
    """
    now = _now()
    with get_connection() as conn:
        request = _get_revision_request(conn, project_id, request_id)
        if request is None:
            raise RevisionDecisionError("not_found", "Revision request not found")
        if request.get("status") == "rescope_resolved":
            raise RevisionDecisionError("already_resolved", "Revision rescope has already been resolved")
        if request.get("status") != "accepted_for_rescope":
            raise RevisionDecisionError("not_accepted_for_rescope", "Revision request is not accepted for rescope")
        payload = dict(request.get("payload") or {})
        review_decision = payload.get("review_decision") if isinstance(payload.get("review_decision"), dict) else {}
        blocker_scope_item_id = review_decision.get("rescope_blocker_scope_item_id")
        if not blocker_scope_item_id:
            raise RevisionDecisionError("rescope_blocker_missing", "Accepted revision has no rescope blocker")
        scope_item = _get_scope_item_for_update(conn, project_id, blocker_scope_item_id)
        if scope_item is None:
            raise RevisionDecisionError("rescope_blocker_missing", "Rescope blocker scope item not found")

        blockers = scope_item.get("blocking_issues") or []
        remaining_blockers = []
        removed_blockers = []
        for blocker in blockers:
            if (
                isinstance(blocker, dict)
                and blocker.get("code") == "customer_revision_rescope_required"
                and blocker.get("customer_revision_request_id") == str(request_id)
            ):
                removed_blockers.append(blocker)
            else:
                remaining_blockers.append(blocker)
        if not removed_blockers:
            raise RevisionDecisionError("already_resolved", "Rescope blocker is already resolved")

        before_snapshot = {
            "customer_revision_request": request,
            "scope_item": scope_item,
        }
        trade_data = dict(scope_item.get("trade_data") or {})
        trade_data.update({
            "revision_status": "rescope_resolved",
            "rescope_resolved_at": now,
            "rescope_resolved_by": actor,
            "delivery_ready": False,
        })
        new_review_status = "blocked" if remaining_blockers else "pending"
        new_conflict_status = "blocking" if remaining_blockers else "none"
        reviewer_notes = notes or "Customer revision rescope blocker resolved; readiness rerun required."
        conn.execute(
            """
            UPDATE scope_items
            SET blocking_issues=?, trade_data=?, review_status=?, conflict_status=?, reviewer_notes=?, updated_at=?
            WHERE project_id=? AND id=?
            """,
            (
                _json_dumps(remaining_blockers), _json_dumps(trade_data), new_review_status,
                new_conflict_status, reviewer_notes, now, str(project_id), blocker_scope_item_id,
            ),
        )
        payload["rescope_resolution"] = {
            "resolved_at": now,
            "actor": actor,
            "notes": notes,
            "blocker_scope_item_id": blocker_scope_item_id,
            "delivery_ready": False,
        }
        update_result = conn.execute(
            """
            UPDATE customer_revision_requests
            SET status='rescope_resolved', payload=?, updated_at=?, resolved_at=?
            WHERE project_id=? AND id=? AND status='accepted_for_rescope'
            """,
            (_dumps(payload), now, now, str(project_id), str(request_id)),
        )
        if update_result.rowcount != 1:
            conn.rollback()
            raise RevisionDecisionError("already_resolved", "Revision rescope has already been resolved")
        updated_scope_item = _get_scope_item_for_update(conn, project_id, blocker_scope_item_id)
        updated_request = _get_revision_request(conn, project_id, request_id)
        after_snapshot = {
            "customer_revision_request": updated_request,
            "scope_item": updated_scope_item,
        }
        changed_items = [{
            "scope_item_id": blocker_scope_item_id,
            "change_type": "customer_revision_rescope_resolved",
            "removed_blocker_codes": [b.get("code") for b in removed_blockers if isinstance(b, dict)],
            "previous_review_status": scope_item.get("review_status"),
            "new_review_status": updated_scope_item.get("review_status") if updated_scope_item else None,
            "customer_revision_request_id": str(request_id),
        }]
        transaction_readiness = _transactional_rescope_readiness_snapshot(
            conn, project_id, blocker_scope_item_id
        )
        version = _insert_rescope_version(
            conn,
            project_id=project_id,
            request_id=str(request_id),
            blocker_scope_item_id=blocker_scope_item_id,
            actor=actor,
            notes=notes,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            changed_items=changed_items,
            readiness_snapshot=transaction_readiness,
        )
        conn.commit()

    readiness = evaluate_estimate_readiness(project_id)
    return {
        "project_id": str(project_id),
        "customer_revision_request_id": str(request_id),
        "status": "rescope_resolved",
        "version": version,
        "changed_items": changed_items,
        "readiness": readiness,
        "customer_delivery_ready": False,
        "delivery_ready": False,
        "estimate_regenerated": False,
        "external_message_sent": False,
    }
