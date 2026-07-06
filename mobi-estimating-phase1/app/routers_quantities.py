"""Quantity requirements API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.database import get_project
from app.quantity_requirements import draft_quantity_requirements, list_quantity_requirements

quantity_router = APIRouter(prefix="/projects", tags=["quantity-requirements"])


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@quantity_router.get("/{project_id}/quantity-requirements")
def list_project_quantity_requirements(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    items = list_quantity_requirements(project_id)
    return {"items": items, "total": len(items)}


@quantity_router.post("/{project_id}/quantity-requirements/draft")
def draft_project_quantity_requirements(project_id: UUID) -> dict[str, Any]:
    """Draft internal quantity requirements from missing-quantity scope blockers.

    This does not generate quantities, price estimates, or deliver customer output.
    """
    _require_project(project_id)
    return draft_quantity_requirements(project_id)
