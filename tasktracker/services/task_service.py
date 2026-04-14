from __future__ import annotations

import csv
import datetime as dt
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from tasktracker.db.models import (
    BusinessHoliday,
    RecurringRule,
    RecurringTodoTemplate,
    Task,
    TaskBlocker,
    TaskNote,
    TaskNoteVersion,
    TaskUpdateLog,
    TodoItem,
)
from tasktracker.domain.enums import RecurrenceGenerationMode, TaskStatus
from tasktracker.domain.priority import compute_priority, priority_display


def _holidays_set(session: Session) -> set[dt.date]:
    rows = session.scalars(select(BusinessHoliday.holiday_date)).all()
    return set(rows)


def _is_business_day(
    d: dt.date,
    holidays: set[dt.date],
    *,
    skip_weekends: bool,
    skip_holidays: bool,
) -> bool:
    if skip_weekends and d.weekday() >= 5:
        return False
    if skip_holidays and d in holidays:
        return False
    return True


def next_business_on_or_after(
    start: dt.date,
    holidays: set[dt.date],
    *,
    skip_weekends: bool,
    skip_holidays: bool,
) -> dt.date:
    d = start
    for _ in range(370):
        if _is_business_day(d, holidays, skip_weekends=skip_weekends, skip_holidays=skip_holidays):
            return d
        d += dt.timedelta(days=1)
    return start


def add_business_days(
    start: dt.date,
    days: int,
    holidays: set[dt.date],
    *,
    skip_weekends: bool,
    skip_holidays: bool,
) -> dt.date:
    """Add `days` calendar steps, landing on a business day when skipping weekends/holidays."""
    if days <= 0:
        return next_business_on_or_after(
            start, holidays, skip_weekends=skip_weekends, skip_holidays=skip_holidays
        )
    d = start
    remaining = days
    while remaining > 0:
        d += dt.timedelta(days=1)
        if _is_business_day(d, holidays, skip_weekends=skip_weekends, skip_holidays=skip_holidays):
            remaining -= 1
    return d


def refresh_next_milestone(session: Session, task: Task) -> None:
    """Update denormalized next_milestone_date without reading task.todos.

    Iterating `task.todos` after commit with expire_on_commit=False can leave a
    stale empty collection in the identity map; query TodoItem directly instead.
    """
    rows = session.scalars(
        select(TodoItem)
        .where(
            TodoItem.task_id == task.id,
            TodoItem.completed_at.is_(None),
            TodoItem.milestone_date.is_not(None),
        )
        .order_by(TodoItem.sort_order)
    ).all()
    task.next_milestone_date = rows[0].milestone_date if rows else None


def _log_change(
    session: Session,
    task_id: int,
    field_name: str,
    old: Any,
    new: Any,
) -> None:
    session.add(
        TaskUpdateLog(
            task_id=task_id,
            field_name=field_name,
            old_value=None if old is None else str(old),
            new_value=None if new is None else str(new),
        )
    )


def _add_system_note(session: Session, task_id: int, body_html: str) -> None:
    note = TaskNote(task_id=task_id, is_system=True)
    session.add(note)
    session.flush()
    session.add(
        TaskNoteVersion(note_id=note.id, version_seq=1, body_html=body_html),
    )


def _note_latest_body(session: Session, note: TaskNote) -> str:
    if not note.versions:
        return ""
    latest = max(note.versions, key=lambda v: v.version_seq)
    return latest.body_html


