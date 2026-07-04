"""Phase 5 API: client-facing proposal generation, lifecycle, and exports.

All routes under ``/api/v1/projects/{project_id}/proposals``. Exports render sell
prices + scope only — never internal cost, margins, rates, or filesystem paths.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

from app import proposals_db
from app.database import get_project
from app.proposals import render, service
from app.proposals.schemas import (
    AcceptRequest,
    DeclineRequest,
    IssueRequest,
    ProposalCreate,
    RegenerateRequest,
)

proposals_router = APIRouter(prefix="/projects", tags=["proposals"])


def _require_project(project_id: UUID) -> dict:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_proposal(project_id: UUID, proposal_id: UUID) -> dict:
    proposal = proposals_db.get_proposal(project_id, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


def _require_version(project_id: UUID, proposal_id: UUID, version_id: UUID) -> dict:
    version = proposals_db.get_version(version_id)
    if (version is None or version["project_id"] != str(project_id)
            or version["proposal_id"] != str(proposal_id)):
        raise HTTPException(status_code=404, detail="Proposal version not found")
    return version


def _http(exc: service.ProposalError) -> HTTPException:
    code_map = {
        "estimate_not_found": 404, "estimate_version_not_found": 404, "not_found": 404,
        "no_version": 404, "estimate_not_approved": 409, "no_approved_version": 409,
        "not_draft": 409, "not_issued": 409, "reason_required": 422,
    }
    return HTTPException(status_code=code_map.get(exc.code, 400), detail=exc.message)


@proposals_router.post("/{project_id}/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal(project_id: UUID, body: ProposalCreate) -> dict[str, Any]:
    _require_project(project_id)
    try:
        return service.create_proposal(project_id, body.model_dump())
    except service.ProposalError as exc:
        raise _http(exc)


@proposals_router.get("/{project_id}/proposals")
def list_proposals(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    return {"items": proposals_db.list_proposals(project_id)}


@proposals_router.get("/{project_id}/proposals/{proposal_id}")
def get_proposal(project_id: UUID, proposal_id: UUID) -> dict[str, Any]:
    proposal = _require_proposal(project_id, proposal_id)
    return {**proposal, "versions": proposals_db.list_versions(proposal_id)}


@proposals_router.get("/{project_id}/proposals/{proposal_id}/versions")
def list_versions(project_id: UUID, proposal_id: UUID) -> dict[str, Any]:
    _require_proposal(project_id, proposal_id)
    return {"items": proposals_db.list_versions(proposal_id)}


@proposals_router.get("/{project_id}/proposals/{proposal_id}/versions/{version_id}")
def get_version(project_id: UUID, proposal_id: UUID, version_id: UUID) -> dict[str, Any]:
    _require_version(project_id, proposal_id, version_id)
    version = service.get_version_public(project_id, str(version_id))
    return {**version, "line_items": proposals_db.get_line_items(str(version_id))}


@proposals_router.post("/{project_id}/proposals/{proposal_id}/versions/{version_id}/issue")
def issue(project_id: UUID, proposal_id: UUID, version_id: UUID,
          body: IssueRequest | None = None) -> dict[str, Any]:
    _require_version(project_id, proposal_id, version_id)
    req = body or IssueRequest()
    try:
        return service.issue(project_id, str(version_id),
                             proposal_number=req.proposal_number, actor=req.actor)
    except service.ProposalError as exc:
        raise _http(exc)


@proposals_router.post("/{project_id}/proposals/{proposal_id}/versions/{version_id}/accept")
def accept(project_id: UUID, proposal_id: UUID, version_id: UUID,
           body: AcceptRequest | None = None) -> dict[str, Any]:
    _require_version(project_id, proposal_id, version_id)
    req = body or AcceptRequest()
    try:
        return service.accept(project_id, str(version_id), actor=req.actor, notes=req.notes)
    except service.ProposalError as exc:
        raise _http(exc)


@proposals_router.post("/{project_id}/proposals/{proposal_id}/versions/{version_id}/decline")
def decline(project_id: UUID, proposal_id: UUID, version_id: UUID,
            body: DeclineRequest) -> dict[str, Any]:
    _require_version(project_id, proposal_id, version_id)
    try:
        return service.decline(project_id, str(version_id), actor=body.actor,
                               reason=body.reason)
    except service.ProposalError as exc:
        raise _http(exc)


@proposals_router.post("/{project_id}/proposals/{proposal_id}/regenerate")
def regenerate(project_id: UUID, proposal_id: UUID,
               body: RegenerateRequest | None = None) -> dict[str, Any]:
    _require_proposal(project_id, proposal_id)
    req = body or RegenerateRequest()
    try:
        return service.regenerate(
            project_id, proposal_id,
            estimate_version_id=req.estimate_version_id, actor=req.actor)
    except service.ProposalError as exc:
        raise _http(exc)


@proposals_router.get("/{project_id}/proposals/{proposal_id}/versions/{version_id}/review-events")
def review_events(project_id: UUID, proposal_id: UUID, version_id: UUID) -> dict[str, Any]:
    _require_version(project_id, proposal_id, version_id)
    return {"items": proposals_db.list_review_events(str(version_id))}


# --- Exports (client-facing; no cost/paths/secrets) -----------------------
def _version_and_lines(project_id, proposal_id, version_id):
    _require_version(project_id, proposal_id, version_id)
    version = proposals_db.get_version(str(version_id))
    return version, proposals_db.get_line_items(str(version_id))


@proposals_router.get("/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.json")
def export_json(project_id: UUID, proposal_id: UUID, version_id: UUID) -> PlainTextResponse:
    version, lines = _version_and_lines(project_id, proposal_id, version_id)
    return PlainTextResponse(render.proposal_json(version, lines),
                             media_type="application/json")


@proposals_router.get("/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.md")
def export_md(project_id: UUID, proposal_id: UUID, version_id: UUID) -> PlainTextResponse:
    version, lines = _version_and_lines(project_id, proposal_id, version_id)
    return PlainTextResponse(render.proposal_markdown(version, lines),
                             media_type="text/markdown")


@proposals_router.get("/{project_id}/proposals/{proposal_id}/versions/{version_id}/export.html")
def export_html(project_id: UUID, proposal_id: UUID, version_id: UUID) -> PlainTextResponse:
    version, lines = _version_and_lines(project_id, proposal_id, version_id)
    return PlainTextResponse(render.proposal_html(version, lines), media_type="text/html")
