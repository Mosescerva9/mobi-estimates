"""Internal clarification package API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.clarification_package import build_clarification_package
from app.database import get_project

clarification_router = APIRouter(prefix="/projects", tags=["clarifications"])


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@clarification_router.get("/{project_id}/clarifications/package")
def get_project_clarification_package(project_id: UUID) -> dict[str, Any]:
    """Return internal clarification candidates.

    This endpoint does not approve, publish, send, email, bill, or deliver a
    customer-facing construction estimate.
    """
    _require_project(project_id)
    return build_clarification_package(project_id)
