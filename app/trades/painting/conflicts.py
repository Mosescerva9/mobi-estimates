"""Painting conflict detection. Never auto-resolves document conflicts."""

from __future__ import annotations

from typing import Any

from app.extraction.schemas import (
    Conflict,
    ConflictSeverity,
    SharedConflictCode,
)
from app.trades.base import CandidateContext
from app.trades.painting.validation import category_requires_quantity


def detect_painting_conflicts(
    candidate: CandidateContext, related_items: list[dict[str, Any]]
) -> list[Conflict]:
    conflicts: list[Conflict] = []

    if (
        category_requires_quantity(candidate.category_code)
        and candidate.quantity_value is None
    ):
        conflicts.append(
            Conflict(
                code=SharedConflictCode.MISSING_QUANTITY.value,
                severity=ConflictSeverity.BLOCKING,
                description=(
                    f"Category '{candidate.category_code}' requires a quantity but "
                    "none was resolved."
                ),
            )
        )

    if candidate.quantity_value is not None and candidate.unit is None:
        conflicts.append(
            Conflict(
                code=SharedConflictCode.MISSING_UNIT.value,
                severity=ConflictSeverity.BLOCKING,
                description="A quantity was provided without a unit.",
            )
        )

    # Duplicate scope: same category + location already present.
    for item in related_items:
        if (
            item.get("category_code") == candidate.category_code
            and item.get("location")
            and item.get("location") == candidate.location
        ):
            conflicts.append(
                Conflict(
                    code=SharedConflictCode.DUPLICATE_SCOPE_CANDIDATE.value,
                    severity=ConflictSeverity.WARNING,
                    description=(
                        "Another candidate shares this category and location; "
                        "verify these are not duplicates."
                    ),
                )
            )
            break

    return conflicts
