from __future__ import annotations

import datetime as dt
import json

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


def test_ticket_numbers_increment_from_zero(svc: TaskService) -> None:
    t0 = svc.create_task(title="One", received_date=dt.date(2026, 5, 1))
    t1 = svc.create_task(title="Two", received_date=dt.date(2026, 5, 2))
    assert t0.ticket_number == 0
    assert t1.ticket_number == 1


def test_search_title_notes_and_ticket(svc: TaskService) -> None:
    a = svc.create_task(title="Network outage", received_date=dt.date(2026, 6, 1))
    b = svc.create_task(title="Printer", received_date=dt.date(2026, 6, 2))
    assert a.ticket_number == 0
    assert b.ticket_number == 1
    svc.add_note(b.id, body_html="<p>Investigate VLAN edge case</p>")

    by_title = svc.search_tasks("outage", fields={"title"})
    assert [t.id for t in by_title] == [a.id]

    by_note = svc.search_tasks("vlan", fields={"notes"})
    assert [t.id for t in by_note] == [b.id]

    by_ticket_prefixed = svc.search_tasks("T1", fields={"ticket"})
    assert [t.id for t in by_ticket_prefixed] == [b.id]


def test_task_area_and_person_assignment(svc: TaskService) -> None:
    cat = svc.add_category("Operations")
    assert cat is not None
    sub = svc.add_subcategory(cat.id, "Network")
    assert sub is not None
    area = svc.add_area(sub.id, "Core Router")
    assert area is not None
    person = svc.add_person("Ada", "Lovelace", "E100")
    assert person is not None

    t = svc.create_task(
        title="Router patch",
        received_date=dt.date(2026, 7, 1),
        area_id=area.id,
        person_id=person.id,
    )
    loaded = svc.get_task(t.id)
    assert loaded is not None
    assert loaded.area is not None
    assert loaded.area.name == "Core Router"
    assert loaded.area.subcategory.name == "Network"
    assert loaded.area.subcategory.category.name == "Operations"
    assert loaded.person is not None
    assert loaded.person.employee_id == "E100"


