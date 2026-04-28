"""SQLite additive migrations after create_all (no Alembic required for local MVP)."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from tasktracker.db.models import Task
from tasktracker.services.task_service import sync_all_task_search_fts_if_stale


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
        if "resolution" not in col_names:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN resolution TEXT"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_ticket_number_unique "
                "ON tasks(ticket_number)"
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_area_id ON tasks(area_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_person_id ON tasks(person_id)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    title_pattern VARCHAR(500) NOT NULL,
                    description_pattern TEXT,
                    default_area_id INTEGER REFERENCES task_areas(id) ON DELETE SET NULL,
                    default_person_id INTEGER REFERENCES task_people(id) ON DELETE SET NULL,
                    default_impact INTEGER NOT NULL DEFAULT 2,
                    default_urgency INTEGER NOT NULL DEFAULT 2,
                    default_status VARCHAR(32) NOT NULL DEFAULT 'open',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_template_todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL REFERENCES task_templates(id) ON DELETE CASCADE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    title VARCHAR(500) NOT NULL,
                    milestone_offset_days INTEGER
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_task_templates_sort ON task_templates(sort_order)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_task_template_todos_template_id "
                "ON task_template_todos(template_id)"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    display_name VARCHAR(500) NOT NULL,
                    storage_relpath VARCHAR(1024) NOT NULL,
                    content_sha256 VARCHAR(64) NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mime_hint VARCHAR(200),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_task_attachments_task_id ON task_attachments(task_id)")
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(120) NOT NULL UNIQUE,
                    slug VARCHAR(140) NOT NULL UNIQUE,
                    color_hint VARCHAR(32),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_tags_name ON tags(name)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_tags_slug ON tags(slug)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_tags (
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY (task_id, tag_id)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_task_tags_task_id ON task_tags(task_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_task_tags_tag_id ON task_tags(tag_id)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    blocker_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    blocked_task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    note TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_task_dependencies_pair UNIQUE (blocker_task_id, blocked_task_id)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_task_dependencies_blocker_task_id "
                "ON task_dependencies(blocker_task_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_task_dependencies_blocked_task_id "
                "ON task_dependencies(blocked_task_id)"
            )
        )
        todo_rows = conn.execute(text("PRAGMA table_info(todo_items)")).fetchall()
        todo_col_names = {r[1] for r in todo_rows}
        if "resolution" not in todo_col_names:
            conn.execute(text("ALTER TABLE todo_items ADD COLUMN resolution TEXT"))

    Session = sessionmaker(bind=engine, expire_on_commit=True, future=True)
    with Session() as session:
        missing = session.scalars(
            select(Task).where(Task.ticket_number.is_(None)).order_by(Task.id)
        ).all()
        if missing:
            m = session.scalar(select(func.max(Task.ticket_number)))
            n = (m + 1) if m is not None else 0
            for t in missing:
                t.ticket_number = n
                n += 1
            session.commit()

    with engine.begin() as conn:
        fts_row = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_search_fts' LIMIT 1"
            )
        ).fetchone()
        if not fts_row:
            conn.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE task_search_fts USING fts5(
                        task_id UNINDEXED,
                        title,
                        description,
                        notes,
                        tokenize = 'porter unicode61 remove_diacritics 2'
                    )
                    """
                )
            )

    with Session() as session:
        sync_all_task_search_fts_if_stale(session)
        session.commit()
