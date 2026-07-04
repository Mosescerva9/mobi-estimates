"""Unit tests for the project-status transition graph."""

from __future__ import annotations

import pytest

from app.schemas import ProjectStatus
from app.status_rules import (
    InvalidStatusTransition,
    assert_transition,
    can_transition,
)


@pytest.mark.parametrize(
    "current,new",
    [
        # Phase 1 transitions (preserved).
        (ProjectStatus.CREATED, ProjectStatus.UPLOADED),
        (ProjectStatus.UPLOADED, ProjectStatus.PROCESSING),
        (ProjectStatus.PROCESSING, ProjectStatus.NEEDS_REVIEW),
        (ProjectStatus.PROCESSING, ProjectStatus.COMPLETE),
        (ProjectStatus.NEEDS_REVIEW, ProjectStatus.PROCESSING),
        (ProjectStatus.NEEDS_REVIEW, ProjectStatus.COMPLETE),
        (ProjectStatus.UPLOADED, ProjectStatus.FAILED),
        # Phase 2 processing lifecycle transitions.
        (ProjectStatus.UPLOADED, ProjectStatus.QUEUED),
        (ProjectStatus.QUEUED, ProjectStatus.PROCESSING),
        (ProjectStatus.PROCESSING, ProjectStatus.READY_FOR_REVIEW),
        (ProjectStatus.PROCESSING, ProjectStatus.FAILED),
        (ProjectStatus.READY_FOR_REVIEW, ProjectStatus.QUEUED),
        (ProjectStatus.FAILED, ProjectStatus.QUEUED),
    ],
)
def test_allowed_transitions(current, new):
    assert can_transition(current, new) is True
    assert_transition(current, new)  # should not raise


@pytest.mark.parametrize(
    "current,new",
    [
        (ProjectStatus.UPLOADED, ProjectStatus.COMPLETE),
        (ProjectStatus.COMPLETE, ProjectStatus.PROCESSING),
        (ProjectStatus.FAILED, ProjectStatus.UPLOADED),
        (ProjectStatus.CREATED, ProjectStatus.COMPLETE),
        (ProjectStatus.QUEUED, ProjectStatus.READY_FOR_REVIEW),
    ],
)
def test_disallowed_transitions(current, new):
    assert can_transition(current, new) is False
    with pytest.raises(InvalidStatusTransition):
        assert_transition(current, new)


def test_complete_is_terminal():
    # `complete` is the only fully terminal state.
    for target in ProjectStatus:
        assert can_transition(ProjectStatus.COMPLETE, target) is False


def test_failed_can_only_requeue():
    # A failed project may be re-queued for another attempt, but nothing else.
    assert can_transition(ProjectStatus.FAILED, ProjectStatus.QUEUED) is True
    for target in ProjectStatus:
        if target is ProjectStatus.QUEUED:
            continue
        assert can_transition(ProjectStatus.FAILED, target) is False
