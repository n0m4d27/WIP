"""SQLite additive migrations after create_all (no Alembic required for local MVP)."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from tasktracker.db.models import Task


def upgrade_schema(engine: Engine) -> None:
    """Add missing columns and backfill. Safe to call on every startup."""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
        col_names = {r[1] for r in rows}
        if "ticket_number" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN ticket_number INTEGER"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_ticket_number_unique "
                "ON tasks(ticket_number)"
            )
        )

    Session = sessionmaker(bind=engine, expire_on_commit=True, future=True)
    with Session() as session:
        missing = session.scalars(
            select(Task).where(Task.ticket_number.is_(None)).order_by(Task.id)
        ).all()
        if not missing:
            return
        m = session.scalar(select(func.max(Task.ticket_number)))
        n = (m + 1) if m is not None else 0
        for t in missing:
            t.ticket_number = n
            n += 1
        session.commit()
