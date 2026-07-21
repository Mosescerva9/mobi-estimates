"""Deterministic source-text extraction provider for narrow, explicit evidence patterns.

This provider is intentionally conservative. It emits candidates only when the supplied,
server-resolved embedded text contains every required phrase for a supported pattern. It
never infers dimensions, quantities, rates, prices, or missing trade data.

The first supported pattern proves one real public-PDF painting slice: Section 099000's
minimum 100-SF paint-system mockup requirement joined to the explicit three-coat gypsum
board system on the next specification page. The output remains review-required and is
anchored by the extraction service to verified project sheet/page records.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from app.extraction.base import ExtractionProvider
from app.extraction.provider_schemas import (
    PROVIDER_SCHEMA_VERSION,
    ScopeExtractionRequest,
    SheetClassificationRequest,
)


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _contains_all(text: str, phrases: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return all(phrase.lower() in lowered for phrase in phrases)


def _quote(text: str, anchor: str, *, max_chars: int = 900) -> str:
    """Return a source substring around an exact case-insensitive anchor."""
    compact = _normalized(text)
    match = re.search(re.escape(anchor), compact, flags=re.IGNORECASE)
    if match is None:
        return compact[:max_chars]
    start = max(0, match.start() - 120)
    end = min(len(compact), match.end() + max_chars - 120)
    return compact[start:end]


def _painting_candidates(request: ScopeExtractionRequest) -> list[dict[str, Any]]:
    mockup_sheet = None
    system_sheet = None
    for sheet in request.sheets:
        text = _normalized(sheet.embedded_text)
        if _contains_all(
            text,
            (
                "section 099000",
                "apply mockups of each paint system indicated",
                "provide samples of at least 100 sq. ft.",
            ),
        ):
            mockup_sheet = sheet
        if _contains_all(
            text,
            (
                "schedule of paints",
                "gypsum board",
                "3 coats",
                "interior qd latex primer-sealer",
                "aquapon epoxy",
            ),
        ):
            system_sheet = sheet

    if mockup_sheet is None or system_sheet is None:
        return []

    mockup_quote = _quote(
        mockup_sheet.embedded_text,
        "Apply mockups of each paint system indicated",
    )
    system_quote = _quote(
        system_sheet.embedded_text,
        "Gypsum Board: (At or Near Wet Areas): 3 Coats",
    )
    return [
        {
            "category_code": "interior_walls",
            "description": (
                "Apply a minimum 100 SF vertical gypsum-board paint-system mockup "
                "using the specified three-coat wet-area system"
            ),
            "location": "Architect-designated mockup surface",
            "quantity": {
                "basis": "explicit_plan_quantity",
                "value": "100",
                "unit": "SF",
                "raw_inputs": {
                    "source_requirement": "minimum 100 SF vertical surface mockup",
                },
                "formula_id": None,
            },
            "trade_data": {
                "substrate": "gypsum board",
                "coating_system": (
                    "Pittsburg Speedhide Interior QD Latex Primer-Sealer 6-2; "
                    "Pittsburg Aquapon Epoxy 97-Line"
                ),
                "finish_coats": 3,
                "interior_exterior": "interior",
                "primer_required": True,
            },
            "evidence": [
                {
                    "pdf_page_number": mockup_sheet.pdf_page_number,
                    "claimed_sheet_number": mockup_sheet.verified_sheet_number,
                    "evidence_type": "finish_schedule",
                    "description": "Section 099000 minimum vertical mockup area requirement",
                    "extracted_text_quote": mockup_quote,
                    "confidence": str(Decimal("0.99")),
                },
                {
                    "pdf_page_number": system_sheet.pdf_page_number,
                    "claimed_sheet_number": system_sheet.verified_sheet_number,
                    "evidence_type": "finish_schedule",
                    "description": "Section 099000 gypsum-board three-coat system",
                    "extracted_text_quote": system_quote,
                    "confidence": str(Decimal("0.99")),
                },
            ],
            "confidence": str(Decimal("0.99")),
            "assumptions": [
                "This candidate covers only the explicitly specified mockup, not total project painting quantity."
            ],
            "exclusions": [
                "No total wall area, production rate, market price, or final estimate is inferred."
            ],
            "conflicts_flagged": [],
        }
    ]


class SourceTextExtractionProvider(ExtractionProvider):
    """Offline provider for explicitly supported deterministic source-text patterns."""

    provider_name = "source_text"

    def classify_sheets(self, request: SheetClassificationRequest) -> dict[str, Any]:
        classifications = []
        for sheet in request.sheets:
            text = _normalized(sheet.embedded_text).lower()
            relevant = any(token in text for token in ("paint", "painting", "coating", "finish"))
            classifications.append(
                {
                    "sheet_id": str(sheet.sheet_id),
                    "relevance": "relevant" if relevant else "not_relevant",
                    "reason": "explicit painting/finish source-text signal" if relevant else "no supported source-text signal",
                }
            )
        return {
            "provider_schema_version": PROVIDER_SCHEMA_VERSION,
            "classifications": classifications,
        }

    def extract_scope(self, request: ScopeExtractionRequest) -> dict[str, Any]:
        candidates = _painting_candidates(request) if request.trade_code == "painting" else []
        return {
            "provider_schema_version": PROVIDER_SCHEMA_VERSION,
            "trade_code": request.trade_code,
            "candidates": candidates,
            "usage": {
                "provider": self.provider_name,
                "network_calls": 0,
                "supported_pattern_count": 1,
            },
        }
