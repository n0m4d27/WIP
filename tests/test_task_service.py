from __future__ import annotations

import datetime as dt

from tasktracker.domain.enums import RecurrenceGenerationMode, TaskStatus
from tasktracker.services.task_service import TaskService


def test_create_and_priority_recompute(svc: TaskService) -> None:
    t = svc.create_task(
        title="A",
        received_date=dt.date(2026, 1, 5),
        due_date=dt.date(2026, 1, 20),
        impact=1,
        urgency=1,
    )
    assert t.priority == 1
    svc.update_task_fields(t.id, impact=3, urgency=3)
    t2 = svc.get_task(t.id)
    assert t2 is not None
    assert t2.priority == 5


def test_next_milestone_ordered_todos(svc: TaskService) -> None:
    t = svc.create_task(title="B", received_date=dt.date(2026, 1, 1))
    svc.add_todo(t.id, title="Second", milestone_date=dt.date(2026, 1, 10))
    svc.add_todo(t.id, title="First", milestone_date=dt.date(2026, 1, 5))
    t2 = svc.get_task(t.id)
    assert t2 is not None
    # First open todo by sort_order should drive next milestone
    todos = sorted(t2.todos, key=lambda x: x.sort_order)
    assert t2.next_milestone_date == todos[0].milestone_date


def test_recurring_on_close_spawns(svc: TaskService) -> None:
    t = svc.create_task(title="Weekly", received_date=dt.date(2026, 4, 1), due_date=dt.date(2026, 4, 8))
    svc.set_recurring_rule(
        t.id,
        generation_mode=RecurrenceGenerationMode.ON_CLOSE,
        skip_weekends=False,
        skip_holidays=False,
        interval_days=7,
        todo_templates=[(0, "Step one", 0), (1, "Step two", 3)],
    )
    closed, new_t = svc.close_task(t.id, closed_on=dt.date(2026, 4, 8))
    assert closed is not None
    assert closed.status == TaskStatus.CLOSED
    assert new_t is not None
    assert new_t.title == "Weekly"
    assert len(new_t.todos) == 2
    assert new_t.recurring_rule is not None


def test_close_idempotent_no_double_spawn(svc: TaskService) -> None:
    t = svc.create_task(title="Once", received_date=dt.date(2026, 4, 1))
    svc.set_recurring_rule(
        t.id,
        generation_mode=RecurrenceGenerationMode.ON_CLOSE,
        skip_weekends=False,
        skip_holidays=False,
        interval_days=1,
        todo_templates=[],
    )
    _, n1 = svc.close_task(t.id)
    assert n1 is not None
    _, n2 = svc.close_task(t.id)
    assert n2 is None
