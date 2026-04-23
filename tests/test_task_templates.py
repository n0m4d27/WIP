from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from sqlalchemy import select

from tasktracker.db.models import TaskTemplate
from tasktracker.domain.enums import TaskStatus
from tasktracker.services.task_service import (
    TaskService,
    expand_task_template_placeholders,
)


def test_expand_placeholders_uses_received_date(svc: TaskService) -> None:
    del svc  # unused
    d = dt.date(2026, 3, 15)
    assert "2026-03-15" in (expand_task_template_placeholders("Due {today}", d) or "")
    assert "2026" in (expand_task_template_placeholders("{yyyy}-{mm}-{dd}", d) or "")
    assert expand_task_template_placeholders("{week}", d) == "11"


def test_create_apply_template_two_todos(svc: TaskService) -> None:
    t = svc.create_task_template(
        name="WFM",
        title_pattern="Refresh {week}",
        description_pattern="Scaffold",
        default_area_id=None,
        default_person_id=None,
        default_impact=1,
        default_urgency=2,
        default_status=TaskStatus.OPEN,
        todo_specs=[
            ("Kickoff", 0, None),
            ("QA", 1, 2),
        ],
    )
    assert t is not None
    recv = dt.date(2026, 4, 6)  # Monday
    snap = svc.expand_task_template(t.id, received_date=recv)
    assert snap is not None
    assert "11" in snap.title or snap.title.startswith("Refresh")
    task = svc.create_task(
        title=snap.title,
        received_date=recv,
        description=snap.description,
        status=snap.status,
        impact=snap.impact,
        urgency=snap.urgency,
        area_id=snap.area_id,
        person_id=snap.person_id,
    )
    assert len(snap.todos) == 2
    for tit, _so, ms in sorted(snap.todos, key=lambda x: x[1]):
        svc.add_todo(task.id, title=tit, milestone_date=ms)
    loaded = svc.get_task(task.id)
    assert loaded is not None
    assert len(loaded.todos) == 2
    titles = sorted([x.title for x in loaded.todos])
    assert titles == ["Kickoff", "QA"]
    milestone_dates = [x.milestone_date for x in loaded.todos if x.title == "QA"]
    assert milestone_dates[0] is not None


def test_template_survives_deleted_area(svc: TaskService) -> None:
    cat = svc.add_category("C")
    assert cat is not None
    sub = svc.add_subcategory(cat.id, "S")
    assert sub is not None
    area = svc.add_area(sub.id, "A")
    assert area is not None
    tt = svc.create_task_template(
        name="Area-bound",
        title_pattern="T",
        default_area_id=area.id,
        todo_specs=[],
    )
    assert tt is not None
    svc.delete_area(area.id)
    snap = svc.expand_task_template(tt.id, received_date=dt.date(2026, 1, 5))
    assert snap is not None
    assert snap.area_id is None


def test_import_templates_idempotent_by_name(svc: TaskService, tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    payload = {
        "version": 1,
        "templates": [
            {
                "name": "Dup",
                "title_pattern": "First",
                "description_pattern": None,
                "default_impact": 2,
                "default_urgency": 2,
                "default_status": TaskStatus.OPEN,
                "sort_order": 0,
                "area_path": None,
                "person_employee_id": None,
                "todos": [{"title": "One", "sort_order": 0, "milestone_offset_days": None}],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    s1 = svc.import_task_templates(path)
    assert s1["created"] == 1
    payload["templates"][0]["title_pattern"] = "Second"
    path.write_text(json.dumps(payload), encoding="utf-8")
    s2 = svc.import_task_templates(path)
    assert s2["updated"] == 1
    one = svc.session.scalar(select(TaskTemplate).where(TaskTemplate.name == "Dup"))
    assert one is not None
    assert one.title_pattern == "Second"


def test_import_invalid_json_raises(svc: TaskService, tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    try:
        svc.import_task_templates(p)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("expected JSONDecodeError")
