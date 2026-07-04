"""Deterministic, offline mock extraction provider.

Used by default and in all tests. It is trade-agnostic: it dispatches on the
requested ``trade_code`` and can produce candidates for more than one trade,
proving the provider layer is not Painting-specific. It also supports forced
``timeout``/``malformed`` behaviors and transient failures for testing the
service's error handling and retry logic.

To prove the server never trusts provider-supplied sheet numbers, the mock cites a
deliberately wrong ``claimed_sheet_number``; the service replaces it with the
verified sheet number from the database.
"""

from __future__ import annotations

from typing import Any

from app.extraction.base import ExtractionProvider, ProviderTimeout
from app.extraction.provider_schemas import (
    PROVIDER_SCHEMA_VERSION,
    ScopeExtractionRequest,
    SheetClassificationRequest,
)

_WRONG_CLAIMED_SHEET = "PROVIDER-CLAIM-IGNORED"


def _painting_candidates(page: int) -> list[dict[str, Any]]:
    return [
        {
            "category_code": "interior_walls",
            "description": "Paint interior gypsum walls per finish schedule",
            "location": "Level 1 Corridor",
            "quantity": {
                "basis": "dimension_inputs",
                "value": None,
                "unit": "SF",
                "formula_id": "painting.wall_gross_area",
                "raw_inputs": {"length_ft": "20", "height_ft": "9"},
            },
            "trade_data": {
                "substrate": "gypsum board",
                "coating_system": "latex eggshell",
                "finish_coats": 2,
                "interior_exterior": "interior",
                "primer_required": True,
            },
            "evidence": [
                {
                    "pdf_page_number": page,
                    "claimed_sheet_number": _WRONG_CLAIMED_SHEET,
                    "evidence_type": "finish_schedule",
                    "description": "Room finish schedule lists paint on gypsum walls",
                    "extracted_text_quote": "WALLS: PT-1 (2 COATS)",
                    "confidence": "0.96",
                }
            ],
            "confidence": "0.96",
            "assumptions": [],
            "exclusions": [],
            "conflicts_flagged": [],
        },
        {
            "category_code": "door_frames",
            "description": "Paint hollow-metal door frames per door schedule",
            "location": "Level 1",
            "quantity": {
                "basis": "schedule_count",
                "value": "3",
                "unit": "EA",
                "formula_id": None,
                "raw_inputs": {},
            },
            "trade_data": {"substrate": "hollow metal"},
            "evidence": [
                {
                    "pdf_page_number": page,
                    "claimed_sheet_number": _WRONG_CLAIMED_SHEET,
                    "evidence_type": "door_schedule",
                    "description": "Door schedule shows 3 HM frames to be painted",
                    "confidence": "0.97",
                }
            ],
            "confidence": "0.97",
            "assumptions": [],
            "exclusions": [],
            "conflicts_flagged": [],
        },
    ]


def _concrete_candidates(page: int) -> list[dict[str, Any]]:
    return [
        {
            "category_code": "slab_on_grade",
            "description": "Slab on grade per structural plan",
            "location": "Building A",
            "quantity": {
                "basis": "dimension_inputs",
                "value": None,
                "unit": "CY",
                "formula_id": "demo_concrete.slab_volume",
                "raw_inputs": {
                    "length_ft": "27",
                    "width_ft": "10",
                    "thickness_in": "6",
                },
            },
            "trade_data": {"mix_design": "3000 psi", "thickness_in": 6},
            "evidence": [
                {
                    "pdf_page_number": page,
                    "claimed_sheet_number": _WRONG_CLAIMED_SHEET,
                    "evidence_type": "schedule",
                    "description": "Slab schedule indicates 6 in slab on grade",
                    "confidence": "0.95",
                }
            ],
            "confidence": "0.95",
            "assumptions": [],
            "exclusions": [],
            "conflicts_flagged": [],
        }
    ]


_TRADE_CANDIDATES = {
    "painting": _painting_candidates,
    "demo_concrete": _concrete_candidates,
}


class MockExtractionProvider(ExtractionProvider):
    provider_name = "mock"

    def __init__(
        self,
        *,
        behavior: str = "normal",
        transient_failures: int = 0,
    ) -> None:
        self.behavior = behavior
        self._remaining_transient = transient_failures

    def _maybe_fail(self) -> None:
        if self.behavior == "timeout":
            raise ProviderTimeout()
        if self._remaining_transient > 0:
            self._remaining_transient -= 1
            raise ProviderTimeout("Transient provider failure")

    def classify_sheets(self, request: SheetClassificationRequest) -> dict[str, Any]:
        self._maybe_fail()
        return {
            "provider_schema_version": PROVIDER_SCHEMA_VERSION,
            "classifications": [
                {"sheet_id": str(s.sheet_id), "relevance": "relevant", "reason": "mock"}
                for s in request.sheets
            ],
        }

    def extract_scope(self, request: ScopeExtractionRequest) -> dict[str, Any]:
        self._maybe_fail()
        if self.behavior == "malformed":
            # Unknown field + missing required fields → service must reject this.
            return {"unexpected_field": True, "candidates": [{"oops": 1}]}

        builder = _TRADE_CANDIDATES.get(request.trade_code)
        candidates: list[dict[str, Any]] = []
        if builder is not None and request.sheets:
            page = request.sheets[0].pdf_page_number
            candidates = builder(page)

        return {
            "provider_schema_version": PROVIDER_SCHEMA_VERSION,
            "trade_code": request.trade_code,
            "candidates": candidates,
            "usage": {
                "prompt_tokens": 100 * max(len(request.sheets), 1),
                "completion_tokens": 50 * max(len(candidates), 1),
                "total_tokens": 150 * max(len(request.sheets), 1),
            },
        }
