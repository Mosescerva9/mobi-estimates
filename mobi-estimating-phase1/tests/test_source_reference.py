"""Guarantee: an unverified detected sheet number cannot back a source reference."""

from __future__ import annotations

import pytest

from app.schemas import (
    SourceReference,
    UnverifiedSheetReferenceError,
    build_source_reference,
)


def test_verified_sheet_number_builds_source_reference():
    ref = build_source_reference(
        page_number=3,
        verified_sheet_number="A-101",
        evidence="Wall finish schedule on sheet A-101",
    )
    assert isinstance(ref, SourceReference)
    assert ref.sheet_number == "A-101"
    assert ref.page_number == 3


def test_unverified_sheet_number_is_rejected():
    # A detected-but-unverified sheet (verified value is None) must not pass.
    with pytest.raises(UnverifiedSheetReferenceError):
        build_source_reference(
            page_number=3,
            verified_sheet_number=None,
            evidence="Detected candidate only",
        )


def test_empty_verified_sheet_number_is_rejected():
    with pytest.raises(UnverifiedSheetReferenceError):
        build_source_reference(
            page_number=3,
            verified_sheet_number="",
            evidence="Empty verified value",
        )
