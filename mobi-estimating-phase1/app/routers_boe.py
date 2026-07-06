"""Basis of Estimate draft API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.boe import draft_boe
from app.database import get_project

boe_router = APIRouter(prefix="/projects", tags=["boe"])


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@boe_router.get("/{project_id}/boe/draft")
def get_project_boe_draft(project_id: UUID) -> dict[str, Any]:
    """Return deterministic draft BOE JSON.

    This endpoint does not create a PDF, approve an estimate, send a message, or
    deliver customer-facing final estimate content.
    """
    _require_project(project_id)
    return draft_boe(project_id)
