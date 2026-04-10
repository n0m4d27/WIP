from __future__ import annotations

import pytest

from tasktracker.domain.priority import compute_priority, priority_display


@pytest.mark.parametrize(
    "impact,urgency,pr",
    [
        (1, 1, 1),
        (1, 2, 2),
        (1, 3, 3),
        (2, 1, 2),
        (2, 2, 3),
        (2, 3, 4),
        (3, 1, 3),
        (3, 2, 4),
        (3, 3, 5),
    ],
)
def test_servicenow_matrix(impact: int, urgency: int, pr: int) -> None:
    assert compute_priority(impact=impact, urgency=urgency) == pr


def test_priority_display() -> None:
    assert "P1" in priority_display(1)
    assert "Critical" in priority_display(1)


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        compute_priority(impact=0, urgency=1)
    with pytest.raises(ValueError):
        compute_priority(impact=1, urgency=4)
