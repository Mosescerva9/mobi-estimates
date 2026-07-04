"""Unit tests for the deterministic sheet-number/title detector."""

from __future__ import annotations

import pytest

from app.services.sheet_detection import (
    SHEET_NUMBER_RE,
    TextBlock,
    detect_sheet_number,
    detect_sheet_number_candidates,
    detect_sheet_title,
    normalize_sheet_token,
)


@pytest.mark.parametrize(
    "token",
    ["A1.01", "A-101", "A101", "S2.1", "M-201", "E001", "P3.02", "C-100", "G0.01"],
)
def test_sheet_number_pattern_matches_common_formats(token):
    assert SHEET_NUMBER_RE.match(normalize_sheet_token(token)) is not None


@pytest.mark.parametrize("token", ["HELLO", "1234", "PLAN", "12.5", "REVISION"])
def test_sheet_number_pattern_rejects_non_sheets(token):
    assert SHEET_NUMBER_RE.match(normalize_sheet_token(token)) is None


def _title_block(value: str) -> list[TextBlock]:
    # A block positioned in the bottom-right title-block region of a letter page.
    return [TextBlock(x0=470, y0=740, x1=560, y1=770, text=value)]


def test_detect_sheet_number_in_title_block_is_accepted():
    result = detect_sheet_number(
        "A-101",
        blocks=_title_block("A-101"),
        page_width=612,
        page_height=792,
    )
    assert result.detected_value == "A-101"
    assert result.requires_review is False
    assert result.confidence is not None and result.confidence >= 0.6


def test_no_reliable_sheet_number_requires_review():
    result = detect_sheet_number(
        "These are only general project notes with no drawing identifier.",
        blocks=[TextBlock(72, 72, 400, 120, "Only general notes here")],
        page_width=612,
        page_height=792,
    )
    assert result.detected_value is None
    assert result.requires_review is True


def test_conflicting_candidates_require_review():
    # Two different, equally-plausible numbers in the title-block region.
    blocks = [
        TextBlock(470, 740, 560, 758, "A-101"),
        TextBlock(470, 760, 560, 778, "A-201"),
    ]
    result = detect_sheet_number(
        "A-101\nA-201", blocks=blocks, page_width=612, page_height=792
    )
    assert result.detected_value is None
    assert result.requires_review is True
    # Both candidates are still surfaced internally for transparency.
    values = {c.value for c in result.candidates}
    assert {"A-101", "A-201"} <= values


def test_first_token_is_not_blindly_chosen():
    # A drawing-like token appears top-left; the real one is in the title block.
    blocks = [
        TextBlock(72, 72, 200, 90, "E001 see electrical"),
        TextBlock(480, 745, 560, 765, "A-101"),
    ]
    result = detect_sheet_number(
        "E001 see electrical\nA-101", blocks=blocks, page_width=612, page_height=792
    )
    # The title-block candidate should win (higher confidence).
    assert result.detected_value == "A-101"


def test_candidates_are_scored_and_sorted():
    blocks = [TextBlock(480, 745, 560, 765, "A-101")]
    candidates = detect_sheet_number_candidates(
        "A-101", blocks=blocks, page_width=612, page_height=792
    )
    assert candidates
    assert candidates[0].value == "A-101"
    assert 0.0 <= candidates[0].confidence <= 1.0


def test_detect_sheet_title_with_keyword_in_title_block():
    blocks = [
        TextBlock(440, 745, 560, 760, "A-101"),
        TextBlock(440, 762, 560, 778, "FIRST FLOOR PLAN"),
    ]
    title = detect_sheet_title(
        "A-101\nFIRST FLOOR PLAN",
        blocks=blocks,
        page_width=612,
        page_height=792,
        sheet_number="A-101",
    )
    assert title == "FIRST FLOOR PLAN"


def test_detect_sheet_title_returns_none_when_unreliable():
    title = detect_sheet_title(
        "x y z 12 34",
        blocks=[TextBlock(72, 72, 200, 90, "x y z 12 34")],
        page_width=612,
        page_height=792,
    )
    assert title is None


def test_detection_is_deterministic():
    blocks = _title_block("M-201")
    first = detect_sheet_number("M-201", blocks=blocks, page_width=612, page_height=792)
    second = detect_sheet_number("M-201", blocks=blocks, page_width=612, page_height=792)
    assert first.detected_value == second.detected_value == "M-201"
    assert first.confidence == second.confidence
