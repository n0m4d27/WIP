from __future__ import annotations

import datetime as dt

import pytest

from tasktracker.domain.enums import TaskStatus
from tasktracker.services.task_service import TaskService


def test_add_and_list_dependencies(svc: TaskService) -> None:
    a = svc.create_task(title="A", received_date=dt.date(2026, 1, 1))
    b = svc.create_task(title="B", received_date=dt.date(2026, 1, 1))
    dep = svc.add_dependency(a.id, b.id, note="A first")
    assert dep is not None
    up, down = svc.list_dependencies(b.id)
    assert len(up) == 1
    assert up[0].blocker_task_id == a.id
    up2, down2 = svc.list_dependencies(a.id)
    assert len(down2) == 1
    assert down2[0].blocked_task_id == b.id
    assert up2 == []


def test_dependency_cycle_guard(svc: TaskService) -> None:
    a = svc.create_task(title="A", received_date=dt.date(2026, 1, 1))
    b = svc.create_task(title="B", received_date=dt.date(2026, 1, 1))
    c = svc.create_task(title="C", received_date=dt.date(2026, 1, 1))
    assert svc.add_dependency(a.id, b.id) is not None
    assert svc.add_dependency(b.id, c.id) is not None
    with pytest.raises(ValueError):
        svc.add_dependency(c.id, a.id)


def test_open_upstream_dependency_indicator(svc: TaskService) -> None:
    blocker = svc.create_task(title="Blocker", received_date=dt.date(2026, 1, 1))
    blocked = svc.create_task(title="Blocked", received_date=dt.date(2026, 1, 1))
    assert svc.add_dependency(blocker.id, blocked.id) is not None
    assert svc.has_open_upstream_dependency(blocked.id) is True
    svc.close_task(blocker.id, resolution="done", closed_on=dt.date(2026, 1, 2))
    assert svc.get_task(blocker.id) is not None
    assert svc.get_task(blocker.id).status == TaskStatus.CLOSED  # type: ignore[union-attr]
    assert svc.has_open_upstream_dependency(blocked.id) is False


def test_dependency_picker_candidate_rules_hide_closed_on(svc: TaskService) -> None:
    current = svc.create_task(title="Current", received_date=dt.date(2026, 1, 1))
    open_ok = svc.create_task(title="Open candidate", received_date=dt.date(2026, 1, 1))
    linked = svc.create_task(title="Already linked blocker", received_date=dt.date(2026, 1, 1))
    closed = svc.create_task(title="Closed candidate", received_date=dt.date(2026, 1, 1))
    svc.close_task(closed.id, resolution="done", closed_on=dt.date(2026, 1, 2))
    assert svc.add_dependency(linked.id, current.id) is not None
    upstream, _ = svc.list_dependencies(current.id)
    already_linked = {int(dep.blocker_task_id) for dep in upstream}
    candidate_ids = {
        int(t.id)
        for t in svc.list_tasks(include_closed=False)
        if int(t.id) != int(current.id) and int(t.id) not in already_linked
    }
    assert int(open_ok.id) in candidate_ids
    assert int(linked.id) not in candidate_ids
    assert int(closed.id) not in candidate_ids
    assert int(current.id) not in candidate_ids


def test_dependency_picker_candidate_rules_hide_closed_off(svc: TaskService) -> None:
    current = svc.create_task(title="Current", received_date=dt.date(2026, 1, 1))
    open_ok = svc.create_task(title="Open candidate", received_date=dt.date(2026, 1, 1))
    linked = svc.create_task(title="Already linked blocker", received_date=dt.date(2026, 1, 1))
    closed = svc.create_task(title="Closed candidate", received_date=dt.date(2026, 1, 1))
    svc.close_task(closed.id, resolution="done", closed_on=dt.date(2026, 1, 2))
    assert svc.add_dependency(linked.id, current.id) is not None
    upstream, _ = svc.list_dependencies(current.id)
    already_linked = {int(dep.blocker_task_id) for dep in upstream}
    candidate_ids = {
        int(t.id)
        for t in svc.list_tasks(include_closed=True)
        if int(t.id) != int(current.id) and int(t.id) not in already_linked
    }
    assert int(open_ok.id) in candidate_ids
    assert int(closed.id) in candidate_ids
    assert int(linked.id) not in candidate_ids
    assert int(current.id) not in candidate_ids
