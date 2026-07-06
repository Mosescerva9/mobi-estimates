"""QA Findings Log API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.database import get_project
from app.qa_findings import draft_qa_findings, list_qa_findings

qa_router = APIRouter(prefix="/projects", tags=["qa"])


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@qa_router.get("/{project_id}/qa/findings")
def list_project_qa_findings(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    items = list_qa_findings(project_id)
    return {"items": items, "total": len(items)}


@qa_router.post("/{project_id}/qa/findings/draft")
def draft_project_qa_findings(project_id: UUID) -> dict[str, Any]:
    """Regenerate automated internal QA findings.

    This is an internal log generator. It does not approve, price, send, or deliver
    a customer estimate.
    """
    _require_project(project_id)
    return draft_qa_findings(project_id)
