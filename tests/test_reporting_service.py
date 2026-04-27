from __future__ import annotations

import datetime as dt

from tasktracker.domain.enums import TaskStatus
from tasktracker.services.reporting_service import (
    UNASSIGNED_LABEL,
    UNCATEGORIZED_LABEL,
    ReportingService,
)
from tasktracker.services.task_service import TaskService


# Reference "today" used by all reports below so the tests stay deterministic.
AS_OF = dt.date(2026, 6, 30)


def _seed_taxonomy(svc: TaskService) -> tuple[int, int]:
    """Return (network_area_id, printer_area_id) under category 'Infra'."""
    cat = svc.add_category("Infra")
    assert cat is not None
    sub = svc.add_subcategory(cat.id, "Networking")
    assert sub is not None
    net_area = svc.add_area(sub.id, "Switches")
    assert net_area is not None
    sub2 = svc.add_subcategory(cat.id, "Print")
    assert sub2 is not None
    pr_area = svc.add_area(sub2.id, "MFPs")
    assert pr_area is not None
    return net_area.id, pr_area.id


def _seed_people(svc: TaskService) -> tuple[int, int]:
    a = svc.add_person("Ada", "Lovelace", "E001")
    b = svc.add_person("Grace", "Hopper", "E002")
    assert a is not None and b is not None
    return a.id, b.id


# ----- 1. WIP & aging --------------------------------------------------------


def test_wip_aging_buckets_by_age(svc: TaskService) -> None:
    svc.create_task(title="fresh", received_date=AS_OF - dt.timedelta(days=2))
    svc.create_task(title="middle", received_date=AS_OF - dt.timedelta(days=20))
    svc.create_task(title="older", received_date=AS_OF - dt.timedelta(days=60))
    svc.create_task(title="ancient", received_date=AS_OF - dt.timedelta(days=200))
    closed = svc.create_task(title="closed-ignored", received_date=AS_OF - dt.timedelta(days=10))
    svc.close_task(closed.id, closed_on=AS_OF, resolution="Done")

    res = ReportingService(svc.session).wip_aging(as_of=AS_OF)
    assert res.meta["total_open"] == 4
    assert res.meta["buckets"] == {"0-7": 1, "8-30": 1, "31-90": 1, "90+": 1}
    all_lines = [r for r in res.rows if r["status"] == "All"]
    assert len(all_lines) == 4


def test_wip_aging_empty_db_returns_zero_buckets(svc: TaskService) -> None:
    res = ReportingService(svc.session).wip_aging(as_of=AS_OF)
    assert res.meta["total_open"] == 0
    none_rows = [r for r in res.rows if r["status"] == "(none)"]
    assert len(none_rows) == 4


# ----- 2. Throughput ---------------------------------------------------------


def test_throughput_weekly_groups_by_iso_week(svc: TaskService) -> None:
    a = svc.create_task(title="a", received_date=dt.date(2026, 6, 1))
    b = svc.create_task(title="b", received_date=dt.date(2026, 6, 1))
    c = svc.create_task(title="c", received_date=dt.date(2026, 6, 1))
    # Two closed in week of Mon 2026-06-15, one in week of Mon 2026-06-22.
    svc.close_task(a.id, closed_on=dt.date(2026, 6, 16), resolution="Done")
    svc.close_task(b.id, closed_on=dt.date(2026, 6, 18), resolution="Done")
    svc.close_task(c.id, closed_on=dt.date(2026, 6, 23), resolution="Done")

    res = ReportingService(svc.session).throughput(
        from_date=dt.date(2026, 6, 1),
        to_date=dt.date(2026, 6, 30),
        period="week",
    )
    by_period = {r["period_start"]: r["count"] for r in res.rows}
    assert by_period == {"2026-06-15": 2, "2026-06-22": 1}
    assert res.meta["total_closed"] == 3