_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _to_plain_text(value: str | None) -> str:
    if not value:
        return ""
    text = _HEAD_RE.sub(" ", value)
    text = _STYLE_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _clip(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_audit_value(field_name: str, raw: str | None) -> str:
    if raw is None:
        return "None"
    if field_name in {"description"}:
        plain = _to_plain_text(raw)
        return _clip(plain) if plain else "(empty)"
    return _clip(raw)


@dataclass
class TimelineEntry:
    at: dt.datetime
    kind: Literal["audit", "note", "note_edit"]
    summary: str
    detail: str | None = None


def _like_pattern(needle: str) -> str:
    cleaned = "".join(c for c in needle.lower() if c not in "%_\\")
    return f"%{cleaned}%"


class TaskService:
    def __init__(self, session: Session):
        self.session = session

    def _next_ticket_number(self) -> int:
        self.session.flush()
        m = self.session.scalar(select(func.coalesce(func.max(Task.ticket_number), -1)))
        return int(m) + 1

    def list_tasks(
        self,
        *,
        include_closed: bool = True,
        status: str | None = None,
    ) -> list[Task]:
        q: Select[tuple[Task]] = select(Task).options(
            selectinload(Task.todos),
            selectinload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
        )
        if not include_closed:
            q = q.where(Task.status != TaskStatus.CLOSED)
        if status:
            q = q.where(Task.status == status)
        # Due dates present first, then by due date, priority, title
        q = q.order_by(Task.ticket_number.is_(None), Task.ticket_number, Task.due_date.is_(None), Task.due_date, Task.priority, Task.title)
        return list(self.session.scalars(q).unique().all())

    def search_tasks(
        self,
        needle: str,
        *,
        fields: set[str],
        include_closed: bool = True,
    ) -> list[Task]:
        raw = needle.strip()
        if not raw:
            return self.list_tasks(include_closed=include_closed)
        pat = _like_pattern(raw)
        conds: list = []

        if "title" in fields:
            conds.append(func.lower(Task.title).like(pat))
        if "description" in fields:
            conds.append(func.lower(Task.description).like(pat))
        if "notes" in fields:
            conds.append(
                exists(
                    select(1)
                    .select_from(TaskNote)
                    .join(TaskNoteVersion, TaskNoteVersion.note_id == TaskNote.id)
                    .where(TaskNote.task_id == Task.id)
                    .where(func.lower(TaskNoteVersion.body_html).like(pat))
                )
            )
        if "todos" in fields:
            conds.append(
                exists(
                    select(1)
                    .select_from(TodoItem)
                    .where(TodoItem.task_id == Task.id)
                    .where(func.lower(TodoItem.title).like(pat))
                )
            )
        if "blockers" in fields:
            conds.append(
                exists(
                    select(1)
                    .select_from(TaskBlocker)
                    .where(TaskBlocker.task_id == Task.id)
                    .where(
                        or_(
                            func.lower(TaskBlocker.title).like(pat),
                            func.lower(TaskBlocker.reason).like(pat),
                        )
                    )
                )
            )
        if "audit" in fields:
            conds.append(
                exists(
                    select(1)
                    .select_from(TaskUpdateLog)
                    .where(TaskUpdateLog.task_id == Task.id)
                    .where(
                        or_(
                            func.lower(TaskUpdateLog.field_name).like(pat),
                            func.lower(TaskUpdateLog.old_value).like(pat),
                            func.lower(TaskUpdateLog.new_value).like(pat),
                        )
                    )
                )
            )
        if "ticket" in fields:
            tq = raw.upper().lstrip()
            if tq.startswith("T") and tq[1:].isdigit():
                conds.append(Task.ticket_number == int(tq[1:]))
            elif raw.isdigit():
                conds.append(Task.ticket_number == int(raw))

        if not conds:
            return []

        q = (
            select(Task)
            .where(or_(*conds))
            .options(
                selectinload(Task.todos),
                selectinload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
            )
            .distinct()
        )
        if not include_closed:
            q = q.where(Task.status != TaskStatus.CLOSED)
        q = q.order_by(
            Task.ticket_number.is_(None),
            Task.ticket_number,
            Task.due_date.is_(None),
            Task.due_date,
            Task.priority,
            Task.title,
        )
        return list(self.session.scalars(q).unique().all())

    def get_task(self, task_id: int) -> Task | None:
        # joinedload on collections duplicates parent rows; .unique() is required (SQLAlchemy 2).
        return self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.todos),
                selectinload(Task.notes).selectinload(TaskNote.versions),
                selectinload(Task.blockers),
                selectinload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
            )
        ).unique().one_or_none()

    def create_task(
        self,
        *,
        title: str,
        received_date: dt.date,
        due_date: dt.date | None = None,
        description: str | None = None,
        status: str = TaskStatus.OPEN,
        impact: int = 2,
        urgency: int = 2,
    ) -> Task:
        pr = compute_priority(impact=impact, urgency=urgency)
        ticket_number = self._next_ticket_number()
        task = Task(
            ticket_number=ticket_number,
            title=title.strip(),
            description=description,
            status=status,
            impact=impact,
            urgency=urgency,
            priority=pr,
            received_date=received_date,
            due_date=due_date,
        )
        self.session.add(task)
        self.session.flush()
        _log_change(self.session, task.id, "title", None, task.title)
        _log_change(self.session, task.id, "status", None, task.status)
        _log_change(self.session, task.id, "ticket_number", None, str(task.ticket_number))
        refresh_next_milestone(self.session, task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def update_task_fields(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        impact: int | None = None,
        urgency: int | None = None,
        received_date: dt.date | None = None,
        due_date: dt.date | None = None,
        closed_date: dt.date | None = None,
    ) -> Task | None:
        task = self.session.get(Task, task_id)
        if not task:
            return None

        if title is not None and title.strip() != task.title:
            _log_change(self.session, task.id, "title", task.title, title.strip())
            task.title = title.strip()
        if description is not None and description != task.description:
            _log_change(self.session, task.id, "description", task.description, description)
            task.description = description
        if status is not None and status != task.status:
            _log_change(self.session, task.id, "status", task.status, status)
            task.status = status
        if received_date is not None and received_date != task.received_date:
            _log_change(self.session, task.id, "received_date", task.received_date, received_date)
            task.received_date = received_date
        if due_date is not None and due_date != task.due_date:
            _log_change(self.session, task.id, "due_date", task.due_date, due_date)
            task.due_date = due_date
        if closed_date is not None and closed_date != task.closed_date:
            _log_change(self.session, task.id, "closed_date", task.closed_date, closed_date)
            task.closed_date = closed_date

        old_pr = task.priority
        if impact is not None and impact != task.impact:
            _log_change(self.session, task.id, "impact", task.impact, impact)
            task.impact = impact
        if urgency is not None and urgency != task.urgency:
            _log_change(self.session, task.id, "urgency", task.urgency, urgency)
            task.urgency = urgency

        new_pr = compute_priority(impact=task.impact, urgency=task.urgency)
        if new_pr != task.priority:
            _log_change(self.session, task.id, "priority", old_pr, new_pr)
            if old_pr != new_pr:
                _add_system_note(
                    self.session,
                    task.id,
                    f"<p>Priority updated automatically to <b>{priority_display(new_pr)}</b> "
                    f"(Impact {task.impact}, Urgency {task.urgency}).</p>",
                )
            task.priority = new_pr

        refresh_next_milestone(self.session, task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def close_task(self, task_id: int, *, closed_on: dt.date | None = None) -> tuple[Task | None, Task | None]:
        """Set closed, run on_close recurrence. Returns (closed_task, new_task_or_none)."""
        task = self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                joinedload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
            )
        ).unique().one_or_none()
        if not task:
            return None, None
        close_day = closed_on or dt.date.today()
        was_already_closed = task.status == TaskStatus.CLOSED
        if not was_already_closed:
            old_status = task.status
            old_closed = task.closed_date
            task.status = TaskStatus.CLOSED
            task.closed_date = close_day
            _log_change(self.session, task.id, "status", old_status, TaskStatus.CLOSED)
            _log_change(self.session, task.id, "closed_date", old_closed, close_day)
        refresh_next_milestone(self.session, task)

        new_task: Task | None = None
        rule = task.recurring_rule
        on_close = RecurrenceGenerationMode.ON_CLOSE.value
        if (
            not was_already_closed
            and rule is not None
            and str(rule.generation_mode) == on_close
        ):
            new_task = self._spawn_recurring_successor(task, rule)

        self.session.commit()
        self.session.refresh(task)
        if new_task:
            self.session.refresh(new_task)
        return task, new_task

    def _spawn_recurring_successor(self, closed: Task, rule: RecurringRule) -> Task:
        holidays = _holidays_set(self.session)
        recv = next_business_on_or_after(
            closed.closed_date or dt.date.today(),
            holidays,
            skip_weekends=rule.skip_weekends,
            skip_holidays=rule.skip_holidays,
        )
        due = add_business_days(
            recv,
            rule.interval_days,
            holidays,
            skip_weekends=rule.skip_weekends,
            skip_holidays=rule.skip_holidays,
        )
        pr = compute_priority(impact=closed.impact, urgency=closed.urgency)
        tn = self._next_ticket_number()
        nt = Task(
            ticket_number=tn,
            title=closed.title,
            description=closed.description,
            status=TaskStatus.OPEN,
            impact=closed.impact,
            urgency=closed.urgency,
            priority=pr,
            received_date=recv,
            due_date=due,
            closed_date=None,
        )
        self.session.add(nt)
        self.session.flush()
        _log_change(self.session, nt.id, "title", None, nt.title)
        _log_change(self.session, nt.id, "ticket_number", None, str(nt.ticket_number))
        _log_change(self.session, nt.id, "created_from_recurring", None, str(closed.id))

        for tmpl in sorted(rule.todo_templates, key=lambda t: t.sort_order):
            ms: dt.date | None = None
            if tmpl.milestone_offset_days is not None:
                ms = recv + dt.timedelta(days=tmpl.milestone_offset_days)
            self.session.add(
                TodoItem(
                    task_id=nt.id,
                    sort_order=tmpl.sort_order,
                    title=tmpl.title,
                    milestone_date=ms,
                )
            )

        nr = RecurringRule(
            task_id=nt.id,
            generation_mode=rule.generation_mode,
            skip_weekends=rule.skip_weekends,
            skip_holidays=rule.skip_holidays,
            interval_days=rule.interval_days,
        )
        self.session.add(nr)
        self.session.flush()
        for tmpl in sorted(rule.todo_templates, key=lambda t: t.sort_order):
            self.session.add(
                RecurringTodoTemplate(
                    rule_id=nr.id,
                    sort_order=tmpl.sort_order,
                    title=tmpl.title,
                    milestone_offset_days=tmpl.milestone_offset_days,
                )
            )

        refresh_next_milestone(self.session, nt)
        return nt

    def set_recurring_rule(
        self,
        task_id: int,
        *,
        generation_mode: str,
        skip_weekends: bool,
        skip_holidays: bool,
        interval_days: int,
        todo_templates: list[tuple[int, str, int | None]],
    ) -> None:
        task = self.session.get(Task, task_id)
        if not task:
            return
        if task.recurring_rule:
            self.session.delete(task.recurring_rule)
            self.session.flush()
        mode_str = (
            generation_mode.value
            if isinstance(generation_mode, RecurrenceGenerationMode)
            else str(generation_mode)
        )
        rule = RecurringRule(
            task_id=task_id,
            generation_mode=mode_str,
            skip_weekends=skip_weekends,
            skip_holidays=skip_holidays,
            interval_days=interval_days,
        )
        self.session.add(rule)
        self.session.flush()
        for sort_order, title, offset in todo_templates:
            self.session.add(
                RecurringTodoTemplate(
                    rule_id=rule.id,
                    sort_order=sort_order,
                    title=title,
                    milestone_offset_days=offset,
                )
            )
        self.session.commit()

    def clear_recurring_rule(self, task_id: int) -> None:
        task = self.session.get(Task, task_id)
        if task and task.recurring_rule:
            self.session.delete(task.recurring_rule)
            self.session.commit()

    def add_todo(
        self,
        task_id: int,
        *,
        title: str,
        milestone_date: dt.date | None = None,
    ) -> TodoItem | None:
        task = self.session.get(Task, task_id)
        if not task:
            return None
        order = max((t.sort_order for t in task.todos), default=-1) + 1
        todo = TodoItem(task_id=task_id, sort_order=order, title=title.strip(), milestone_date=milestone_date)
        self.session.add(todo)
        refresh_next_milestone(self.session, task)
        self.session.commit()
        self.session.refresh(todo)
        return todo

    def complete_todo(self, todo_id: int) -> None:
        todo = self.session.get(TodoItem, todo_id)
        if not todo or todo.completed_at:
            return
        todo.completed_at = dt.datetime.now(dt.UTC)
        task = self.session.get(Task, todo.task_id)
        if task:
            refresh_next_milestone(self.session, task)
        self.session.commit()

    def reorder_todo(self, todo_id: int, new_index: int) -> None:
        todo = self.session.get(TodoItem, todo_id)
        if not todo:
            return
        task = self.session.scalar(
            select(Task)
            .where(Task.id == todo.task_id)
            .options(joinedload(Task.todos))
        )
        if not task:
            return
        others = [t for t in sorted(task.todos, key=lambda x: x.sort_order) if t.id != todo.id]
        new_index = max(0, min(new_index, len(others)))
        others.insert(new_index, todo)
        for i, t in enumerate(others):
            t.sort_order = i
        refresh_next_milestone(self.session, task)
        self.session.commit()

    def add_note(self, task_id: int, *, body_html: str, is_system: bool = False) -> TaskNote | None:
        task = self.session.get(Task, task_id)
        if not task:
            return None
        note = TaskNote(task_id=task_id, is_system=is_system)
        self.session.add(note)
        self.session.flush()
        self.session.add(TaskNoteVersion(note_id=note.id, version_seq=1, body_html=body_html))
        self.session.commit()
        self.session.refresh(note)
        return note

    def update_note_body(self, note_id: int, body_html: str) -> None:
        note = self.session.get(TaskNote, note_id, options=[joinedload(TaskNote.versions)])
        if not note or note.is_system:
            return
        seq = max((v.version_seq for v in note.versions), default=0) + 1
        self.session.add(TaskNoteVersion(note_id=note.id, version_seq=seq, body_html=body_html))
        self.session.commit()

    def add_blocker(self, task_id: int, *, title: str, reason: str | None = None) -> TaskBlocker | None:
        task = self.session.get(Task, task_id)
        if not task:
            return None
        b = TaskBlocker(task_id=task_id, title=title.strip(), reason=reason)
        self.session.add(b)
        if task.status != TaskStatus.BLOCKED:
            _log_change(self.session, task.id, "status", task.status, TaskStatus.BLOCKED)
            task.status = TaskStatus.BLOCKED
        self.session.commit()
        self.session.refresh(b)
        return b

    def clear_blocker(self, blocker_id: int) -> None:
        b = self.session.get(TaskBlocker, blocker_id)
        if not b or b.cleared_at:
            return
        b.cleared_at = dt.datetime.now(dt.UTC)
        task = self.session.get(Task, b.task_id)
        if task:
            open_blockers = [x for x in task.blockers if x.cleared_at is None and x.id != b.id]
            if not open_blockers and task.status == TaskStatus.BLOCKED:
                _log_change(self.session, task.id, "status", task.status, TaskStatus.IN_PROGRESS)
                task.status = TaskStatus.IN_PROGRESS
        self.session.commit()

    def combined_timeline(self, task_id: int) -> list[TimelineEntry]:
        task = self.session.get(Task, task_id)
        if not task:
            return []
        logs = self.session.scalars(
            select(TaskUpdateLog)
            .where(TaskUpdateLog.task_id == task_id)
            .order_by(TaskUpdateLog.changed_at)
        ).all()
        notes = list(
            self.session.scalars(
                select(TaskNote)
                .where(TaskNote.task_id == task_id)
                .options(joinedload(TaskNote.versions))
                .order_by(TaskNote.created_at)
            ).unique().all()
        )
        entries: list[TimelineEntry] = []
        for log in logs:
            old_v = _format_audit_value(log.field_name, log.old_value)
            new_v = _format_audit_value(log.field_name, log.new_value)
            entries.append(
                TimelineEntry(
                    at=log.changed_at,
                    kind="audit",
                    summary=f"{log.field_name}: {old_v} -> {new_v}",
                )
            )
        for note in notes:
            for v in sorted(note.versions, key=lambda x: x.version_seq):
                kind: Literal["note", "note_edit"] = "note" if v.version_seq == 1 else "note_edit"
                prefix = "[System] " if note.is_system else ""
                detail = _clip(_to_plain_text(v.body_html), limit=200)
                entries.append(
                    TimelineEntry(
                        at=v.created_at,
                        kind=kind,
                        summary=f"{prefix}Note v{v.version_seq}",
                        detail=detail,
                    )
                )
        entries.sort(key=lambda e: e.at)
        return entries

    def calendar_events(
        self,
        *,
        include_due: bool = True,
        include_milestones: bool = True,
        include_received: bool = False,
        include_closed: bool = False,
        include_closed_tasks: bool = False,
        from_date: dt.date | None = None,
        to_date: dt.date | None = None,
    ) -> list[dict[str, Any]]:
        tasks = self.list_tasks(include_closed=include_closed_tasks)
        holidays = _holidays_set(self.session)
        out: list[dict[str, Any]] = []
        d0, d1 = from_date, to_date

        def in_range(d: dt.date | None) -> bool:
            if d is None:
                return False
            if d0 and d < d0:
                return False
            if d1 and d > d1:
                return False
            return True

        for t in tasks:
            if include_due and in_range(t.due_date):
                out.append(
                    {
                        "date": t.due_date,
                        "type": "due",
                        "label": t.title,
                        "task_id": t.id,
                        "priority": t.priority,
                    }
                )
            if include_received and in_range(t.received_date):
                out.append(
                    {
                        "date": t.received_date,
                        "type": "received",
                        "label": t.title,
                        "task_id": t.id,
                        "priority": t.priority,
                    }
                )
            if include_closed and t.closed_date and in_range(t.closed_date):
                out.append(
                    {
                        "date": t.closed_date,
                        "type": "closed",
                        "label": t.title,
                        "task_id": t.id,
                        "priority": t.priority,
                    }
                )
            if include_milestones:
                for todo in t.todos:
                    if todo.completed_at is None and in_range(todo.milestone_date):
                        out.append(
                            {
                                "date": todo.milestone_date,
                                "type": "milestone",
                                "label": f"{t.title} — {todo.title}",
                                "task_id": t.id,
                                "priority": t.priority,
                            }
                        )
        for h in holidays:
            if in_range(h):
                out.append({"date": h, "type": "holiday", "label": "Holiday", "task_id": None, "priority": 99})
        out.sort(key=lambda r: (r["date"], r["priority"], r["label"] or ""))
        return out

    def export_tasks_csv(self, path: Path) -> None:
        tasks = self.list_tasks(include_closed=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "id",
                    "ticket_number",
                    "title",
                    "status",
                    "impact",
                    "urgency",
                    "priority",
                    "received_date",
                    "due_date",
                    "closed_date",
                    "next_milestone_date",
                ]
            )
            for t in tasks:
                w.writerow(
                    [
                        t.id,
                        t.ticket_number,
                        t.title,
                        t.status,
                        t.impact,
                        t.urgency,
                        t.priority,
                        t.received_date.isoformat(),
                        t.due_date.isoformat() if t.due_date else "",
                        t.closed_date.isoformat() if t.closed_date else "",
                        t.next_milestone_date.isoformat() if t.next_milestone_date else "",
                    ]
                )

    def export_tasks_excel(self, path: Path) -> None:
        from openpyxl import Workbook

        tasks = self.list_tasks(include_closed=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "Tasks"
        headers = [
            "id",
            "ticket_number",
            "title",
            "status",
            "impact",
            "urgency",
            "priority",
            "received_date",
            "due_date",
            "closed_date",
            "next_milestone_date",
        ]
        ws.append(headers)
        for t in tasks:
            ws.append(
                [
                    t.id,
                    t.ticket_number,
                    t.title,
                    t.status,
                    t.impact,
                    t.urgency,
                    t.priority,
                    t.received_date.isoformat(),
                    t.due_date.isoformat() if t.due_date else "",
                    t.closed_date.isoformat() if t.closed_date else "",
                    t.next_milestone_date.isoformat() if t.next_milestone_date else "",
                ]
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)

    def report_overdue(self) -> list[Task]:
        today = dt.date.today()
        tasks = self.list_tasks(include_closed=False)
        return [t for t in tasks if t.due_date and t.due_date < today]

    def report_due_this_week(self) -> list[Task]:
        today = dt.date.today()
        end = today + dt.timedelta(days=7)
        tasks = self.list_tasks(include_closed=False)
        return [t for t in tasks if t.due_date and today <= t.due_date <= end]

    def report_closure_velocity(self, days: int = 30) -> dict[str, Any]:
        """Count tasks closed in the last `days` days."""
        since = dt.date.today() - dt.timedelta(days=days)
        tasks = self.list_tasks(include_closed=True)
        closed = [t for t in tasks if t.closed_date and t.closed_date >= since]
        return {"since": since.isoformat(), "days_window": days, "closed_count": len(closed)}

    def list_holidays(self) -> list[BusinessHoliday]:
        return list(
            self.session.scalars(select(BusinessHoliday).order_by(BusinessHoliday.holiday_date)).all()
        )

    def add_holiday(self, holiday_date: dt.date, label: str | None = None) -> BusinessHoliday | None:
        if self.session.scalar(select(BusinessHoliday).where(BusinessHoliday.holiday_date == holiday_date)):
            return None
        h = BusinessHoliday(holiday_date=holiday_date, label=label)
        self.session.add(h)
        self.session.commit()
        self.session.refresh(h)
        return h

    def delete_holiday(self, holiday_id: int) -> None:
        h = self.session.get(BusinessHoliday, holiday_id)
        if h:
            self.session.delete(h)
            self.session.commit()
