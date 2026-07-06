"""Automation loop runner API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.automation_loops import list_automation_loop_runs, run_estimate_build_loop
from app.database import get_project

loops_router = APIRouter(prefix="/projects", tags=["automation-loops"])


class EstimateBuildLoopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_passes: int = Field(default=3, ge=1, le=10)


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@loops_router.get("/{project_id}/automation-loops")
def list_project_automation_loops(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    items = list_automation_loop_runs(project_id)
    return {"items": items, "total": len(items)}


@loops_router.post("/{project_id}/automation-loops/estimate-build/run")
def run_project_estimate_build_loop(
    project_id: UUID,
    body: EstimateBuildLoopRequest | None = None,
) -> dict[str, Any]:
    """Run safe internal estimate-build drafting stages as a bounded loop.

    Trigger: project estimate build requested.
    Action: deterministic draft stages.
    Stop condition: artifacts stabilize or max_passes is reached.

    This does not send messages, approve, price, or deliver final construction estimates.
    """
    _require_project(project_id)
    req = body or EstimateBuildLoopRequest()
    return run_estimate_build_loop(project_id, max_passes=req.max_passes)