def test_throughput_group_by_person_legacy_alias(svc: TaskService) -> None:
    """Saved ui_settings.json files written before the for-person rename
    still contain group_by='person'; the service must accept that alias."""
    ada_id, _ = _seed_people(svc)
    a = svc.create_task(
        title="ada-closed",
        received_date=dt.date(2026, 6, 1),
        person_id=ada_id,
    )
    svc.close_task(a.id, closed_on=dt.date(2026, 6, 16), resolution="Done")
    res = ReportingService(svc.session).throughput(
        from_date=dt.date(2026, 6, 1),
        to_date=dt.date(2026, 6, 30),
        period="week",
        group_by="person",
    )
    assert res.rows
    assert any(r.get("group") == "Lovelace, Ada" for r in res.rows)


def test_throughput_excludes_tasks_outside_window(svc: TaskService) -> None:
    a = svc.create_task(title="early", received_date=dt.date(2026, 5, 1))
    svc.close_task(a.id, closed_on=dt.date(2026, 5, 15), resolution="Done")
    res = ReportingService(svc.session).throughput(
        from_date=dt.date(2026, 6, 1),
        to_date=dt.date(2026, 6, 30),
        period="month",
    )
    assert res.rows == []
    assert res.meta["total_closed"] == 0


# ----- 3. Workload -----------------------------------------------------------


def test_workload_per_person_with_unassigned_bucket(svc: TaskService) -> None:
    ada_id, _grace_id = _seed_people(svc)
    svc.create_task(
        title="open ada 1",
        received_date=AS_OF - dt.timedelta(days=10),
        person_id=ada_id,
        impact=1,
        urgency=1,
    )
    svc.create_task(
        title="open ada overdue",
        received_date=AS_OF - dt.timedelta(days=20),
        due_date=AS_OF - dt.timedelta(days=2),
        person_id=ada_id,
    )
    svc.create_task(
        title="unassigned",
        received_date=AS_OF - dt.timedelta(days=5),
    )

    res = ReportingService(svc.session).workload(as_of=AS_OF)
    by_person = {r["for_person"]: r for r in res.rows}
    assert "for_person" in res.columns
    assert UNASSIGNED_LABEL in by_person
    assert "Lovelace, Ada" in by_person
    ada_row = by_person["Lovelace, Ada"]
    assert ada_row["open_count"] == 2
    assert ada_row["overdue_count"] == 1
    assert ada_row["p1_count"] == 1
    assert by_person[UNASSIGNED_LABEL]["open_count"] == 1


def test_workload_ignores_closed_tasks(svc: TaskService) -> None:
    t = svc.create_task(title="will close", received_date=AS_OF - dt.timedelta(days=3))
    svc.close_task(t.id, closed_on=AS_OF, resolution="Done")
    res = ReportingService(svc.session).workload(as_of=AS_OF)
    assert res.meta["total_open"] == 0
    assert res.rows == []


# ----- 4. SLA ----------------------------------------------------------------


def test_sla_counts_on_time_late_and_no_due(svc: TaskService) -> None:
    on_time = svc.create_task(
        title="ok", received_date=dt.date(2026, 6, 1), due_date=dt.date(2026, 6, 20)
    )
    late = svc.create_task(
        title="late", received_date=dt.date(2026, 6, 1), due_date=dt.date(2026, 6, 10)
    )
    no_due = svc.create_task(title="no-due", received_date=dt.date(2026, 6, 1))
    svc.close_task(on_time.id, closed_on=dt.date(2026, 6, 18), resolution="Done")
    svc.close_task(late.id, closed_on=dt.date(2026, 6, 14), resolution="Done")  # 4 days late
    svc.close_task(no_due.id, closed_on=dt.date(2026, 6, 15), resolution="Done")

    res = ReportingService(svc.session).sla(
        from_date=dt.date(2026, 6, 1), to_date=dt.date(2026, 6, 30)
    )
    assert res.meta["on_time"] == 1
    assert res.meta["late"] == 1
    assert res.meta["no_sla"] == 1
    assert res.meta["miss_rate_pct"] == 50.0
    assert res.meta["avg_days_late"] == 4.0


