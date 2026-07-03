"""Proposal enums and API request models (client-facing document layer)."""

from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProposalStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ProposalVersionStatus(str, Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ProposalDetailLevel(str, Enum):
    SUMMARY = "summary"   # single total + scope narrative
    TRADE = "trade"       # sell price per trade section
    LINE = "line"         # sell price per line item


class ProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ProposalCreate(ProposalModel):
    name: str = Field(min_length=1, max_length=255)
    estimate_id: UUID
    # Optional explicit approved estimate version; defaults to the latest approved.
    estimate_version_id: UUID | None = None
    client_name: str = Field(min_length=1, max_length=255)
    client_contact: str | None = Field(default=None, max_length=255)
    prepared_by: str | None = Field(default=None, max_length=255)
    detail_level: ProposalDetailLevel = ProposalDetailLevel.TRADE
    valid_until: date | None = None
    cover_notes: str = Field(default="", max_length=4000)
    terms: str = Field(default="", max_length=8000)
    # Proposal-level additions, merged with (and after) the estimate's own lists.
    extra_inclusions: list[str] = Field(default_factory=list)
    extra_exclusions: list[str] = Field(default_factory=list)
    extra_assumptions: list[str] = Field(default_factory=list)
    extra_clarifications: list[str] = Field(default_factory=list)


class IssueRequest(ProposalModel):
    proposal_number: str | None = Field(default=None, max_length=64)
    actor: str = Field(default="system", max_length=128)


class AcceptRequest(ProposalModel):
    actor: str = Field(default="system", max_length=128)
    notes: str = Field(default="", max_length=2000)


class DeclineRequest(ProposalModel):
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="system", max_length=128)


class RegenerateRequest(ProposalModel):
    # Optionally re-base on a different approved estimate version.
    estimate_version_id: UUID | None = None
    actor: str = Field(default="system", max_length=128)
