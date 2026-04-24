"""Read-only reporting service: aggregations and report shapes for the
Reports tab and rich workbook export.

Each public method returns a :class:`ReportResult`: ``columns`` for table /
sheet headers in display order, ``rows`` as plain dicts (so CSV / xlsx /
QTableWidget consumers don't need to know about the report shape), and
``meta`` carrying the input parameters plus computed totals. ``summary``
is a short multi-line string suitable for the Reports tab "Copy summary
to clipboard" button.

All numeric ages here are calendar days, not business days, to match the
intuition of pivoting in Excel against ``received_date`` / ``closed_date``
and to avoid pulling business-day math into report calculations. The
existing close-date math in :mod:`tasktracker.services.task_service`
remains business-day aware where it counts (recurrence successor
scheduling).
"""

# Status semantics (see ``tech_decisions.md`` / user guide **Tasks → Statuses**):
# - ``open`` = captured / intake; not actively in flight.
# - ``in_progress`` = actively being worked.
# Both sit in ``_OPEN_STATUSES`` for combined WIP totals; crosstabs and
# ``open_by_status``-style summaries keep them as distinct keys.

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tasktracker.db.models import (
    Task,
    TaskArea,
    TaskSubCategory,
)
from tasktracker.domain.enums import TaskStatus
from tasktracker.domain.priority import priority_display
from tasktracker.domain.ticket import format_task_ticket


# Status sets used across reports.
_OPEN_STATUSES: frozenset[str] = frozenset(
    {
        TaskStatus.OPEN.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.ON_HOLD.value,
    }
)
_CLOSED_STATUSES: frozenset[str] = frozenset(
    {TaskStatus.CLOSED.value, TaskStatus.CANCELLED.value}
)

AGE_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("0-7", 0, 7),
    ("8-30", 8, 30),
    ("31-90", 31, 90),
    ("90+", 91, None),
)

UNASSIGNED_LABEL = "(unassigned)"
UNCATEGORIZED_LABEL = "(uncategorized)"


@dataclass
class ReportResult:
    """Generic report payload consumed by the UI table, CSV writer, and
    rich-workbook builder. ``rows`` are dicts keyed by ``columns``."""

    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    meta: dict[str, Any] = field(default_factory=dict)
    summary: str = ""


def _age_days(received: dt.date, as_of: dt.date) -> int:
    return max(0, (as_of - received).days)


def _bucket_for(age: int) -> str:
    for label, lo, hi in AGE_BUCKETS:
        if hi is None:
            if age >= lo:
                return label
        elif lo <= age <= hi:
            return label
    return AGE_BUCKETS[-1][0]


def _person_label(task: Task) -> str:
    if task.person is None:
        return UNASSIGNED_LABEL
    return f"{task.person.last_name}, {task.person.first_name}"


def _category_label(task: Task) -> str:
    area = task.area
    sub = area.subcategory if area else None
    cat = sub.category if sub else None
    if cat is None:
        return UNCATEGORIZED_LABEL
    return cat.name


