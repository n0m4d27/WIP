from __future__ import annotations

import datetime as dt

from tasktracker.services.task_service import TaskService


def test_tag_crud_and_attach_detach(svc: TaskService) -> None:
    t = svc.create_task(title="Tagged", received_date=dt.date(2026, 1, 1))
    tag = svc.create_tag("Q1 Planning", color_hint="blue")
    assert tag is not None
    assert svc.attach_tag_to_task(t.id, tag.id) is True
    loaded = svc.get_task(t.id)
    assert loaded is not None
    assert [x.name for x in loaded.tags] == ["Q1 Planning"]
    assert svc.detach_tag_from_task(t.id, tag.id) is True
    loaded2 = svc.get_task(t.id)
    assert loaded2 is not None
    assert loaded2.tags == []


def test_merge_tags_reassigns_rows(svc: TaskService) -> None:
    t = svc.create_task(title="Tagged", received_date=dt.date(2026, 1, 1))
    a = svc.create_tag("alpha")
    b = svc.create_tag("beta")
    assert a is not None and b is not None
    svc.attach_tag_to_task(t.id, a.id)
    assert svc.merge_tags(a.id, b.id) is True
    loaded = svc.get_task(t.id)
    assert loaded is not None
    assert [x.name for x in loaded.tags] == ["beta"]


def test_tag_filter_in_list_and_search(svc: TaskService) -> None:
    t1 = svc.create_task(title="one", received_date=dt.date(2026, 1, 1))
    t2 = svc.create_task(title="two", received_date=dt.date(2026, 1, 1))
    tag = svc.create_tag("Ops")
    assert tag is not None
    svc.attach_tag_to_task(t2.id, tag.id)
    listed = svc.list_tasks(tag_id=tag.id)
    assert [x.id for x in listed] == [t2.id]
    hits = svc.search_tasks("two", fields={"title"}, tag_id=tag.id)
    assert [h.task.id for h in hits] == [t2.id]
    hits2 = svc.search_tasks("one", fields={"title"}, tag_id=tag.id)
    assert hits2 == []