def test_sla_handles_only_no_due(svc: TaskService) -> None:
    """Edge case: nothing in the window had a due date set so miss-rate
    must not divide by zero."""
    t = svc.create_task(title="no due", received_date=dt.date(2026, 6, 1))
    svc.close_task(t.id, closed_on=dt.date(2026, 6, 5), resolution="Done")
    res = ReportingService(svc.session).sla(
        from_date=dt.date(2026, 6, 1), to_date=dt.date(2026, 6, 30)
    )
    assert res.meta["on_time"] == 0
    assert res.meta["late"] == 0
    assert res.meta["no_sla"] == 1
    assert res.meta["miss_rate_pct"] == 0.0


# ----- 5. Category mix ------------------------------------------------------


def test_category_mix_received_closed_and_open(svc: TaskService) -> None:
    net_area, _printer_area = _seed_taxonomy(svc)
    a = svc.create_task(
        title="net1", received_date=dt.date(2026, 6, 5), area_id=net_area
    )
    svc.create_task(
        title="net2-open", received_date=dt.date(2026, 6, 10), area_id=net_area
    )
    svc.close_task(a.id, closed_on=dt.date(2026, 6, 20), resolution="Done")

    res = ReportingService(svc.session).category_mix(
        from_date=dt.date(2026, 6, 1), to_date=dt.date(2026, 6, 30)
    )
    by_cat = {r["category"]: r for r in res.rows}
    assert by_cat["Infra"]["received_in_period"] == 2
    assert by_cat["Infra"]["closed_in_period"] == 1
    assert by_cat["Infra"]["net_change"] == 1
    assert by_cat["Infra"]["current_open"] == 1


def test_category_mix_uncategorized_bucket(svc: TaskService) -> None:
    svc.create_task(title="loose", received_date=dt.date(2026, 6, 5))
    res = ReportingService(svc.session).category_mix(
        from_date=dt.date(2026, 6, 1), to_date=dt.date(2026, 6, 30)
    )
    by_cat = {r["category"]: r for r in res.rows}
    assert UNCATEGORIZED_LABEL in by_cat
    assert by_cat[UNCATEGORIZED_LABEL]["received_in_period"] == 1


# ----- 6. Weekly status -----------------------------------------------------


def test_weekly_status_counts_match_window(svc: TaskService) -> None:
    closed_in_window = svc.create_task(
        title="cw", received_date=AS_OF - dt.timedelta(days=20)
    )
    svc.close_task(closed_in_window.id, closed_on=AS_OF - dt.timedelta(days=2), resolution="Done")

    closed_too_old = svc.create_task(
        title="old close", received_date=AS_OF - dt.timedelta(days=40)
    )
    svc.close_task(closed_too_old.id, closed_on=AS_OF - dt.timedelta(days=15), resolution="Done")

    svc.create_task(
        title="due soon",
        received_date=AS_OF - dt.timedelta(days=3),
        due_date=AS_OF + dt.timedelta(days=3),
    )
    svc.create_task(
        title="due far",
        received_date=AS_OF - dt.timedelta(days=3),
        due_date=AS_OF + dt.timedelta(days=30),
    )

    res = ReportingService(svc.session).weekly_status(as_of=AS_OF)
    assert res.meta["closed_last_7"] == 1
    assert res.meta["due_next_7"] == 1
    assert res.meta["open_total"] == 2


def test_weekly_status_blocked_count_uses_status(svc: TaskService) -> None:
    t = svc.create_task(title="blocker subject", received_date=AS_OF - dt.timedelta(days=4))
    svc.add_blocker(t.id, title="waiting on vendor")
    res = ReportingService(svc.session).weekly_status(as_of=AS_OF)
    assert res.meta["currently_blocked"] == 1
    assert res.meta["open_by_status"].get(TaskStatus.BLOCKED.value) == 1
