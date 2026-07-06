"""Customer revision request API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.customer_revisions import create_revision_requests, list_revision_requests
from app.database import get_project

revision_router = APIRouter(prefix="/projects", tags=["customer-revisions"])


class RevisionParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="customer_message", max_length=64)
    actor: str = Field(default="customer", max_length=128)
    text: str = Field(min_length=1, max_length=10000)


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@revision_router.get("/{project_id}/customer-revisions")
def list_project_customer_revisions(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    items = list_revision_requests(project_id)
    return {"items": items, "total": len(items)}


@revision_router.post("/{project_id}/customer-revisions/parse")
def parse_project_customer_revisions(
    project_id: UUID,
    body: RevisionParseRequest,
) -> dict[str, Any]:
    """Parse and log customer revision feedback internally.

    This does not send a message, regenerate an estimate, or deliver revised work.
    """
    _require_project(project_id)
    return create_revision_requests(
        project_id,
        source=body.source,
        actor=body.actor,
        raw_text=body.text,
    )
