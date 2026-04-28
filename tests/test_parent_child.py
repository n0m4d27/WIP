from __future__ import annotations

import datetime as dt

import pytest

from tasktracker.domain.enums import TaskStatus
from tasktracker.services.task_service import TaskService


def test_set_and_clear_parent(svc: TaskService) -> None:
    parent = svc.create_task(title="Parent", received_date=dt.date(2026, 1, 1))
    child = svc.create_task(title="Child", received_date=dt.date(2026, 1, 1))
    updated = svc.set_parent(child.id, parent.id)
    assert updated is not None
    assert updated.parent_task_id == parent.id
    cleared = svc.clear_parent(child.id)
    assert cleared is not None
    assert cleared.parent_task_id is None


def test_parent_cycle_guard(svc: TaskService) -> None:
    a = svc.create_task(title="A", received_date=dt.date(2026, 1, 1))
    b = svc.create_task(title="B", received_date=dt.date(2026, 1, 1))
    svc.set_parent(b.id, a.id)
    with pytest.raises(ValueError):
        svc.set_parent(a.id, b.id)


def test_grandchildren_not_allowed_when_parent_is_already_child(svc: TaskService) -> None:
    a = svc.create_task(title="A", received_date=dt.date(2026, 1, 1))
    b = svc.create_task(title="B", received_date=dt.date(2026, 1, 1))
    c = svc.create_task(title="C", received_date=dt.date(2026, 1, 1))
    svc.set_parent(b.id, a.id)
    with pytest.raises(ValueError):
        svc.set_parent(c.id, b.id)


def test_grandchildren_not_allowed_when_task_already_has_children(svc: TaskService) -> None:
    a = svc.create_task(title="A", received_date=dt.date(2026, 1, 1))
    b = svc.create_task(title="B", received_date=dt.date(2026, 1, 1))
    c = svc.create_task(title="C", received_date=dt.date(2026, 1, 1))
    svc.set_parent(b.id, a.id)
    with pytest.raises(ValueError):
        svc.set_parent(a.id, c.id)


def test_delete_parent_nulls_children(svc: TaskService) -> None:
    parent = svc.create_task(title="Parent", received_date=dt.date(2026, 1, 1))
    child = svc.create_task(title="Child", received_date=dt.date(2026, 1, 1))
    svc.set_parent(child.id, parent.id)
    assert svc.delete_task(parent.id) is True
    loaded_child = svc.get_task(child.id)
    assert loaded_child is not None
    assert loaded_child.parent_task_id is None


def test_children_summary_rollups(svc: TaskService) -> None:
    parent = svc.create_task(title="Parent", received_date=dt.date(2026, 1, 1))
    overdue = svc.create_task(
        title="Overdue child",
        received_date=dt.date(2026, 1, 1),
        due_date=dt.date.today() - dt.timedelta(days=1),
    )
    blocked = svc.create_task(title="Blocked child", received_date=dt.date(2026, 1, 1))
    closed = svc.create_task(title="Closed child", received_date=dt.date(2026, 1, 1))
    svc.set_parent(overdue.id, parent.id)
    svc.set_parent(blocked.id, parent.id)
    svc.set_parent(closed.id, parent.id)
    svc.update_task_fields(blocked.id, status=TaskStatus.BLOCKED)
    svc.close_task(closed.id, resolution="done", closed_on=dt.date(2026, 1, 2))
    summary = svc.children_summary(parent.id)
    assert summary.total == 3
    assert summary.closed == 1
    assert summary.has_overdue_open_child is True
    assert summary.has_blocked_open_child is True


def test_parent_candidate_rules_respect_hide_closed_toggle(svc: TaskService) -> None:
    current = svc.create_task(title="Current", received_date=dt.date(2026, 1, 1))
    open_parent = svc.create_task(title="Open parent", received_date=dt.date(2026, 1, 1))
    closed_parent = svc.create_task(title="Closed parent", received_date=dt.date(2026, 1, 1))
    svc.close_task(closed_parent.id, resolution="done", closed_on=dt.date(2026, 1, 2))
    hidden_ids = {t.id for t in svc.eligible_parent_tasks(current.id, include_closed=False)}
    shown_ids = {t.id for t in svc.eligible_parent_tasks(current.id, include_closed=True)}
    assert open_parent.id in hidden_ids
    assert closed_parent.id not in hidden_ids
    assert closed_parent.id in shown_ids
