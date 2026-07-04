"""Deterministic painting sheet-routing rules (multi-signal, not prefix-only)."""

from __future__ import annotations

from app.extraction.schemas import RoutingStatus
from app.trades.base import SheetContext, SheetRoutingResult

PAINT_KEYWORDS = (
    "PAINT", "PAINTING", "COATING", "COATINGS", "FINISH", "FINISHES",
)
# Disciplines that are conventionally irrelevant to painting scope.
EXCLUDED_DISCIPLINE_PREFIXES = ("E", "P", "M", "FP", "FA", "T")
ARCHITECTURAL_PREFIXES = ("A", "ID", "AD")


def _discipline_prefix(sheet_number: str) -> str:
    letters = ""
    for char in sheet_number.upper():
        if char.isalpha():
            letters += char
        else:
            break
    return letters


def route_painting_sheet(sheet: SheetContext) -> SheetRoutingResult:
    # A verified sheet number is required before any evidence can be trusted.
    if not sheet.verified_sheet_number:
        return SheetRoutingResult(
            RoutingStatus.BLOCKED_UNVERIFIED,
            "Sheet has no verified sheet number; verify before extraction.",
        )
    if sheet.requires_ocr:
        return SheetRoutingResult(
            RoutingStatus.BLOCKED_OCR,
            "Sheet has insufficient embedded text and requires OCR.",
        )

    blob = " ".join(
        filter(
            None,
            [
                sheet.verified_sheet_number,
                sheet.verified_sheet_title or "",
                sheet.embedded_text or "",
            ],
        )
    ).upper()
    has_paint_signal = any(keyword in blob for keyword in PAINT_KEYWORDS)
    prefix = _discipline_prefix(sheet.verified_sheet_number)

    if has_paint_signal:
        return SheetRoutingResult(
            RoutingStatus.ELIGIBLE,
            "Painting/finish keyword found in verified sheet text.",
        )
    if prefix in EXCLUDED_DISCIPLINE_PREFIXES:
        return SheetRoutingResult(
            RoutingStatus.EXCLUDED,
            f"Non-painting discipline '{prefix}' with no painting signal.",
        )
    if prefix in ARCHITECTURAL_PREFIXES:
        return SheetRoutingResult(
            RoutingStatus.REQUIRES_REVIEW,
            "Architectural sheet without an explicit painting keyword.",
        )
    return SheetRoutingResult(
        RoutingStatus.REQUIRES_REVIEW,
        "Insufficient signal to route this sheet automatically.",
    )
