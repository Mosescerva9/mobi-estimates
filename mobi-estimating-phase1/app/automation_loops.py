"""Automation Loop Runner v1 for Mobi estimating builds.

Video-derived loop model:

trigger -> action -> observation -> stop condition

This runner is intentionally deterministic and backend-local. It runs the safe
internal draft stages that already exist and records each pass. It does not send
messages, create final prices, approve estimates, or deliver customer output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.boe import draft_boe
from app.coverage_db import list_coverage_rows, validate_coverage
from app.database import get_connection
from app.generic_pricing import assign_generic_pricing_methods
from app.generic_scope import draft_generic_scope_candidates
from app.qa_findings import draft_qa_findings, list_qa_findings
from app.quantity_requirements import draft_quantity_requirements, list_quantity_requirements
from app.trade_census import draft_trade_census

LOOP_NAME = "estimate_build_loop_v1"
MAX_PASSES = 3


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
    for key in ("trigger", "stop_condition", "observation", "actions", "payload"):
        data[key] = _loads(data.get(key))
    return data


def _insert_loop_run(project_id: UUID, *, trigger: dict[str, Any], stop_condition: dict[str, Any]) -> str:
    run_id = str(uuid4())
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO automation_loop_runs (id, project_id, loop_name, status,
                trigger, stop_condition, observation, actions, pass_count,
                created_at, updated_at)
            VALUES (?, ?, ?, 'running', ?, ?, '{}', '[]', 0, ?, ?)
            """,
            (run_id, str(project_id), LOOP_NAME, _dumps(trigger), _dumps(stop_condition), now, now),
        )
        conn.commit()
    return run_id


def _finish_loop_run(
    run_id: str,
    *,
    status: str,
    observation: dict[str, Any],
    actions: list[dict[str, Any]],
    pass_count: int,
) -> dict[str, Any]:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE automation_loop_runs
            SET status=?, observation=?, actions=?, pass_count=?, updated_at=?, completed_at=?
            WHERE id=?
            """,
            (status, _dumps(observation), _dumps(actions), pass_count, now, now, run_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM automation_loop_runs WHERE id=?", (run_id,)).fetchone()
    return _row(row)


def list_automation_loop_runs(project_id: UUID) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM automation_loop_runs WHERE project_id=? "
            "ORDER BY created_at DESC, id DESC",
            (str(project_id),),
        ).fetchall()
    return [_row(row) for row in rows]


def _observe(project_id: UUID, boe: dict[str, Any] | None = None) -> dict[str, Any]:
    coverage = list_coverage_rows(project_id)
    validation = validate_coverage(project_id)
    findings = list_qa_findings(project_id)
    quantity_requirements = list_quantity_requirements(project_id)
    boe_packet = boe or draft_boe(project_id)
    open_findings = [row for row in findings if row.get("status") == "open"]
    open_quantities = [row for row in quantity_requirements if row.get("status") == "open"]
    return {
        "coverage_count": len(coverage),
        "coverage_complete": validation["complete"],
        "coverage_critical_count": validation["critical_count"],
        "coverage_major_count": validation["major_count"],
        "open_qa_finding_count": len(open_findings),
        "critical_qa_finding_count": sum(1 for row in open_findings if row.get("severity") == "critical"),
        "open_quantity_requirement_count": len(open_quantities),
        "boe_status": boe_packet.get("status"),
        "boe_delivery_ready": boe_packet.get("delivery_ready"),
        "delivery_blockers": boe_packet.get("delivery_blockers", []),
        "stop_reason": None,
    }


def _run_pass(project_id: UUID, pass_number: int) -> dict[str, Any]:
    census = draft_trade_census(project_id)
    scope = draft_generic_scope_candidates(project_id)
    pricing = assign_generic_pricing_methods(project_id)
    quantities = draft_quantity_requirements(project_id)
    qa = draft_qa_findings(project_id)
    boe = draft_boe(project_id)
    return {
        "pass": pass_number,
        "actions": [
            {"name": "coverage_census", "created_count": census.get("created_count", 0), "updated_count": census.get("updated_count", 0)},
            {"name": "generic_scope", "created_count": scope.get("created_count", 0), "skipped_count": scope.get("skipped_count", 0)},
            {"name": "generic_pricing_methods", "updated_count": pricing.get("updated_count", 0)},
            {"name": "quantity_requirements", "created_count": quantities.get("created_count", 0), "skipped_count": quantities.get("skipped_count", 0)},
            {"name": "qa_findings", "finding_count": qa.get("finding_count", 0), "critical_count": qa.get("critical_count", 0)},
            {"name": "boe_draft", "status": boe.get("status"), "delivery_ready": boe.get("delivery_ready")},
        ],
        "observation": _observe(project_id, boe),
    }


def _new_artifact_count(pass_result: dict[str, Any]) -> int:
    total = 0
    for action in pass_result["actions"]:
        for key in ("created_count", "updated_count"):
            value = action.get(key)
            if isinstance(value, int):
                total += value
    return total


def run_estimate_build_loop(project_id: UUID, *, max_passes: int = MAX_PASSES) -> dict[str, Any]:
    max_passes = max(1, min(max_passes, 10))
    trigger = {
        "type": "project_estimate_build_requested",
        "source": "automation_loop_runner_v1",
        "message": "Run deterministic internal draft stages until artifacts stabilize or blockers remain.",
    }
    stop_condition = {
        "hard_pass_cap": max_passes,
        "objective_checks": [
            "BOE draft exists and remains delivery_ready=false until final approval behavior exists.",
            "No new draft artifacts are created/updated on the latest pass, or max passes reached.",
            "Open QA findings and quantity requirements are exposed as blockers, not hidden.",
        ],
    }
    run_id = _insert_loop_run(project_id, trigger=trigger, stop_condition=stop_condition)
    pass_results: list[dict[str, Any]] = []
    status = "completed_with_blockers"
    observation: dict[str, Any] = {}
    for pass_number in range(1, max_passes + 1):
        result = _run_pass(project_id, pass_number)
        pass_results.append(result)
        observation = result["observation"]
        created_or_updated = _new_artifact_count(result)
        if created_or_updated == 0:
            observation["stop_reason"] = "artifact_stabilized"
            break
        if pass_number == max_passes:
            observation["stop_reason"] = "max_passes_reached"
            break

    if (
        observation.get("coverage_complete")
        and observation.get("critical_qa_finding_count") == 0
        and observation.get("open_quantity_requirement_count") == 0
    ):
        status = "completed_ready_for_internal_review"

    run = _finish_loop_run(
        run_id,
        status=status,
        observation=observation,
        actions=pass_results,
        pass_count=len(pass_results),
    )
    return {"run": run, "latest_observation": observation, "passes": pass_results}