class ReportingService:
    """Reporting facade. Construct with the same SQLAlchemy ``Session`` used
    elsewhere in the request; the service does not commit and does not mutate
    rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ----- internal helpers -------------------------------------------------

    def _all_tasks(self) -> list[Task]:
        """Tasks with the relationships every report tends to read.

        Eager-loads area/subcategory/category and person; reports that need
        todos / blockers reload as needed (they are rare paths).
        """
        q = select(Task).options(
            selectinload(Task.area)
            .selectinload(TaskArea.subcategory)
            .selectinload(TaskSubCategory.category),
            selectinload(Task.person),
            selectinload(Task.blockers),
        )
        return list(self.session.scalars(q).unique().all())

    # ----- 1. WIP & aging ---------------------------------------------------

    def wip_aging(self, as_of: dt.date | None = None) -> ReportResult:
        """Open tasks bucketed by age in calendar days. One row per
        (bucket, status, priority) combination present, plus an "All" line
        per bucket. ``ticket_numbers`` is a comma-separated list so the
        Excel / CSV consumer can drill in without exploding to per-task rows.
        """
        as_of = as_of or dt.date.today()
        tasks = [t for t in self._all_tasks() if t.status in _OPEN_STATUSES]
        rows: list[dict[str, Any]] = []
        per_bucket: Counter[str] = Counter()
        per_bucket_status: dict[str, Counter[str]] = defaultdict(Counter)
        per_bucket_priority: dict[str, Counter[int]] = defaultdict(Counter)
        bucket_tickets: dict[str, list[str]] = defaultdict(list)

        for t in tasks:
            age = _age_days(t.received_date, as_of)
            b = _bucket_for(age)
            per_bucket[b] += 1
            per_bucket_status[b][t.status] += 1
            per_bucket_priority[b][t.priority] += 1
            bucket_tickets[b].append(format_task_ticket(t.ticket_number))

        for label, _lo, _hi in AGE_BUCKETS:
            if per_bucket[label] == 0:
                rows.append(
                    {
                        "bucket": label,
                        "status": "(none)",
                        "priority": "",
                        "count": 0,
                        "ticket_numbers": "",
                    }
                )
                continue
            for status, count in sorted(per_bucket_status[label].items()):
                rows.append(
                    {
                        "bucket": label,
                        "status": status,
                        "priority": "",
                        "count": count,
                        "ticket_numbers": "",
                    }
                )
            for priority, count in sorted(per_bucket_priority[label].items()):
                rows.append(
                    {
                        "bucket": label,
                        "status": "",
                        "priority": priority_display(priority),
                        "count": count,
                        "ticket_numbers": "",
                    }
                )
            rows.append(
                {
                    "bucket": label,
                    "status": "All",
                    "priority": "All",
                    "count": per_bucket[label],
                    "ticket_numbers": ", ".join(sorted(bucket_tickets[label])),
                }
            )

        total_open = sum(per_bucket.values())
        meta = {
            "as_of": as_of.isoformat(),
            "total_open": total_open,
            "buckets": {label: per_bucket[label] for label, _, _ in AGE_BUCKETS},
        }
        summary_lines = [f"WIP & aging as of {as_of.isoformat()}: {total_open} open"]
        for label, _, _ in AGE_BUCKETS:
            summary_lines.append(f"  {label} days: {per_bucket[label]}")
        return ReportResult(
            name="WIP & aging",
            columns=["bucket", "status", "priority", "count", "ticket_numbers"],
            rows=rows,
            meta=meta,
            summary="\n".join(summary_lines),
        )

    # ----- 2. Throughput / closure velocity --------------------------------

    def throughput(
        self,
        from_date: dt.date,
        to_date: dt.date,
        *,
        period: str = "week",
        group_by: str = "none",
    ) -> ReportResult:
        """Closed task counts over time.

        ``period`` is ``"week"`` (ISO week start: Monday) or ``"month"``.
        ``group_by`` adds a column split: ``"none"``, ``"category"``,
        ``"for_person"``. Tasks without a ``closed_date`` in the range are
        ignored. Cancelled tasks are included alongside fully closed ones
        because both are "off the WIP", and excluding them would understate
        throughput.

        ``group_by="person"`` is accepted as a back-compat alias for the
        canonical ``"for_person"`` so that ``ui_settings.json`` files saved
        before the rename keep loading without manual editing.
        """
        if period not in ("week", "month"):
            raise ValueError("period must be 'week' or 'month'")
        if group_by == "person":  # legacy alias - keep for saved settings
            group_by = "for_person"
        if group_by not in ("none", "category", "for_person"):
            raise ValueError("group_by must be 'none', 'category', or 'for_person'")
        tasks = [
            t
            for t in self._all_tasks()
            if t.status in _CLOSED_STATUSES
            and t.closed_date is not None
            and from_date <= t.closed_date <= to_date
        ]

        def period_key(d: dt.date) -> dt.date:
            if period == "week":
                return d - dt.timedelta(days=d.weekday())  # Monday of that week
            return d.replace(day=1)

        def group_key(t: Task) -> str:
            if group_by == "category":
                return _category_label(t)
            if group_by == "for_person":
                return _person_label(t)
            return ""

        cell: dict[tuple[dt.date, str], int] = defaultdict(int)
        for t in tasks:
            assert t.closed_date is not None
            cell[(period_key(t.closed_date), group_key(t))] += 1

        rows: list[dict[str, Any]] = []
        for (pstart, gk), count in sorted(cell.items()):
            row: dict[str, Any] = {
                "period_start": pstart.isoformat(),
                "count": count,
            }
            if group_by != "none":
                row["group"] = gk
            rows.append(row)

        columns = ["period_start"]
        if group_by != "none":
            columns.append("group")
        columns.append("count")

        meta = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "period": period,
            "group_by": group_by,
            "total_closed": len(tasks),
            "periods_covered": len({k[0] for k in cell}),
        }
        summary = (
            f"Throughput {from_date.isoformat()} -> {to_date.isoformat()} "
            f"({period}, group_by={group_by}): {len(tasks)} closed across "
            f"{meta['periods_covered']} period(s)"
        )
        return ReportResult(
            name="Throughput",
            columns=columns,
            rows=rows,
            meta=meta,
            summary=summary,
        )

    # ----- 3. Workload by person -------------------------------------------

    def workload(self, *, as_of: dt.date | None = None) -> ReportResult:
        """Per for-person open workload. Includes a synthetic
        "(unassigned)" row so tasks with no for-person attribution are
        visible rather than silently dropped. The column key is
        ``for_person`` to match the form label on the task panel and the
        existing ``for_person`` / ``for_person_employee_id`` columns on the
        flat Tasks export."""
        as_of = as_of or dt.date.today()
        tasks = [t for t in self._all_tasks() if t.status in _OPEN_STATUSES]

        groups: dict[str, list[Task]] = defaultdict(list)
        for t in tasks:
            groups[_person_label(t)].append(t)

        rows: list[dict[str, Any]] = []
        for person, items in sorted(groups.items()):
            ages = [_age_days(t.received_date, as_of) for t in items]
            overdue = [t for t in items if t.due_date and t.due_date < as_of]
            p1 = sum(1 for t in items if t.priority == 1)
            p2 = sum(1 for t in items if t.priority == 2)
            oldest = min((t.received_date for t in items), default=None)
            avg_age = round(sum(ages) / len(ages), 1) if ages else 0.0
            rows.append(
                {
                    "for_person": person,
                    "open_count": len(items),
                    "overdue_count": len(overdue),
                    "p1_count": p1,
                    "p2_count": p2,
                    "oldest_received": oldest.isoformat() if oldest else "",
                    "avg_age_days": avg_age,
                }
            )

        total_open = sum(r["open_count"] for r in rows)
        total_overdue = sum(r["overdue_count"] for r in rows)
        meta = {
            "as_of": as_of.isoformat(),
            "people": len(rows),
            "total_open": total_open,
            "total_overdue": total_overdue,
        }
        summary = (
            f"Workload as of {as_of.isoformat()}: {total_open} open across "
            f"{len(rows)} for-person bucket(s); {total_overdue} overdue"
        )
        return ReportResult(
            name="Workload",
            columns=[
                "for_person",
                "open_count",
                "overdue_count",
                "p1_count",
                "p2_count",
                "oldest_received",
                "avg_age_days",
            ],
            rows=rows,
            meta=meta,
            summary=summary,
        )

    # ----- 4. SLA / due-date performance -----------------------------------

    def sla(self, from_date: dt.date, to_date: dt.date) -> ReportResult:
        """For tasks closed in the window: how many hit the due date and
        how late the misses were. Tasks closed without a ``due_date`` are
        counted as ``no_sla`` and excluded from miss-rate math (you can't
        miss a target that wasn't set)."""
        tasks = [
            t
            for t in self._all_tasks()
            if t.status in _CLOSED_STATUSES
            and t.closed_date is not None
            and from_date <= t.closed_date <= to_date
        ]
        per_cat_on: Counter[str] = Counter()
        per_cat_late: Counter[str] = Counter()
        per_cat_late_days: dict[str, list[int]] = defaultdict(list)
        per_cat_no_sla: Counter[str] = Counter()

        for t in tasks:
            cat = _category_label(t)
            if t.due_date is None:
                per_cat_no_sla[cat] += 1
                continue
            assert t.closed_date is not None
            days_late = (t.closed_date - t.due_date).days
            if days_late <= 0:
                per_cat_on[cat] += 1
            else:
                per_cat_late[cat] += 1
                per_cat_late_days[cat].append(days_late)

        rows: list[dict[str, Any]] = []
        all_cats = sorted(set(per_cat_on) | set(per_cat_late) | set(per_cat_no_sla))
        for cat in all_cats:
            on_time = per_cat_on[cat]
            late = per_cat_late[cat]
            no_sla = per_cat_no_sla[cat]
            graded = on_time + late
            miss_rate = round((late / graded) * 100, 1) if graded else 0.0
            avg_late = (
                round(sum(per_cat_late_days[cat]) / len(per_cat_late_days[cat]), 1)
                if per_cat_late_days[cat]
                else 0.0
            )
            rows.append(
                {
                    "category": cat,
                    "on_time": on_time,
                    "late": late,
                    "no_sla": no_sla,
                    "miss_rate_pct": miss_rate,
                    "avg_days_late": avg_late,
                }
            )

        total_on = sum(per_cat_on.values())
        total_late = sum(per_cat_late.values())
        total_no_sla = sum(per_cat_no_sla.values())
        graded_total = total_on + total_late
        overall_miss = round((total_late / graded_total) * 100, 1) if graded_total else 0.0
        all_late_days = [d for ds in per_cat_late_days.values() for d in ds]
        overall_avg_late = (
            round(sum(all_late_days) / len(all_late_days), 1) if all_late_days else 0.0
        )

        meta = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "on_time": total_on,
            "late": total_late,
            "no_sla": total_no_sla,
            "miss_rate_pct": overall_miss,
            "avg_days_late": overall_avg_late,
        }
        summary = (
            f"SLA {from_date.isoformat()} -> {to_date.isoformat()}: "
            f"{total_on} on time, {total_late} late ({overall_miss}% miss), "
            f"avg {overall_avg_late} days late; {total_no_sla} closed with no due date set"
        )
        return ReportResult(
            name="SLA performance",
            columns=[
                "category",
                "on_time",
                "late",
                "no_sla",
                "miss_rate_pct",
                "avg_days_late",
            ],
            rows=rows,
            meta=meta,
            summary=summary,
        )

    # ----- 5. Category mix / backlog growth --------------------------------

    def category_mix(self, from_date: dt.date, to_date: dt.date) -> ReportResult:
        """Per category: ``received_in_period`` (received_date in window),
        ``closed_in_period`` (closed_date in window), ``net_change`` (the
        delta - positive means backlog grew), and ``current_open`` for
        cross-reference. Useful for showing which workstreams are growing
        vs. being burned down."""
        all_tasks = self._all_tasks()
        per_cat_recv: Counter[str] = Counter()
        per_cat_closed: Counter[str] = Counter()
        per_cat_open: Counter[str] = Counter()
        for t in all_tasks:
            cat = _category_label(t)
            if from_date <= t.received_date <= to_date:
                per_cat_recv[cat] += 1
            if (
                t.closed_date is not None
                and from_date <= t.closed_date <= to_date
            ):
                per_cat_closed[cat] += 1
            if t.status in _OPEN_STATUSES:
                per_cat_open[cat] += 1

        rows: list[dict[str, Any]] = []
        for cat in sorted(set(per_cat_recv) | set(per_cat_closed) | set(per_cat_open)):
            recv = per_cat_recv[cat]
            closed = per_cat_closed[cat]
            rows.append(
                {
                    "category": cat,
                    "received_in_period": recv,
                    "closed_in_period": closed,
                    "net_change": recv - closed,
                    "current_open": per_cat_open[cat],
                }
            )

        meta = {
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "categories": len(rows),
            "total_received": sum(per_cat_recv.values()),
            "total_closed": sum(per_cat_closed.values()),
            "total_open": sum(per_cat_open.values()),
        }
        summary = (
            f"Category mix {from_date.isoformat()} -> {to_date.isoformat()}: "
            f"{meta['total_received']} received, {meta['total_closed']} closed, "
            f"net {meta['total_received'] - meta['total_closed']:+d}; "
            f"{meta['total_open']} currently open"
        )
        return ReportResult(
            name="Category mix",
            columns=[
                "category",
                "received_in_period",
                "closed_in_period",
                "net_change",
                "current_open",
            ],
            rows=rows,
            meta=meta,
            summary=summary,
        )

    # ----- 6. Weekly status readout ----------------------------------------

    def weekly_status(self, *, as_of: dt.date | None = None) -> ReportResult:
        """Composite report intended for an emailable weekly readout.

        Rows here are heterogenous (one row per "section" rather than one
        row per task) so the table reads top-to-bottom like a status report
        rather than a pivot. The ``meta`` dict carries the underlying
        counts for the workbook Summary sheet to pull from.
        """
        as_of = as_of or dt.date.today()
        last_week_start = as_of - dt.timedelta(days=7)
        next_week_end = as_of + dt.timedelta(days=7)
        tasks = self._all_tasks()

        closed_last_7 = [
            t
            for t in tasks
            if t.status in _CLOSED_STATUSES
            and t.closed_date is not None
            and last_week_start <= t.closed_date <= as_of
        ]
        open_tasks = [t for t in tasks if t.status in _OPEN_STATUSES]
        open_by_status: Counter[str] = Counter(t.status for t in open_tasks)
        due_next_7 = [
            t
            for t in open_tasks
            if t.due_date is not None and as_of <= t.due_date <= next_week_end
        ]
        currently_blocked = [
            t for t in open_tasks if t.status == TaskStatus.BLOCKED.value
        ]
        top_priority_open = sorted(
            open_tasks,
            key=lambda x: (x.priority, x.due_date or dt.date.max, x.id),
        )[:5]

        def task_line(t: Task) -> str:
            tk = format_task_ticket(t.ticket_number)
            due = t.due_date.isoformat() if t.due_date else "no due"
            return f"{tk} {t.title} (P{t.priority}, due {due})"

        rows: list[dict[str, Any]] = []
        rows.append(
            {
                "section": f"Closed in last 7 days ({len(closed_last_7)})",
                "detail": ", ".join(format_task_ticket(t.ticket_number) for t in closed_last_7)
                or "(none)",
            }
        )
        rows.append(
            {
                "section": f"Open ({len(open_tasks)}) - by status",
                "detail": ", ".join(f"{s}: {c}" for s, c in sorted(open_by_status.items()))
                or "(none open)",
            }
        )
        rows.append(
            {
                "section": f"Due in next 7 days ({len(due_next_7)})",
                "detail": " | ".join(task_line(t) for t in due_next_7) or "(none)",
            }
        )
        rows.append(
            {
                "section": f"Currently blocked ({len(currently_blocked)})",
                "detail": " | ".join(task_line(t) for t in currently_blocked) or "(none)",
            }
        )
        rows.append(
            {
                "section": f"Top priority open (showing {len(top_priority_open)})",
                "detail": " | ".join(task_line(t) for t in top_priority_open) or "(none)",
            }
        )

        meta = {
            "as_of": as_of.isoformat(),
            "closed_last_7": len(closed_last_7),
            "open_total": len(open_tasks),
            "open_by_status": dict(open_by_status),
            "due_next_7": len(due_next_7),
            "currently_blocked": len(currently_blocked),
        }
        summary_lines = [
            f"Weekly status as of {as_of.isoformat()}",
            f"  Closed last 7 days: {len(closed_last_7)}",
            f"  Open total: {len(open_tasks)}",
            f"  Due next 7 days: {len(due_next_7)}",
            f"  Currently blocked: {len(currently_blocked)}",
        ]
        return ReportResult(
            name="Weekly status",
            columns=["section", "detail"],
            rows=rows,
            meta=meta,
            summary="\n".join(summary_lines),
        )
