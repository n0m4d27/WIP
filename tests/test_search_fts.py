from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from tasktracker.db.models import Base
from tasktracker.db.schema_upgrade import upgrade_schema
from tasktracker.services.task_service import TaskService


def _session_with_fts() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    upgrade_schema(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=True, future=True)
    return SessionLocal()


def test_fts_row_count_matches_task_count() -> None:
    s = _session_with_fts()
    svc = TaskService(s)
    svc.create_task(title="A", received_date=dt.date(2026, 1, 1))
    svc.create_task(title="B", received_date=dt.date(2026, 1, 2))
    n_tasks = s.scalar(text("SELECT count(*) FROM tasks"))
    n_fts = s.scalar(text("SELECT count(*) FROM task_search_fts"))
    assert int(n_tasks or 0) == int(n_fts or 0) == 2


def test_search_finds_term_only_in_note_plaintext() -> None:
    s = _session_with_fts()
    svc = TaskService(s)
    t = svc.create_task(title="No keyword in title", received_date=dt.date(2026, 1, 1))
    svc.add_note(t.id, body_html="<p>The <b>stakeholder</b> said quorum</p>")
    hits = svc.search_tasks("quorum", fields={"notes"})
    assert len(hits) == 1
    assert hits[0].task.id == t.id


def test_fts_snippet_populated_for_notes_hit() -> None:
    s = _session_with_fts()
    svc = TaskService(s)
    t = svc.create_task(title="X", received_date=dt.date(2026, 1, 1))
    svc.add_note(t.id, body_html="<p>alpha bravo charlie</p>")
    hits = svc.search_tasks("bravo", fields={"notes"})
    assert len(hits) == 1
    assert hits[0].snippet is not None
    assert "bravo" in hits[0].snippet.lower()


def test_single_char_query_falls_back_to_like_on_notes() -> None:
    s = _session_with_fts()
    svc = TaskService(s)
    t = svc.create_task(title="Y", received_date=dt.date(2026, 1, 1))
    svc.add_note(t.id, body_html="<p>x</p>")
    hits = svc.search_tasks("x", fields={"notes"})
    assert len(hits) == 1
    assert hits[0].task.id == t.id


def test_note_edit_updates_fts() -> None:
    s = _session_with_fts()
    svc = TaskService(s)
    t = svc.create_task(title="Z", received_date=dt.date(2026, 1, 1))
    note = svc.add_note(t.id, body_html="<p>oldterm</p>")
    assert note is not None
    assert not svc.search_tasks("newterm", fields={"notes"})
    svc.update_note_body(note.id, "<p>newterm here</p>")
    hits = svc.search_tasks("newterm", fields={"notes"})
    assert len(hits) == 1
    assert not svc.search_tasks("oldterm", fields={"notes"})


def test_delete_task_removes_fts_row() -> None:
    from tasktracker.db.models import Task

    s = _session_with_fts()
    svc = TaskService(s)
    t = svc.create_task(title="Delete me", received_date=dt.date(2026, 1, 1))
    tid = t.id
    n = s.execute(
        text("SELECT count(*) FROM task_search_fts WHERE rowid = :i"), {"i": tid}
    ).scalar()
    assert int(n or 0) == 1
    assert svc.delete_task(tid) is True
    assert s.get(Task, tid) is None
    n2 = s.execute(
        text("SELECT count(*) FROM task_search_fts WHERE rowid = :i"), {"i": tid}
    ).scalar()
    assert int(n2 or 0) == 0


def test_upgrade_schema_idempotent_row_counts() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    upgrade_schema(engine)
    upgrade_schema(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as s:
        svc = TaskService(s)
        svc.create_task(title="Only", received_date=dt.date(2026, 1, 1))
    upgrade_schema(engine)
    with SessionLocal() as s:
        n_t = int(s.scalar(text("SELECT count(*) FROM tasks")) or 0)
        n_f = int(s.scalar(text("SELECT count(*) FROM task_search_fts")) or 0)
        assert n_t == n_f == 1
