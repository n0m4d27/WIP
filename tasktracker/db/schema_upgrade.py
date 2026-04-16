"""SQLite additive migrations after create_all (no Alembic required for local MVP)."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from tasktracker.db.models import Task


def upgrade_schema(engine: Engine) -> None:
    """Add missing columns and backfill. Safe to call on every startup."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200) NOT NULL UNIQUE
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_subcategories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    FOREIGN KEY(category_id) REFERENCES task_categories(id) ON DELETE CASCADE,
                    CONSTRAINT uq_task_subcategories_category_name UNIQUE (category_id, name)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_areas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subcategory_id INTEGER NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    FOREIGN KEY(subcategory_id) REFERENCES task_subcategories(id) ON DELETE CASCADE,
                    CONSTRAINT uq_task_areas_subcategory_name UNIQUE (subcategory_id, name)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name VARCHAR(120) NOT NULL,
                    last_name VARCHAR(120) NOT NULL,
                    employee_id VARCHAR(120) NOT NULL UNIQUE
                )
                """
            )
        )
        conn.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_task_categories_name ON task_categories(name)")
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_task_people_employee_id "
                "ON task_people(employee_id)"
            )
        )

        rows = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
        col_names = {r[1] for r in rows}
        if "ticket_number" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN ticket_number INTEGER"))
        if "area_id" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN area_id INTEGER"))
        if "person_id" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN person_id INTEGER"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_ticket_number_unique "
                "ON tasks(ticket_number)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_area_id ON tasks(area_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_person_id ON tasks(person_id)"))

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