def test_reference_data_export_import_roundtrip(svc: TaskService, tmp_path) -> None:
    cat = svc.add_category("Ops")
    assert cat is not None
    sub = svc.add_subcategory(cat.id, "Windows")
    assert sub is not None
    area = svc.add_area(sub.id, "Patching")
    assert area is not None
    person = svc.add_person("Grace", "Hopper", "E200")
    assert person is not None

    path = tmp_path / "refs.json"
    svc.export_reference_data(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["categories"][0]["name"] == "Ops"
    assert payload["people"][0]["employee_id"] == "E200"

    # Re-import should merge and remain idempotent (no duplicate people by employee_id).
    summary = svc.import_reference_data(path)
    assert summary["categories"] >= 1
    assert summary["subcategories"] >= 1
    assert summary["areas"] >= 1
    assert summary["people"] >= 1
    assert len([p for p in svc.list_people() if p.employee_id == "E200"]) == 1


def test_update_todo_title(svc: TaskService) -> None:
    t = svc.create_task(title="Parent", received_date=dt.date(2026, 8, 1))
    todo = svc.add_todo(t.id, title="Draft report", milestone_date=dt.date(2026, 8, 10))
    assert todo is not None
    updated = svc.update_todo(todo.id, title="Draft quarterly report")
    assert updated is not None
    assert updated.title == "Draft quarterly report"
    assert updated.milestone_date == dt.date(2026, 8, 10)


def test_update_todo_set_milestone_refreshes_next(svc: TaskService) -> None:
    t = svc.create_task(title="Parent", received_date=dt.date(2026, 8, 1))
    todo = svc.add_todo(t.id, title="Kickoff")
    assert todo is not None
    before = svc.get_task(t.id)
    assert before is not None
    assert before.next_milestone_date is None
    svc.update_todo(todo.id, milestone_date=dt.date(2026, 8, 5))
    after = svc.get_task(t.id)
    assert after is not None
    assert after.next_milestone_date == dt.date(2026, 8, 5)


def test_update_todo_clear_milestone(svc: TaskService) -> None:
    t = svc.create_task(title="Parent", received_date=dt.date(2026, 8, 1))
    todo = svc.add_todo(t.id, title="Kickoff", milestone_date=dt.date(2026, 8, 5))
    assert todo is not None
    svc.update_todo(todo.id, milestone_date=None)
    reloaded = svc.get_todo(todo.id)
    assert reloaded is not None
    assert reloaded.milestone_date is None
    task = svc.get_task(t.id)
    assert task is not None
    assert task.next_milestone_date is None


def test_update_todo_missing_returns_none(svc: TaskService) -> None:
    assert svc.update_todo(999_999, title="nope") is None


def test_update_todo_empty_title_is_noop(svc: TaskService) -> None:
    t = svc.create_task(title="Parent", received_date=dt.date(2026, 8, 1))
    todo = svc.add_todo(t.id, title="Original")
    assert todo is not None
    svc.update_todo(todo.id, title="   ")
    reloaded = svc.get_todo(todo.id)
    assert reloaded is not None
    assert reloaded.title == "Original"


def test_update_task_fields_clear_due_and_closed_dates(svc: TaskService) -> None:
    t = svc.create_task(
        title="Has dates",
        received_date=dt.date(2026, 9, 1),
        due_date=dt.date(2026, 9, 15),
    )
    svc.update_task_fields(t.id, closed_date=dt.date(2026, 9, 10))
    loaded = svc.get_task(t.id)
    assert loaded is not None and loaded.due_date == dt.date(2026, 9, 15)
    assert loaded.closed_date == dt.date(2026, 9, 10)
    svc.update_task_fields(t.id, due_date=None, closed_date=None)
    cleared = svc.get_task(t.id)
    assert cleared is not None
    assert cleared.due_date is None
    assert cleared.closed_date is None


def test_update_task_fields_omitting_date_leaves_it_alone(svc: TaskService) -> None:
    t = svc.create_task(
        title="Unchanged dates",
        received_date=dt.date(2026, 9, 1),
        due_date=dt.date(2026, 9, 15),
    )
    svc.update_task_fields(t.id, title="Renamed")
    loaded = svc.get_task(t.id)
    assert loaded is not None
    assert loaded.title == "Renamed"
    assert loaded.due_date == dt.date(2026, 9, 15)


def test_update_task_fields_clear_description(svc: TaskService) -> None:
    t = svc.create_task(
        title="With desc",
        received_date=dt.date(2026, 9, 1),
        description="<p>something</p>",
    )
    assert t.description == "<p>something</p>"
    svc.update_task_fields(t.id, description=None)
    loaded = svc.get_task(t.id)
    assert loaded is not None
    assert loaded.description is None


def test_rename_category_and_duplicate_blocked(svc: TaskService) -> None:
    a = svc.add_category("Alpha")
    b = svc.add_category("Beta")
    assert a is not None and b is not None
    renamed = svc.rename_category(a.id, "AlphaPrime")
    assert renamed is not None and renamed.name == "AlphaPrime"
    assert svc.rename_category(a.id, "Beta") is None
    assert svc.rename_category(999_999, "X") is None


def test_rename_subcategory_unique_per_category(svc: TaskService) -> None:
    c = svc.add_category("C")
    assert c is not None
    s1 = svc.add_subcategory(c.id, "S1")
    s2 = svc.add_subcategory(c.id, "S2")
    assert s1 is not None and s2 is not None
    assert svc.rename_subcategory(s1.id, "S2") is None
    assert svc.rename_subcategory(s1.id, "S1b") is not None


def test_rename_area_unique_per_subcategory(svc: TaskService) -> None:
    c = svc.add_category("C")
    assert c is not None
    s = svc.add_subcategory(c.id, "S")
    assert s is not None
    a1 = svc.add_area(s.id, "A1")
    a2 = svc.add_area(s.id, "A2")
    assert a1 is not None and a2 is not None
    assert svc.rename_area(a1.id, "A2") is None
    assert svc.rename_area(a1.id, "A1b") is not None


def test_update_person_and_employee_id_collision(svc: TaskService) -> None:
    p1 = svc.add_person("Ada", "Lovelace", "E1")
    p2 = svc.add_person("Grace", "Hopper", "E2")
    assert p1 is not None and p2 is not None
    updated = svc.update_person(p1.id, "Augusta", "Ada", "E1")
    assert updated is not None
    assert updated.first_name == "Augusta"
    assert svc.update_person(p1.id, "A", "B", "E2") is None
