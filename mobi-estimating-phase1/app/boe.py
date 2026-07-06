"""Basis of Estimate Draft Generator v1.

Produces a deterministic BOE summary from project, sheet, coverage, scope, and QA
state. This is a draft data packet only: no PDF export, customer delivery, email,
or final-estimate approval occurs here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.assumptions_register import build_assumptions_register
from app.coverage_db import list_coverage_rows, validate_coverage
from app.database import get_project, list_sheets
from app.extraction_db import list_scope_items
from app.qa_findings import list_qa_findings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_all_scope_items(project_id: UUID, *, page_size: int = 10000) -> tuple[list[dict[str, Any]], int]:
    """Page through every scope item so BOE counts align with readiness/register."""
    all_items: list[dict[str, Any]] = []
    offset = 0
    total = 0
    while True:
        page, total = list_scope_items(project_id, filters={}, limit=page_size, offset=offset)
        all_items.extend(page)
        if len(all_items) >= total or not page:
            break
        offset += len(page)
    return all_items, total


def _trade_summary(row: dict[str, Any], scope_counts: dict[str, int]) -> dict[str, Any]:
    return {
        "trade_code": row["trade_code"],
        "trade_name": row["trade_name"],
        "csi_divisions": row.get("csi_divisions") or [],
        "disposition": row.get("disposition"),
        "status": row.get("status"),
        "confidence": row.get("confidence"),
        "detected_from": row.get("detected_from") or [],
        "basis_note": row.get("basis_note"),
        "scope_item_count": scope_counts.get(row["trade_code"], 0),
        "blockers": row.get("blockers") or [],
    }


def draft_boe(project_id: UUID) -> dict[str, Any]:
    project = get_project(project_id)
    sheets, sheet_total = list_sheets(project_id, limit=1000, offset=0)
    coverage = list_coverage_rows(project_id)
    scope_items, scope_total = _list_all_scope_items(project_id)
    findings = list_qa_findings(project_id)
    validation = validate_coverage(project_id)
    register = build_assumptions_register(project_id)

    scope_counts: dict[str, int] = {}
    assumptions: list[str] = []
    exclusions: list[str] = []
    open_questions: list[str] = []
    for item in scope_items:
        if item.get("review_status") != "rejected":
            scope_counts[item["trade_code"]] = scope_counts.get(item["trade_code"], 0) + 1
        for assumption in item.get("assumptions") or []:
            text = assumption.get("text") if isinstance(assumption, dict) else str(assumption)
            if text and text not in assumptions:
                assumptions.append(text)
        for exclusion in item.get("exclusions") or []:
            text = exclusion.get("text") if isinstance(exclusion, dict) else str(exclusion)
            if text and text not in exclusions:
                exclusions.append(text)
        for blocker in item.get("blocking_issues") or []:
            msg = blocker.get("message") if isinstance(blocker, dict) else str(blocker)
            if msg and msg not in open_questions:
                open_questions.append(msg)

    critical = [f for f in findings if f.get("severity") == "critical" and f.get("status") == "open"]
    major = [f for f in findings if f.get("severity") == "major" and f.get("status") == "open"]
    return {
        "project_id": str(project_id),
        "project_name": project.get("name") if project else None,
        "generated_at": _now(),
        "status": "draft",
        "delivery_ready": False,
        "delivery_blockers": [
            "BOE v1 is an internal draft packet only; it is not a final construction estimate.",
            "Pricing, quantities, final QA, approval, and customer delivery are outside this endpoint.",
        ],
        "document_basis": {
            "sheet_count": sheet_total,
            "processed_sheet_count": sum(1 for sheet in sheets if sheet.get("processing_status") == "complete"),
            "ocr_required_count": sum(1 for sheet in sheets if sheet.get("requires_ocr")),
            "review_required_count": sum(1 for sheet in sheets if sheet.get("requires_review")),
        },
        "coverage_summary": {
            "trade_count": len(coverage),
            "complete": validation["complete"],
            "critical_count": validation["critical_count"],
            "major_count": validation["major_count"],
            "trades": [_trade_summary(row, scope_counts) for row in coverage],
        },
        "scope_summary": {
            "scope_item_count": scope_total,
            "blocked_scope_item_count": sum(1 for item in scope_items if item.get("review_status") == "blocked"),
            "pending_scope_item_count": sum(1 for item in scope_items if item.get("review_status") == "pending"),
        },
        "qa_summary": {
            "open_finding_count": len([f for f in findings if f.get("status") == "open"]),
            "critical_count": len(critical),
            "major_count": len(major),
            "top_findings": [
                {
                    "code": f["code"],
                    "severity": f["severity"],
                    "trade_code": f.get("trade_code"),
                    "message": f["message"],
                }
                for f in findings[:25]
            ],
        },
        "assumptions_register": register,
        "assumptions": assumptions[:50],
        "exclusions": exclusions[:50],
        "open_questions": open_questions[:50],
    }
