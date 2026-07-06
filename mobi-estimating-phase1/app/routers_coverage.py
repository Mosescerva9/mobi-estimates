"""Trade Coverage Matrix API.

Routes are internal/backend-local controls for the automation-first all-trade
coverage layer. They do not deliver estimates or send customer messages.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.coverage_db import (
    create_coverage_row,
    get_coverage_row,
    list_coverage_rows,
    update_coverage_row,
    validate_coverage,
)
from app.database import get_project
from app.generic_scope import draft_generic_scope_candidates
from app.trade_census import draft_trade_census

coverage_router = APIRouter(prefix="/projects", tags=["coverage"])

CoverageDisposition = Literal[
    "undispositioned",
    "included_module",
    "included_generic",
    "included_quote",
    "allowance",
    "customer_confirmation_needed",
    "excluded_by_customer",
    "excluded_by_mobi",
    "not_applicable",
    "blocked_needs_info",
    "blocked_needs_source_data",
]
CoverageStatus = Literal["draft", "ready", "blocked", "excluded", "needs_customer", "complete"]


class CoverageRowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_code: str = Field(min_length=1, max_length=64)
    trade_name: str = Field(min_length=1, max_length=128)
    csi_divisions: list[str] = Field(default_factory=list)
    detected_from: list[str] = Field(default_factory=list)
    disposition: CoverageDisposition = "undispositioned"
    basis_note: str | None = Field(default=None, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: CoverageStatus = "draft"
    blockers: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class CoverageRowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_name: str | None = Field(default=None, min_length=1, max_length=128)
    csi_divisions: list[str] | None = None
    detected_from: list[str] | None = None
    disposition: CoverageDisposition | None = None
    basis_note: str | None = Field(default=None, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    status: CoverageStatus | None = None
    blockers: list[str] | None = None
    evidence_refs: list[dict[str, Any]] | None = None


def _require_project(project_id: UUID) -> None:
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "trade_code": row["trade_code"],
        "trade_name": row["trade_name"],
        "csi_divisions": row.get("csi_divisions") or [],
        "detected_from": row.get("detected_from") or [],
        "disposition": row.get("disposition"),
        "basis_note": row.get("basis_note"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "blockers": row.get("blockers") or [],
        "evidence_refs": row.get("evidence_refs") or [],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@coverage_router.get("/{project_id}/coverage")
def list_project_coverage(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    rows = list_coverage_rows(project_id)
    return {"items": [_public(row) for row in rows], "total": len(rows)}


@coverage_router.post("/{project_id}/coverage", status_code=201)
def create_project_coverage_row(project_id: UUID, body: CoverageRowCreate) -> dict[str, Any]:
    _require_project(project_id)
    try:
        row = create_coverage_row(project_id, body.model_dump(mode="json"))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Coverage row already exists for this project and trade",
        ) from exc
    return _public(row)


@coverage_router.patch("/{project_id}/coverage/{row_id}")
def update_project_coverage_row(
    project_id: UUID, row_id: UUID, body: CoverageRowUpdate
) -> dict[str, Any]:
    _require_project(project_id)
    row = update_coverage_row(
        project_id,
        row_id,
        body.model_dump(mode="json", exclude_unset=True),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Coverage row not found")
    return _public(row)


@coverage_router.post("/{project_id}/coverage/draft")
def draft_project_coverage(project_id: UUID) -> dict[str, Any]:
    """Draft coverage rows from processed sheet/document signals.

    This is backend-local automation only: it does not price, message customers,
    send RFQs, or deliver estimate packages.
    """
    _require_project(project_id)
    result = draft_trade_census(project_id)
    return {**result, "rows": [_public(row) for row in result["rows"]]}


@coverage_router.post("/{project_id}/coverage/generic-scope/draft")
def draft_project_generic_scope(project_id: UUID) -> dict[str, Any]:
    """Draft generic scope items from coverage rows.

    This creates blocked/pending internal scope candidates only. It does not price,
    send messages, request quotes, or deliver customer-facing estimates.
    """
    _require_project(project_id)
    return draft_generic_scope_candidates(project_id)


@coverage_router.get("/{project_id}/coverage/validate")
def validate_project_coverage(project_id: UUID) -> dict[str, Any]:
    _require_project(project_id)
    return validate_coverage(project_id)
