"""Centralised date-shift engine for task due dates and todo milestones.

Three call sites need the same primitives:

* The calendar quick-edit dialog (shift selected todos by N days; shift
  all todos on save when the task's due date changed).
* The Tasks tab multi-select "Shift dates…" action.
* The Edit menu "Slip schedule from date…" tool.

Each call site gets a preview (dry-run) it can show to the user, then
applies the plan atomically. Apply returns a :class:`ShiftResult` that
includes an inverse plan so ``MainWindow`` can offer a single-level
undo without re-deriving what was touched.

The service intentionally owns all the arithmetic, business-day
awareness, audit logging, and denormalized-cache refresh; UI code only
needs to collect parameters and display rows.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from tasktracker.db.models import Task, TodoItem
from tasktracker.domain.enums import TaskStatus
from tasktracker.domain.ticket import format_task_ticket
from tasktracker.services.task_service import (
    _holidays_set,
    _log_change,
    refresh_next_milestone,
    shift_business_days,
)

EntityKind = Literal["task", "todo"]
FieldKind = Literal["due_date", "milestone_date"]


@dataclass(frozen=True)
class ShiftPlanRow:
    """A single proposed date change.

    ``flag`` is used by preview rendering to highlight potentially
    problematic landings (``weekend`` or ``holiday`` for calendar-day
    shifts; ``no-op`` when there's nothing to shift - e.g. a task with
    no due date). Rows carry enough context (``ticket``, ``title``) to
    render the preview table without re-hydrating parent objects.
    """

    entity_type: EntityKind
    id: int
    ticket: str | None
    title: str
    field: FieldKind
    old_value: dt.date | None
    new_value: dt.date | None
    flag: str | None


@dataclass(frozen=True)
class ShiftPlan:
    """Immutable description of a proposed shift.

    Produced by the ``preview_*`` methods, consumed by
    :meth:`ShiftService.apply_shift`. ``params`` is a JSON-friendly
    record of the user-facing parameters (delta, business-days flag,
    filters) so the UI can show them alongside the row table and the
    Activity log can reference them.
    """

    rows: tuple[ShiftPlanRow, ...]
    summary: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ShiftResult:
    """What was actually written to the database during
    :meth:`ShiftService.apply_shift`, plus the inverse plan for undo."""

    shift_id: str
    applied_at: dt.datetime
    rows: tuple[ShiftPlanRow, ...]
    inverse: ShiftPlan

    @property
    def changed_row_count(self) -> int:
        return sum(1 for r in self.rows if r.old_value != r.new_value)

    def describe(self) -> str:
        """Short human-readable description for menu tooltips."""
        return (
            f"{len(self.rows)} row(s) shifted (id {self.shift_id})"
        )


# Statuses that are excluded from "slip from date" by default; the
# assumption is that closed / cancelled work doesn't need rescheduling.
_DEFAULT_EXCLUDED_STATUSES: frozenset[str] = frozenset(
    {TaskStatus.CLOSED.value, TaskStatus.CANCELLED.value}
)


class ShiftService:
    """Service class that owns all bulk shift logic.

    Instances are cheap; construct one per UI operation so it shares
    the caller's ``Session`` (and therefore its transaction scope).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _shift_date(
        self,
        d: dt.date | None,
        delta_days: int,
        business_days: bool,
        holidays: set[dt.date],
    ) -> dt.date | None:
        if d is None or delta_days == 0:
            return d
        if business_days:
            return shift_business_days(
                d, delta_days, holidays,
                skip_weekends=True, skip_holidays=True,
            )
        return d + dt.timedelta(days=delta_days)

    def _flag_for_date(
        self,
        new: dt.date | None,
        holidays: set[dt.date],
        *,
        business_days: bool,
    ) -> str | None:
        """Return a highlight flag for calendar-day landings that fall
        on weekends or holidays. Business-day shifts never flag because
        they intentionally skipped over those days already."""
        if new is None or business_days:
            return None
        if new in holidays:
            return "holiday"
        if new.weekday() >= 5:
            return "weekend"
        return None

    @staticmethod
    def _format_ticket(task: Task | None) -> str | None:
        if task is None or task.ticket_number is None:
            return None
        return format_task_ticket(task.ticket_number)

    # ------------------------------------------------------------------
    # Previews
    # ------------------------------------------------------------------

    def preview_task_shift(
        self,
        task_ids: Sequence[int],
        delta_days: int,
        *,
        business_days: bool = False,
        include_todos: bool = True,
    ) -> ShiftPlan:
        """Preview shifting each task's due date (and, optionally,
        every attached todo milestone) by ``delta_days``.

        Tasks with ``due_date is None`` produce a ``no-op`` row so the
        user can see at a glance which tasks have nothing to shift;
        todos with ``milestone_date is None`` are skipped silently.
        """
        holidays = _holidays_set(self.session) if business_days or True else set()
        rows: list[ShiftPlanRow] = []
        task_field_rows = 0
        todo_field_rows = 0
        seen_task_ids: list[int] = []
        for tid in task_ids:
            task = self.session.get(Task, tid)
            if task is None:
                continue
            seen_task_ids.append(task.id)
            ticket = self._format_ticket(task)
            if task.due_date is not None:
                new = self._shift_date(task.due_date, delta_days, business_days, holidays)
                flag = self._flag_for_date(new, holidays, business_days=business_days)
                rows.append(ShiftPlanRow(
                    entity_type="task", id=task.id, ticket=ticket, title=task.title,
                    field="due_date", old_value=task.due_date, new_value=new, flag=flag,
                ))
                task_field_rows += 1
            else:
                rows.append(ShiftPlanRow(
                    entity_type="task", id=task.id, ticket=ticket, title=task.title,
                    field="due_date", old_value=None, new_value=None, flag="no-op",
                ))
            if include_todos:
                todos = self.session.scalars(
                    select(TodoItem)
                    .where(TodoItem.task_id == task.id)
                    .order_by(TodoItem.sort_order)
                ).all()
                for td in todos:
                    if td.milestone_date is None:
                        continue
                    new = self._shift_date(
                        td.milestone_date, delta_days, business_days, holidays
                    )
                    flag = self._flag_for_date(new, holidays, business_days=business_days)
                    rows.append(ShiftPlanRow(
                        entity_type="todo", id=td.id, ticket=ticket, title=td.title,
                        field="milestone_date", old_value=td.milestone_date,
                        new_value=new, flag=flag,
                    ))
                    todo_field_rows += 1
        mode = "business days" if business_days else "calendar days"
        summary = (
            f"Shift {len(seen_task_ids)} task(s) by {delta_days:+d} {mode}. "
            f"{task_field_rows} task due date(s), {todo_field_rows} todo milestone(s)."
        )
        return ShiftPlan(
            rows=tuple(rows),
            summary=summary,
            params={
                "mode": "tasks",
                "delta_days": delta_days,
                "business_days": business_days,
                "include_todos": include_todos,
                "task_ids": list(seen_task_ids),
            },
        )

    def preview_slip_from_date(
        self,
        anchor_date: dt.date,
        delta_days: int,
        *,
        business_days: bool = False,
        include_todos: bool = True,
        for_person_ids: list[int] | None = None,
        area_ids: list[int] | None = None,
        min_priority: int | None = None,
        statuses: list[str] | None = None,
    ) -> ShiftPlan:
        """Preview a "slip" that shifts every task with a due date on or
        after ``anchor_date`` by ``delta_days``.

        Filters are ANDed: ``for_person_ids`` / ``area_ids`` / statuses.
        ``min_priority`` keeps tasks with priority *less than or equal
        to* the threshold (recall P1 > P5 in this app's ordering, so
        ``min_priority=2`` keeps P1+P2 only). When ``statuses`` is
        ``None`` the default filter excludes closed and cancelled work.
        """
        q = select(Task).where(Task.due_date.is_not(None)).where(Task.due_date >= anchor_date)
        if statuses is None:
            q = q.where(Task.status.not_in(_DEFAULT_EXCLUDED_STATUSES))
        elif statuses:
            q = q.where(Task.status.in_(statuses))
        if for_person_ids:
            q = q.where(Task.person_id.in_(for_person_ids))
        if area_ids:
            q = q.where(Task.area_id.in_(area_ids))
        if min_priority is not None:
            q = q.where(Task.priority <= min_priority)
        q = q.order_by(Task.due_date, Task.ticket_number)
        task_ids = [t.id for t in self.session.scalars(q).all()]
        inner = self.preview_task_shift(
            task_ids,
            delta_days,
            business_days=business_days,
            include_todos=include_todos,
        )
        params = dict(inner.params)
        params.update({
            "mode": "slip",
            "anchor_date": anchor_date.isoformat(),
            "for_person_ids": for_person_ids or [],
            "area_ids": area_ids or [],
            "min_priority": min_priority,
            "statuses": list(statuses or []),
        })
        summary = (
            f"Slip from {anchor_date.isoformat()} by {delta_days:+d} "
            f"{'business' if business_days else 'calendar'} day(s). "
            f"{len(task_ids)} task(s) matched filters."
        )
        return ShiftPlan(rows=inner.rows, summary=summary, params=params)

    def preview_todo_shift(
        self,
        todo_ids: Sequence[int],
        delta_days: int,
        *,
        business_days: bool = False,
    ) -> ShiftPlan:
        """Preview shifting only the listed todos' milestone dates."""
        holidays = _holidays_set(self.session)
        rows: list[ShiftPlanRow] = []
        for tid in todo_ids:
            td = self.session.get(TodoItem, tid)
            if td is None or td.milestone_date is None:
                continue
            parent = self.session.get(Task, td.task_id)
            ticket = self._format_ticket(parent)
            new = self._shift_date(
                td.milestone_date, delta_days, business_days, holidays
            )
            flag = self._flag_for_date(new, holidays, business_days=business_days)
            rows.append(ShiftPlanRow(
                entity_type="todo", id=td.id, ticket=ticket,
                title=td.title, field="milestone_date",
                old_value=td.milestone_date, new_value=new, flag=flag,
            ))
        mode = "business days" if business_days else "calendar days"
        summary = f"Shift {len(rows)} todo milestone(s) by {delta_days:+d} {mode}."
        return ShiftPlan(
            rows=tuple(rows),
            summary=summary,
            params={
                "mode": "todos",
                "delta_days": delta_days,
                "business_days": business_days,
                "todo_ids": list(todo_ids),
            },
        )

    # ------------------------------------------------------------------
    # Apply / undo
    # ------------------------------------------------------------------

    def apply_shift(self, plan: ShiftPlan) -> ShiftResult:
        """Apply ``plan`` atomically and return a :class:`ShiftResult`.

        Rows whose ``old_value`` no longer matches the current database
        value (e.g. someone else edited the task in another session
        between preview and apply) are silently skipped. The returned
        ``result.rows`` only lists what was actually written, which is
        also what the inverse plan undoes.
        """
        shift_id = uuid.uuid4().hex[:12]
        applied_rows: list[ShiftPlanRow] = []
        inverse_rows: list[ShiftPlanRow] = []
        touched_task_ids: set[int] = set()

        for row in plan.rows:
            if row.flag == "no-op":
                continue
            if row.old_value == row.new_value:
                continue

            if row.entity_type == "task":
                task = self.session.get(Task, row.id)
                if task is None or task.due_date != row.old_value:
                    continue
                _log_change(
                    self.session, task.id,
                    "due_date", task.due_date, row.new_value,
                )
                task.due_date = row.new_value
                touched_task_ids.add(task.id)
                applied_rows.append(row)
                inverse_rows.append(ShiftPlanRow(
                    entity_type="task", id=task.id, ticket=row.ticket, title=row.title,
                    field="due_date", old_value=row.new_value, new_value=row.old_value,
                    flag=None,
                ))
            else:  # todo
                td = self.session.get(TodoItem, row.id)
                if td is None or td.milestone_date != row.old_value:
                    continue
                td.milestone_date = row.new_value
                touched_task_ids.add(td.task_id)
                applied_rows.append(row)
                inverse_rows.append(ShiftPlanRow(
                    entity_type="todo", id=td.id, ticket=row.ticket, title=row.title,
                    field="milestone_date", old_value=row.new_value,
                    new_value=row.old_value, flag=None,
                ))

        # One bulk_shift audit entry per affected task so the Activity
        # tab tells a coherent story ("bulk shift applied: <id>").
        for tid in sorted(touched_task_ids):
            _log_change(self.session, tid, "bulk_shift", None, shift_id)

        for tid in touched_task_ids:
            task = self.session.get(Task, tid)
            if task is not None:
                refresh_next_milestone(self.session, task)

        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        inverse_plan = ShiftPlan(
            rows=tuple(inverse_rows),
            summary=f"Undo bulk shift {shift_id} ({len(inverse_rows)} row(s))",
            params={"mode": "undo", "shift_id": shift_id},
        )
        return ShiftResult(
            shift_id=shift_id,
            applied_at=dt.datetime.now(dt.UTC),
            rows=tuple(applied_rows),
            inverse=inverse_plan,
        )

    def undo_shift(self, result: ShiftResult) -> ShiftResult:
        """Apply the inverse plan from ``result`` and return its own result.

        Does not cross-check the returned inverse against the original
        because :meth:`apply_shift` already skips out-of-band rows.
        """
        return self.apply_shift(result.inverse)
