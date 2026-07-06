"""Estimate readiness gate API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.database import get_project
from app.estimate_readiness import evaluate_estimate_readiness

readiness_router = APIRouter(prefix="/projects", tags=["estimate-readiness"])


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@readiness_router.get("/{project_id}/estimate-readiness")
def get_project_estimate_readiness(project_id: UUID) -> dict[str, Any]:
    """Evaluate internal owner-review readiness.

    This does not approve, publish, price, send, or deliver a customer estimate.
    """
    _require_project(project_id)
    return evaluate_estimate_readiness(project_id)
