"""API request models for the human-review workflow."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class CorrectionRequest(ReviewModel):
    """Reviewer corrections. Only shared editable fields + trade_data are allowed.

    A reviewer-supplied ``quantity`` is recorded with basis ``manual_reviewer_entry``.
    The original provider candidate is never modified.
    """

    description: str | None = Field(default=None, min_length=1, max_length=1000)
    location: str | None = Field(default=None, max_length=255)
    category_code: str | None = Field(default=None, max_length=64)
    specification_section: str | None = Field(default=None, max_length=64)
    material_or_substrate: str | None = Field(default=None, max_length=255)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=16)
    trade_data: dict[str, Any] | None = None
    reviewer_id: str = Field(default="system", max_length=128)
    reviewer_notes: str | None = Field(default=None, max_length=2000)


class ApprovalRequest(ReviewModel):
    reviewer_id: str = Field(default="system", max_length=128)
    reviewer_notes: str | None = Field(default=None, max_length=2000)


class RejectionRequest(ReviewModel):
    reason: str = Field(min_length=1, max_length=2000)
    reviewer_id: str = Field(default="system", max_length=128)


class RecalculateRequest(ReviewModel):
    formula_id: str = Field(min_length=1, max_length=128)
    inputs: dict[str, Any]
    reviewer_id: str = Field(default="system", max_length=128)
