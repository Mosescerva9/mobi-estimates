"""Internal owner-review package API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.database import get_project
from app.owner_review import build_owner_review_package

owner_review_router = APIRouter(prefix="/projects", tags=["owner-review"])


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@owner_review_router.get("/{project_id}/owner-review/package")
def get_project_owner_review_package(project_id: UUID) -> dict[str, Any]:
    """Return internal owner-review package.

    This endpoint does not approve, publish, send, email, bill, or deliver a
    customer-facing construction estimate.
    """
    _require_project(project_id)
    return build_owner_review_package(project_id)
