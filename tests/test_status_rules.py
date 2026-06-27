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
        (ProjectStatus.CREATED, ProjectStatus.UPLOADED),
        (ProjectStatus.UPLOADED, ProjectStatus.PROCESSING),
        (ProjectStatus.PROCESSING, ProjectStatus.NEEDS_REVIEW),
        (ProjectStatus.PROCESSING, ProjectStatus.COMPLETE),
        (ProjectStatus.NEEDS_REVIEW, ProjectStatus.PROCESSING),
        (ProjectStatus.NEEDS_REVIEW, ProjectStatus.COMPLETE),
        (ProjectStatus.UPLOADED, ProjectStatus.FAILED),
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
    ],
)
def test_disallowed_transitions(current, new):
    assert can_transition(current, new) is False
    with pytest.raises(InvalidStatusTransition):
        assert_transition(current, new)


def test_terminal_states_have_no_exits():
    for terminal in (ProjectStatus.COMPLETE, ProjectStatus.FAILED):
        for target in ProjectStatus:
            assert can_transition(terminal, target) is False
