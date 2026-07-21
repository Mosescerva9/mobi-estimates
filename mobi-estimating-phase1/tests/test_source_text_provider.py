"""Deterministic source-text provider tests."""

from __future__ import annotations

from uuid import uuid4

from app.extraction.provider_schemas import ProviderSheetInput, ScopeExtractionRequest
from app.extraction.source_text_provider import SourceTextExtractionProvider


def _request(*texts: str) -> ScopeExtractionRequest:
    return ScopeExtractionRequest(
        trade_code="painting",
        prompt_version="scope_extractor_v1",
        allowed_categories=["interior_walls"],
        allowed_units=["SF"],
        sheets=[
            ProviderSheetInput(
                sheet_id=uuid4(),
                pdf_page_number=index,
                verified_sheet_number=f"099000-{index}",
                verified_sheet_title="PAINTING",
                embedded_text=text,
            )
            for index, text in enumerate(texts, start=1)
        ],
    )


def test_source_text_provider_emits_only_explicit_joined_painting_mockup_scope():
    response = SourceTextExtractionProvider().extract_scope(
        _request(
            """
            SECTION 099000 PAINTING
            Apply mockups of each paint system indicated and each color and finish selected.
            Vertical and Horizontal Surfaces: Provide samples of at least 100 sq. ft.
            """,
            """
            SCHEDULE OF PAINTS
            Gypsum Board: (At or Near Wet Areas): 3 Coats:
            1st Coat: Pittsburg Speedhide Interior QD Latex Primer-Sealer 6-2
            2nd & 3rd Coats: Pittsburg Aquapon Epoxy 97-Line
            """,
        )
    )

    assert response["usage"]["network_calls"] == 0
    assert len(response["candidates"]) == 1
    candidate = response["candidates"][0]
    assert candidate["category_code"] == "interior_walls"
    assert candidate["quantity"] == {
        "basis": "explicit_plan_quantity",
        "value": "100",
        "unit": "SF",
        "raw_inputs": {"source_requirement": "minimum 100 SF vertical surface mockup"},
        "formula_id": None,
    }
    assert candidate["trade_data"]["finish_coats"] == 3
    assert candidate["trade_data"]["substrate"] == "gypsum board"
    assert len(candidate["evidence"]) == 2
    assert "100 sq. ft." in candidate["evidence"][0]["extracted_text_quote"]
    assert "Aquapon Epoxy" in candidate["evidence"][1]["extracted_text_quote"]
    assert "No total wall area" in candidate["exclusions"][0]


def test_source_text_provider_abstains_when_quantity_or_system_evidence_is_incomplete():
    provider = SourceTextExtractionProvider()
    only_mockup = provider.extract_scope(
        _request(
            "SECTION 099000 Apply mockups of each paint system indicated. "
            "Provide samples of at least 100 sq. ft."
        )
    )
    only_system = provider.extract_scope(
        _request(
            "SCHEDULE OF PAINTS Gypsum Board: 3 Coats. "
            "Interior QD Latex Primer-Sealer. Aquapon Epoxy."
        )
    )

    assert only_mockup["candidates"] == []
    assert only_system["candidates"] == []


def test_source_text_provider_abstains_for_other_trades():
    request = _request("SECTION 099000 PAINTING")
    request.trade_code = "demo_concrete"
    assert SourceTextExtractionProvider().extract_scope(request)["candidates"] == []
