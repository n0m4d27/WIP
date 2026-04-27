"""Unit tests for :mod:`tasktracker.services.shift_service`.

These tests reuse the :fixture:`svc` session factory from conftest so
the shift service runs against the same in-memory SQLite the regular
task service tests use. No Qt here, so they stay fast on Windows.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tasktracker.db.models import Task, TodoItem
from tasktracker.domain.enums import TaskStatus
from tasktracker.services.shift_service import (
    ShiftPlan,
    ShiftPlanRow,
    ShiftService,
)
from tasktracker.services.task_service import TaskService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def shift(svc: TaskService) -> ShiftService:
    return ShiftService(svc.session)


def _seed_task_with_todos(
    svc: TaskService,
    *,
    title: str = "Shift target",
    due: dt.date | None = dt.date(2026, 5, 4),
    milestones: list[dt.date | None] | None = None,
) -> Task:
    task = svc.create_task(
        title=title,
        received_date=dt.date(2026, 5, 1),
        due_date=due,
    )
    for i, ms in enumerate(milestones or []):
        svc.add_todo(task.id, title=f"step {i}", milestone_date=ms)
    return task


# ---------------------------------------------------------------------------
# Calendar-day math
# ---------------------------------------------------------------------------


def test_preview_task_shift_calendar_days(svc: TaskService, shift: ShiftService) -> None:
    t = _seed_task_with_todos(svc, milestones=[dt.date(2026, 5, 6)])
    plan = shift.preview_task_shift([t.id], 3)
    due_row = next(r for r in plan.rows if r.entity_type == "task")
    ms_row = next(r for r in plan.rows if r.entity_type == "todo")
    assert due_row.old_value == dt.date(2026, 5, 4)
    assert due_row.new_value == dt.date(2026, 5, 7)
    assert ms_row.new_value == dt.date(2026, 5, 9)


def test_preview_task_shift_negative_delta(svc: TaskService, shift: ShiftService) -> None:
    t = _seed_task_with_todos(svc, milestones=[dt.date(2026, 5, 10)])
    plan = shift.preview_task_shift([t.id], -2)
    due_row = next(r for r in plan.rows if r.entity_type == "task")
    ms_row = next(r for r in plan.rows if r.entity_type == "todo")
    assert due_row.new_value == dt.date(2026, 5, 2)
    assert ms_row.new_value == dt.date(2026, 5, 8)


def test_preview_task_shift_business_days(svc: TaskService, shift: ShiftService) -> None:
    # 2026-05-04 is a Monday. Shifting +5 business days should land
    # on 2026-05-11 (the following Monday) with no weekend in between.
    t = _seed_task_with_todos(svc, due=dt.date(2026, 5, 4), milestones=[dt.date(2026, 5, 4)])
    plan = shift.preview_task_shift([t.id], 5, business_days=True)
    due_row = next(r for r in plan.rows if r.entity_type == "task")
    assert due_row.new_value == dt.date(2026, 5, 11)
    assert due_row.flag is None  # business-day shifts never flag


def test_preview_task_shift_flags_weekend_landing(
    svc: TaskService, shift: ShiftService
) -> None:
    # Shift a Friday due date +1 calendar day -> lands on Saturday,
    # which should raise a 'weekend' flag in preview.
    t = _seed_task_with_todos(svc, due=dt.date(2026, 5, 1))
    plan = shift.preview_task_shift([t.id], 1)
    due_row = next(r for r in plan.rows if r.entity_type == "task")
    assert due_row.flag == "weekend"


def test_preview_task_shift_no_op_row(svc: TaskService, shift: ShiftService) -> None:
    t = _seed_task_with_todos(svc, due=None)
    plan = shift.preview_task_shift([t.id], 4)
    due_row = next(r for r in plan.rows if r.entity_type == "task")
    assert due_row.flag == "no-op"


# ---------------------------------------------------------------------------
# Apply / undo round-trip
# ---------------------------------------------------------------------------


def test_apply_shift_writes_exactly_what_preview_shows(
    svc: TaskService, shift: ShiftService
) -> None:
    t = _seed_task_with_todos(
        svc,
        milestones=[dt.date(2026, 5, 5), dt.date(2026, 5, 6)],
    )
    plan = shift.preview_task_shift([t.id], 7)
    result = shift.apply_shift(plan)
    expected_rows = [r for r in plan.rows if r.flag != "no-op"]
    # result.rows should be a subset of expected (nothing new appears)
    for row in result.rows:
        assert row in expected_rows
    refreshed = svc.get_task(t.id)
    assert refreshed is not None
    assert refreshed.due_date == dt.date(2026, 5, 11)
    for td in refreshed.todos:
        # Both milestones shifted +7 days.
        assert td.milestone_date in (dt.date(2026, 5, 12), dt.date(2026, 5, 13))


def test_undo_restores_prior_values(svc: TaskService, shift: ShiftService) -> None:
    t = _seed_task_with_todos(svc, milestones=[dt.date(2026, 5, 6)])
    plan = shift.preview_task_shift([t.id], 10)
    result = shift.apply_shift(plan)
    shift.undo_shift(result)
    restored = svc.get_task(t.id)
    assert restored is not None
    assert restored.due_date == dt.date(2026, 5, 4)
    assert restored.todos[0].milestone_date == dt.date(2026, 5, 6)


def test_apply_skips_rows_with_out_of_band_changes(
    svc: TaskService, shift: ShiftService
) -> None:
    """If the underlying date no longer matches the preview's
    ``old_value`` - e.g. another client edited the task between preview
    and apply - that row is silently skipped, not applied with stale
    delta math."""
    t = _seed_task_with_todos(svc)
    plan = shift.preview_task_shift([t.id], 4)
    # Simulate an out-of-band edit to the task's due date.
    svc.update_task_fields(t.id, due_date=dt.date(2026, 6, 1))
    result = shift.apply_shift(plan)
    assert all(r.entity_type != "task" for r in result.rows)
    refreshed = svc.get_task(t.id)
    assert refreshed is not None
    assert refreshed.due_date == dt.date(2026, 6, 1)


def test_apply_shift_logs_bulk_shift_audit(svc: TaskService, shift: ShiftService) -> None:
    t = _seed_task_with_todos(svc)
    result = shift.apply_shift(shift.preview_task_shift([t.id], 2))
    tl = svc.combined_timeline(t.id)
    assert any(
        e.kind == "audit" and "bulk_shift" in e.summary
        for e in tl
    ), f"expected bulk_shift audit entry, got {[e.summary for e in tl]}"
    assert result.shift_id in " ".join(e.summary for e in tl if e.kind == "audit")


# ---------------------------------------------------------------------------
# Slip from date + filters
# ---------------------------------------------------------------------------


def test_preview_slip_from_date_anchor_filters_by_date(
    svc: TaskService, shift: ShiftService
) -> None:
    before = _seed_task_with_todos(svc, title="Before anchor", due=dt.date(2026, 5, 1))
    on_or_after = _seed_task_with_todos(svc, title="Needs slip", due=dt.date(2026, 5, 10))
    plan = shift.preview_slip_from_date(dt.date(2026, 5, 10), 3)
    affected_ids = {r.id for r in plan.rows if r.entity_type == "task"}
    assert on_or_after.id in affected_ids
    assert before.id not in affected_ids


def test_preview_slip_excludes_closed_tasks_by_default(
    svc: TaskService, shift: ShiftService
) -> None:
    open_t = _seed_task_with_todos(svc, title="Open", due=dt.date(2026, 5, 12))
    closed_t = _seed_task_with_todos(svc, title="Closed", due=dt.date(2026, 5, 14))
    svc.close_task(closed_t.id, closed_on=dt.date(2026, 5, 14), resolution="Closed after shift")
    plan = shift.preview_slip_from_date(dt.date(2026, 5, 1), 2)
    ids = {r.id for r in plan.rows if r.entity_type == "task"}
    assert open_t.id in ids
    assert closed_t.id not in ids


def test_preview_slip_filter_by_for_person(svc: TaskService, shift: ShiftService) -> None:
    ada = svc.add_person("Ada", "Lovelace", "E001")
    grace = svc.add_person("Grace", "Hopper", "E002")
    assert ada and grace
    my_task = svc.create_task(
        title="Mine",
        received_date=dt.date(2026, 5, 1),
        due_date=dt.date(2026, 5, 20),
        person_id=ada.id,
    )
    other = svc.create_task(
        title="Not mine",
        received_date=dt.date(2026, 5, 1),
        due_date=dt.date(2026, 5, 21),
        person_id=grace.id,
    )
    plan = shift.preview_slip_from_date(
        dt.date(2026, 5, 1), 4, for_person_ids=[ada.id]
    )
    ids = {r.id for r in plan.rows if r.entity_type == "task"}
    assert my_task.id in ids
    assert other.id not in ids


def test_preview_slip_filter_by_min_priority(svc: TaskService, shift: ShiftService) -> None:
    p1 = svc.create_task(
        title="Critical", received_date=dt.date(2026, 5, 1),
        due_date=dt.date(2026, 5, 10), impact=1, urgency=1,
    )
    p5 = svc.create_task(
        title="Planning", received_date=dt.date(2026, 5, 1),
        due_date=dt.date(2026, 5, 10), impact=3, urgency=3,
    )
    plan = shift.preview_slip_from_date(dt.date(2026, 5, 1), 3, min_priority=2)
    ids = {r.id for r in plan.rows if r.entity_type == "task"}
    assert p1.id in ids
    assert p5.id not in ids


# ---------------------------------------------------------------------------
# Todo-only selection shift
# ---------------------------------------------------------------------------


def test_preview_todo_shift_only_touches_listed_ids(
    svc: TaskService, shift: ShiftService
) -> None:
    t = _seed_task_with_todos(
        svc,
        milestones=[dt.date(2026, 5, 4), dt.date(2026, 5, 5), dt.date(2026, 5, 6)],
    )
    parent = svc.get_task(t.id)
    assert parent is not None
    todos_sorted = sorted(parent.todos, key=lambda x: x.sort_order)
    plan = shift.preview_todo_shift([todos_sorted[0].id, todos_sorted[2].id], 1)
    assert {r.id for r in plan.rows} == {todos_sorted[0].id, todos_sorted[2].id}
    assert all(r.entity_type == "todo" for r in plan.rows)


def test_task_service_shift_task_milestones_wrapper(
    svc: TaskService,
) -> None:
    """The tiny wrapper on :class:`TaskService` is what the calendar
    quick-edit dialog calls on save when the "also shift todos"
    checkbox is on; here we verify it shifts every todo and returns
    the correct count."""
    t = _seed_task_with_todos(
        svc, milestones=[dt.date(2026, 6, 1), dt.date(2026, 6, 2), None],
    )
    touched = svc.shift_task_milestones(t.id, 2)
    assert touched == 2
    reloaded = svc.get_task(t.id)
    assert reloaded is not None
    ms = sorted(
        (td.milestone_date for td in reloaded.todos if td.milestone_date is not None)
    )
    assert ms == [dt.date(2026, 6, 3), dt.date(2026, 6, 4)]


def test_task_service_shift_task_milestones_business_mode(
    svc: TaskService,
) -> None:
    # Add a holiday to exercise the business-day skip logic too.
    svc.add_holiday(dt.date(2026, 6, 5), "Test holiday")
    t = _seed_task_with_todos(svc, milestones=[dt.date(2026, 6, 4)])  # Thursday
    svc.shift_task_milestones(t.id, 2, business_days=True)
    reloaded = svc.get_task(t.id)
    assert reloaded is not None
    # 6/4 Thu -> skip 6/5 holiday -> Fri 6/6 (wait 6/5 is Fri actually).
    # Let's compute: 6/5/2026 is a Friday and we add it as a holiday, so
    # Thursday + 2 business days = skip Fri(holiday) + Sat + Sun =
    # land on Monday 6/8, then another business day = Tuesday 6/9.
    assert reloaded.todos[0].milestone_date == dt.date(2026, 6, 9)
