"""Project-status transition rules.

Status changes are constrained by an explicit directed graph so a project can
never jump into an invalid lifecycle state (for example from ``complete`` back to
``uploaded``). Pricing and extraction code in later phases must route every status
change through :func:`assert_transition`.
"""

from __future__ import annotations

from app.schemas import ProjectStatus


class InvalidStatusTransition(ValueError):
    """Raised when a requested status transition is not permitted."""


# Allowed forward transitions. ``complete`` is the only fully terminal state.
#
# Phase 2 adds the deterministic processing lifecycle (queued / processing /
# ready_for_review) while preserving every Phase 1 transition that existing code
# and tests rely on (e.g. uploaded -> processing, processing -> needs_review).
ALLOWED_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.CREATED: frozenset({ProjectStatus.UPLOADED, ProjectStatus.FAILED}),
    ProjectStatus.UPLOADED: frozenset(
        {
            ProjectStatus.QUEUED,
            ProjectStatus.PROCESSING,
            ProjectStatus.FAILED,
        }
    ),
    ProjectStatus.QUEUED: frozenset(
        {ProjectStatus.PROCESSING, ProjectStatus.FAILED}
    ),
    ProjectStatus.PROCESSING: frozenset(
        {
            ProjectStatus.READY_FOR_REVIEW,
            ProjectStatus.NEEDS_REVIEW,
            ProjectStatus.COMPLETE,
            ProjectStatus.FAILED,
        }
    ),
    ProjectStatus.READY_FOR_REVIEW: frozenset(
        {
            ProjectStatus.QUEUED,  # only when explicitly reprocessing
            ProjectStatus.NEEDS_REVIEW,
            ProjectStatus.COMPLETE,
            ProjectStatus.FAILED,
        }
    ),
    ProjectStatus.NEEDS_REVIEW: frozenset(
        {
            ProjectStatus.PROCESSING,
            ProjectStatus.COMPLETE,
            ProjectStatus.FAILED,
        }
    ),
    ProjectStatus.COMPLETE: frozenset(),
    # A failed project may be re-queued for another processing attempt.
    ProjectStatus.FAILED: frozenset({ProjectStatus.QUEUED}),
}


def can_transition(current: ProjectStatus, new: ProjectStatus) -> bool:
    """Return ``True`` if moving from ``current`` to ``new`` is allowed."""
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: ProjectStatus, new: ProjectStatus) -> None:
    """Raise :class:`InvalidStatusTransition` if the transition is not allowed."""
    if not can_transition(current, new):
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset()))
        raise InvalidStatusTransition(
            f"Cannot move project from '{current.value}' to '{new.value}'. "
            f"Allowed next states: {allowed or 'none (terminal state)'}."
        )
