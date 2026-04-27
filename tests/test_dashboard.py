"""Tests for the plan 01 dashboard aggregation service.

These tests operate against the in-memory SQLite fixture from
``conftest.py``. They deliberately avoid spinning up a ``QApplication``
- the widget layer is already thin and stateless, and the numbers the
user cares about are all produced here in the service layer.
"""

from __future__ import annotations

import datetime as dt

from tasktracker.domain.enums import TaskStatus
from tasktracker.services.task_service import (
    DASHBOARD_CARD_IDS,
    TaskService,
)


def _make_task(
    svc: TaskService,
    title: str,
    *,
    due: dt.date | None = None,
    impact: int = 3,
    urgency: int = 3,
    status: str | None = None,
):
    task = svc.create_task(
        title=title,
        received_date=dt.date(2026, 1, 1),
        due_date=due,
        impact=impact,
        urgency=urgency,
    )
    if status is not None:
        svc.update_task_fields(task.id, status=status)
        task = svc.get_task(task.id)
        assert task is not None
    return task


def test_dashboard_sections_returns_all_expected_cards(svc: TaskService) -> None:
    sections = svc.dashboard_sections(as_of=dt.date(2026, 3, 10))
    assert set(sections.keys()) == set(DASHBOARD_CARD_IDS)
    for card_id in DASHBOARD_CARD_IDS:
        entry = sections[card_id]
        assert "count" in entry
        assert "rows" in entry
        assert isinstance(entry["rows"], list)


def test_overdue_card_counts_match_due_date_predicate(svc: TaskService) -> None:
    today = dt.date(2026, 3, 10)
    # Two overdue, one due today (should NOT count as overdue), one
    # due later (should NOT count as overdue), one no due date.
    _make_task(svc, "yesterday", due=today - dt.timedelta(days=1))
    _make_task(svc, "last week", due=today - dt.timedelta(days=7))
    _make_task(svc, "today", due=today)
    _make_task(svc, "tomorrow", due=today + dt.timedelta(days=1))
    _make_task(svc, "no due", due=None)

    sections = svc.dashboard_sections(as_of=today)
    overdue = sections["overdue"]
    assert overdue["count"] == 2
    titles = {t.title for t in overdue["rows"]}
    assert titles == {"yesterday", "last week"}


def test_overdue_ignores_closed_and_cancelled(svc: TaskService) -> None:
    today = dt.date(2026, 3, 10)
    open_task = _make_task(svc, "open overdue", due=today - dt.timedelta(days=3))
    closed = _make_task(svc, "closed overdue", due=today - dt.timedelta(days=3))
    cancelled = _make_task(svc, "cancelled overdue", due=today - dt.timedelta(days=3))
    svc.close_task(closed.id, closed_on=today, resolution="Done")
    svc.update_task_fields(cancelled.id, status=TaskStatus.CANCELLED)

    sections = svc.dashboard_sections(as_of=today)
    titles = {t.title for t in sections["overdue"]["rows"]}
    assert titles == {open_task.title}
    assert sections["overdue"]["count"] == 1


def test_due_today_and_due_this_week(svc: TaskService) -> None:
    today = dt.date(2026, 3, 10)
    _make_task(svc, "today a", due=today)
    _make_task(svc, "today b", due=today)
    _make_task(svc, "plus three", due=today + dt.timedelta(days=3))
    _make_task(svc, "plus six", due=today + dt.timedelta(days=6))
    _make_task(svc, "plus seven", due=today + dt.timedelta(days=7))
    _make_task(svc, "overdue", due=today - dt.timedelta(days=1))

    sections = svc.dashboard_sections(as_of=today)

    due_today_titles = {t.title for t in sections["due_today"]["rows"]}
    assert due_today_titles == {"today a", "today b"}
    assert sections["due_today"]["count"] == 2

    # Week window is today .. today+6 inclusive. "plus seven" falls outside.
    week_titles = {t.title for t in sections["due_this_week"]["rows"]}
    assert week_titles == {"today a", "today b", "plus three", "plus six"}
    assert sections["due_this_week"]["count"] == 4


def test_blocked_card_matches_status(svc: TaskService) -> None:
    today = dt.date(2026, 3, 10)
    _make_task(svc, "open", due=today)
    blocked = _make_task(svc, "blocked", due=today, status=TaskStatus.BLOCKED)
    _make_task(svc, "cancelled", due=today, status=TaskStatus.CANCELLED)

    sections = svc.dashboard_sections(as_of=today)
    titles = {t.title for t in sections["blocked"]["rows"]}
    assert titles == {blocked.title}
    assert sections["blocked"]["count"] == 1


def test_top_priority_card_includes_p1_and_p2_only(svc: TaskService) -> None:
    today = dt.date(2026, 3, 10)
    # Priority is derived from the impact x urgency matrix:
    # impact=urgency=1 -> P1 (Critical); impact=1,urgency=2 -> P2
    # (High); impact=urgency=2 -> P3 (Moderate). We want a P1 + P2
    # mix plus a lower-priority row the card should exclude.
    p1 = _make_task(svc, "p1", impact=1, urgency=1)
    p2 = _make_task(svc, "p2", impact=1, urgency=2)
    p3 = _make_task(svc, "p3", impact=2, urgency=2)

    sections = svc.dashboard_sections(as_of=today)
    titles = [t.title for t in sections["top_priority"]["rows"]]
    assert p1.title in titles
    assert p2.title in titles
    assert p3.title not in titles
    assert sections["top_priority"]["count"] == 2
    # Sort is by due date (both None here, so tied) then priority
    # ascending: Critical before High.
    assert titles.index(p1.title) < titles.index(p2.title)


def test_dashboard_rows_cap_at_top_n(svc: TaskService) -> None:
    today = dt.date(2026, 3, 10)
    for i in range(12):
        _make_task(svc, f"overdue-{i:02d}", due=today - dt.timedelta(days=i + 1))

    sections = svc.dashboard_sections(as_of=today, top_n=5)
    assert sections["overdue"]["count"] == 12
    assert len(sections["overdue"]["rows"]) == 5


def test_empty_state_returns_zero_counts(svc: TaskService) -> None:
    sections = svc.dashboard_sections(as_of=dt.date(2026, 3, 10))
    for card_id in DASHBOARD_CARD_IDS:
        assert sections[card_id]["count"] == 0
        assert sections[card_id]["rows"] == []
