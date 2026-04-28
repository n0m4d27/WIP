from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import html
import json
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from sqlalchemy import Select, exists, func, or_, select, text
from sqlalchemy.orm import Session, joinedload, selectinload

from tasktracker.db.models import (
    BusinessHoliday,
    RecurringRule,
    RecurringTodoTemplate,
    TaskArea,
    TaskCategory,
    Task,
    TaskAttachment,
    TaskBlocker,
    TaskDependency,
    TaskNote,
    TaskNoteVersion,
    TaskPerson,
    TaskSubCategory,
    Tag,
    TaskTemplate,
    TaskTemplateTodo,
    TaskUpdateLog,
    TodoItem,
)
from tasktracker.paths import attachments_dir
from tasktracker.vault_attachments_crypto import purge_task_attachments_folder
from tasktracker.domain.enums import RecurrenceGenerationMode, TaskStatus
from tasktracker.domain.priority import compute_priority, priority_display


@dataclass(frozen=True)
class TaskSearchHit:
    task: Task
    snippet: str | None = None


@dataclass(frozen=True)
class TemplateApplySnapshot:
    """Expanded fields ready to populate the new-task form (plan 03)."""

    title: str
    description: str | None
    area_id: int | None
    person_id: int | None
    impact: int
    urgency: int
    status: str
    todos: tuple[tuple[str, int, dt.date | None], ...]


_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def expand_task_template_placeholders(pattern: str | None, anchor: dt.date) -> str | None:
    """Expand ``{today}``, ``{yyyy}``, ``{mm}``, ``{dd}``, ``{week}`` against ``anchor``."""
    if pattern is None:
        return None
    iso = anchor.isoformat()
    _y, week_no, _wd = anchor.isocalendar()
    repl = {
        "today": iso,
        "yyyy": f"{anchor.year:04d}",
        "mm": f"{anchor.month:02d}",
        "dd": f"{anchor.day:02d}",
        "week": str(week_no),
    }

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1).lower()
        return repl.get(key, m.group(0))

    return _TEMPLATE_PLACEHOLDER_RE.sub(_sub, pattern)


# Fields backed by the task_search_fts virtual table (plan 02).
_FTS_INDEXED_FIELDS: frozenset[str] = frozenset({"title", "description", "notes"})
_FTS_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)


def _fts_table_exists(session: Session) -> bool:
    return (
        session.scalar(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_search_fts' LIMIT 1"
            )
        )
        is not None
    )


def _fts_eligible(needle: str) -> bool:
    raw = needle.strip()
    if len(raw) < 2:
        return False
    tokens = [t.lower() for t in _FTS_TOKEN_RE.findall(raw)]
    if not tokens:
        return False

    def _ok(tok: str) -> bool:
        if len(tok) >= 2:
            return True
        return tok.isdigit() and len(tok) >= 2

    return all(_ok(t) for t in tokens)


def _fts_match_expression(fts_fields: set[str], raw: str) -> str:
    tokens = [t.lower() for t in _FTS_TOKEN_RE.findall(raw)]
    tokens = [t for t in tokens if len(t) >= 2 or (t.isdigit() and len(t) >= 2)]
    col_list = " ".join(sorted(fts_fields))

    def esc(tok: str) -> str:
        return '"' + tok.replace('"', '""') + '"'

    inner = " AND ".join(esc(t) for t in tokens)
    return f"{{ {col_list} }} : ({inner})"


# Stable ordering for Dashboard cards. UI and tests import this tuple
# instead of spelling the ids out in multiple places; adding a new card
# is a one-line change here plus its service branch.
DASHBOARD_CARD_IDS: tuple[str, ...] = (
    "overdue",
    "due_today",
    "due_this_week",
    "blocked",
    "top_priority",
)


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


def shift_business_days(
    start: dt.date,
    days: int,
    holidays: set[dt.date],
    *,
    skip_weekends: bool = True,
    skip_holidays: bool = True,
) -> dt.date:
    """Move ``start`` by ``days`` business days in either direction.

    Unlike :func:`add_business_days` (which is tailored for recurrence
    spawning and collapses ``days <= 0`` to "next business day on or
    after"), this helper is symmetric: positive deltas step into the
    future, negative deltas step into the past, and ``0`` returns
    ``start`` unchanged (no rounding). Intermediate weekend/holiday
    days are counted against the running tally in both directions so
    "shift by 5 business days" always skips exactly five work days.

    Kept here alongside :func:`add_business_days` so anything that
    needs business-day arithmetic (recurrence, bulk shifts, the
    calendar quick-edit dialog) pulls from one module.
    """
    if days == 0:
        return start
    step = dt.timedelta(days=1 if days > 0 else -1)
    remaining = abs(days)
    d = start
    while remaining > 0:
        d += step
        if _is_business_day(
            d, holidays, skip_weekends=skip_weekends, skip_holidays=skip_holidays
        ):
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


def _aggregate_notes_plain(session: Session, task_id: int) -> str:
    """Concatenate latest plain-text body for each note (ordered by note creation).

    Latest versions are loaded with per-note scalar queries so a just-flushed
    ``TaskNoteVersion`` row is visible even when a cached ``TaskNote.versions``
    collection in the identity map is stale.
    """
    note_ids = session.scalars(
        select(TaskNote.id).where(TaskNote.task_id == task_id).order_by(TaskNote.created_at)
    ).all()
    parts: list[str] = []
    for nid in note_ids:
        body = session.scalar(
            select(TaskNoteVersion.body_html)
            .where(TaskNoteVersion.note_id == nid)
            .order_by(TaskNoteVersion.version_seq.desc())
            .limit(1)
        )
        if body:
            plain = _to_plain_text(body)
            if plain:
                parts.append(plain)
    return " ".join(parts)


def sync_task_search_fts(session: Session, task_id: int) -> None:
    """Upsert or delete one FTS row for ``task_id``. No-op when the FTS table is absent."""
    if not _fts_table_exists(session):
        return
    conn = session.connection()
    task = session.get(Task, task_id)
    if task is None:
        conn.execute(text("DELETE FROM task_search_fts WHERE rowid = :tid"), {"tid": task_id})
        return
    notes_plain = _aggregate_notes_plain(session, task_id)
    title = task.title or ""
    desc = _to_plain_text(task.description)
    conn.execute(text("DELETE FROM task_search_fts WHERE rowid = :tid"), {"tid": task_id})
    conn.execute(
        text(
            "INSERT INTO task_search_fts(rowid, task_id, title, description, notes) "
            "VALUES (:rowid, :task_id, :title, :description, :notes)"
        ),
        {
            "rowid": task_id,
            "task_id": task_id,
            "title": title,
            "description": desc,
            "notes": notes_plain,
        },
    )


def sync_all_task_search_fts_if_stale(session: Session) -> None:
    """Backfill or repair the FTS table when its row count disagrees with ``tasks``."""
    if not _fts_table_exists(session):
        return
    task_n = int(session.scalar(select(func.count()).select_from(Task)) or 0)
    fts_n = int(session.scalar(text("SELECT count(*) FROM task_search_fts")) or 0)
    if task_n == fts_n:
        return
    for tid in session.scalars(select(Task.id)).all():
        sync_task_search_fts(session, int(tid))


def _clip(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_audit_value(field_name: str, raw: str | None) -> str:
    if raw is None:
        return "None"
    if field_name in {"description"}:
        plain = _to_plain_text(raw)
        return _clip(plain) if plain else "(empty)"
    return _clip(raw)


def _task_taxonomy_labels(task: Task) -> tuple[str, str, str]:
    area = task.area
    sub = area.subcategory if area else None
    cat = sub.category if sub else None
    return (
        cat.name if cat else "",
        sub.name if sub else "",
        area.name if area else "",
    )


def _area_label_by_id(session: Session, area_id: int | None) -> str | None:
    if area_id is None:
        return None
    area = session.get(
        TaskArea,
        area_id,
        options=[joinedload(TaskArea.subcategory).joinedload(TaskSubCategory.category)],
    )
    if area is None:
        return None
    sub = area.subcategory
    cat = sub.category if sub else None
    cat_name = cat.name if cat else ""
    sub_name = sub.name if sub else ""
    return f"{cat_name} / {sub_name} / {area.name}".strip(" /")


def _person_label_by_id(session: Session, person_id: int | None) -> str | None:
    if person_id is None:
        return None
    person = session.get(TaskPerson, person_id)
    if person is None:
        return None
    return f"{person.last_name}, {person.first_name} ({person.employee_id})"


@dataclass
class TimelineEntry:
    at: dt.datetime
    kind: Literal["audit", "note", "note_edit"]
    summary: str
    detail: str | None = None


def _like_pattern(needle: str) -> str:
    cleaned = "".join(c for c in needle.lower() if c not in "%_\\")
    return f"%{cleaned}%"


_UNSET = object()


class TaskService:
    ATTACHMENT_SOFT_CAP_BYTES: int = 100 * 1024 * 1024

    def __init__(self, session: Session, vault_root: Path | None = None):
        self.session = session
        self.vault_root = Path(vault_root).resolve() if vault_root is not None else None

    @staticmethod
    def _slugify_tag(name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        return base or quote(name.strip().lower())[:80] or "tag"

    def _next_unique_tag_slug(self, desired: str, *, exclude_tag_id: int | None = None) -> str:
        slug = desired
        n = 2
        while True:
            q = select(Tag).where(Tag.slug == slug)
            if exclude_tag_id is not None:
                q = q.where(Tag.id != exclude_tag_id)
            if self.session.scalar(q) is None:
                return slug
            slug = f"{desired}-{n}"
            n += 1

    def list_tags(self) -> list[Tag]:
        return list(self.session.scalars(select(Tag).order_by(Tag.name)).all())

    def create_tag(self, name: str, *, color_hint: str | None = None) -> Tag | None:
        nm = name.strip()
        if not nm:
            return None
        if self.session.scalar(select(Tag).where(Tag.name == nm)):
            return None
        desired = self._slugify_tag(nm)
        slug = self._next_unique_tag_slug(desired)
        row = Tag(name=nm, slug=slug, color_hint=(color_hint.strip() if color_hint else None))
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def rename_tag(self, tag_id: int, name: str) -> Tag | None:
        row = self.session.get(Tag, tag_id)
        nm = name.strip()
        if row is None or not nm:
            return None
        if nm != row.name and self.session.scalar(select(Tag).where(Tag.name == nm, Tag.id != tag_id)):
            return None
        row.name = nm
        row.slug = self._next_unique_tag_slug(self._slugify_tag(nm), exclude_tag_id=tag_id)
        self.session.commit()
        self.session.refresh(row)
        return row

    def update_tag(self, tag_id: int, *, color_hint: str | None = None) -> Tag | None:
        row = self.session.get(Tag, tag_id)
        if row is None:
            return None
        row.color_hint = color_hint.strip() if color_hint else None
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete_tag(self, tag_id: int) -> bool:
        row = self.session.get(Tag, tag_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def merge_tags(self, source_tag_id: int, target_tag_id: int) -> bool:
        if source_tag_id == target_tag_id:
            return False
        source = self.session.get(Tag, source_tag_id)
        target = self.session.get(Tag, target_tag_id)
        if source is None or target is None:
            return False
        src_tasks = self.session.scalars(select(Task).join(Task.tags).where(Tag.id == source.id)).all()
        for t in src_tasks:
            if target not in t.tags:
                t.tags.append(target)
            if source in t.tags:
                t.tags.remove(source)
        self.session.delete(source)
        self.session.commit()
        return True

    def set_task_tags(self, task_id: int, tag_ids: list[int]) -> bool:
        task = self.session.get(Task, task_id)
        if task is None:
            return False
        rows = self.session.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all() if tag_ids else []
        task.tags = sorted(rows, key=lambda x: x.name.lower())
        self.session.commit()
        return True

    def attach_tag_to_task(self, task_id: int, tag_id: int) -> bool:
        task = self.session.get(Task, task_id)
        tag = self.session.get(Tag, tag_id)
        if task is None or tag is None:
            return False
        if tag not in task.tags:
            task.tags.append(tag)
            self.session.commit()
        return True

    def detach_tag_from_task(self, task_id: int, tag_id: int) -> bool:
        task = self.session.get(Task, task_id)
        tag = self.session.get(Tag, tag_id)
        if task is None or tag is None:
            return False
        if tag in task.tags:
            task.tags.remove(tag)
            self.session.commit()
        return True

    def export_tags(self, path: Path) -> None:
        payload = {
            "version": 1,
            "tags": [
                {"name": t.name, "slug": t.slug, "color_hint": t.color_hint}
                for t in self.list_tags()
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_tags(self, path: Path) -> dict[str, int]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("tags", []) if isinstance(raw, dict) else []
        created = 0
        merged = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            color = row.get("color_hint")
            existing = self.session.scalar(select(Tag).where(Tag.name == name))
            if existing is None:
                if self.create_tag(name, color_hint=str(color) if color is not None else None):
                    created += 1
            else:
                existing.color_hint = str(color).strip() if color is not None and str(color).strip() else existing.color_hint
                merged += 1
        self.session.commit()
        return {"created": created, "merged": merged}

    def _dependency_reachable(self, start_id: int, target_id: int) -> bool:
        if start_id == target_id:
            return True
        seen: set[int] = set()
        stack = [start_id]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            nxt = self.session.scalars(
                select(TaskDependency.blocked_task_id).where(TaskDependency.blocker_task_id == cur)
            ).all()
            for nid in nxt:
                if int(nid) == target_id:
                    return True
                stack.append(int(nid))
        return False

    def add_dependency(
        self, blocker_task_id: int, blocked_task_id: int, *, note: str | None = None
    ) -> TaskDependency | None:
        if blocker_task_id == blocked_task_id:
            raise ValueError("A task cannot depend on itself.")
        if self.session.get(Task, blocker_task_id) is None or self.session.get(Task, blocked_task_id) is None:
            return None
        existing = self.session.scalar(
            select(TaskDependency).where(
                TaskDependency.blocker_task_id == blocker_task_id,
                TaskDependency.blocked_task_id == blocked_task_id,
            )
        )
        if existing is not None:
            return existing
        # New edge blocker->blocked must not make a cycle.
        if self._dependency_reachable(blocked_task_id, blocker_task_id):
            raise ValueError("Dependency cycle detected.")
        row = TaskDependency(
            blocker_task_id=blocker_task_id,
            blocked_task_id=blocked_task_id,
            note=note.strip() if note and note.strip() else None,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def remove_dependency(self, dependency_id: int) -> bool:
        row = self.session.get(TaskDependency, dependency_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def list_dependencies(self, task_id: int) -> tuple[list[TaskDependency], list[TaskDependency]]:
        upstream = list(
            self.session.scalars(
                select(TaskDependency)
                .where(TaskDependency.blocked_task_id == task_id)
                .options(selectinload(TaskDependency.blocker_task))
                .order_by(TaskDependency.created_at)
            ).all()
        )
        downstream = list(
            self.session.scalars(
                select(TaskDependency)
                .where(TaskDependency.blocker_task_id == task_id)
                .options(selectinload(TaskDependency.blocked_task))
                .order_by(TaskDependency.created_at)
            ).all()
        )
        return upstream, downstream

    def has_open_upstream_dependency(self, task_id: int) -> bool:
        rows = self.session.scalars(
            select(TaskDependency)
            .where(TaskDependency.blocked_task_id == task_id)
            .options(selectinload(TaskDependency.blocker_task))
        ).all()
        for dep in rows:
            if dep.blocker_task.status != TaskStatus.CLOSED:
                return True
        return False

    @staticmethod
    def _safe_attachment_filename(orig: str) -> str:
        name = Path(orig).name.strip()
        if not name or name in (".", ".."):
            return "file"
        return name[:240]

    def add_task_attachment(
        self,
        task_id: int,
        source: Path,
        *,
        confirm_large: bool = False,
    ) -> tuple[TaskAttachment | None, str | None]:
        """Copy ``source`` into the vault and create a row. Returns ``(row, error)``.

        ``error`` is ``\"oversize\"`` when the file exceeds :attr:`ATTACHMENT_SOFT_CAP_BYTES`
        and ``confirm_large`` is false; ``\"no_vault\"`` when no vault root was configured.
        """
        if self.vault_root is None:
            return None, "no_vault"
        task = self.session.get(Task, task_id)
        if not task:
            return None, "missing_task"
        src = Path(source).expanduser().resolve()
        if not src.is_file():
            return None, "missing_file"
        size = int(src.stat().st_size)
        if size > self.ATTACHMENT_SOFT_CAP_BYTES and not confirm_large:
            return None, "oversize"
        sha = hashlib.sha256()
        with open(src, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha.update(chunk)
        sha_hex = sha.hexdigest()
        base_name = self._safe_attachment_filename(src.name)
        dest_dir = attachments_dir(self.vault_root) / str(task_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{sha_hex}_{base_name}"
        candidate = dest_dir / stem
        n = 2
        while candidate.exists():
            p = Path(stem)
            candidate = dest_dir / f"{p.stem}_{n}{p.suffix}"
            n += 1
        shutil.copy2(src, candidate)
        relpath = candidate.relative_to(self.vault_root.resolve()).as_posix()
        mime, _ = mimetypes.guess_type(src.name)
        row = TaskAttachment(
            task_id=task_id,
            display_name=base_name,
            storage_relpath=relpath,
            content_sha256=sha_hex,
            size_bytes=size,
            mime_hint=mime,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row, None

    def remove_task_attachment(self, attachment_id: int) -> bool:
        if self.vault_root is None:
            return False
        row = self.session.get(TaskAttachment, attachment_id)
        if not row:
            return False
        rel = row.storage_relpath.replace("/", os.sep)
        abs_path = self.vault_root / rel
        self.session.delete(row)
        self.session.commit()
        try:
            abs_path.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def rename_task_attachment(self, attachment_id: int, display_name: str) -> bool:
        row = self.session.get(TaskAttachment, attachment_id)
        if not row:
            return False
        cleaned = display_name.strip()
        if not cleaned:
            return False
        row.display_name = cleaned[:500]
        self.session.commit()
        return True

    def materialize_attachment_open_copy(self, attachment_id: int, dest_dir: Path) -> Path | None:
        """Copy vault plaintext into ``dest_dir`` for opening with an external app."""
        if self.vault_root is None:
            return None
        row = self.session.get(TaskAttachment, attachment_id)
        if not row:
            return None
        rel = row.storage_relpath.replace("/", os.sep)
        src = self.vault_root / rel
        if not src.is_file():
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = self._safe_attachment_filename(row.display_name)
        dest = dest_dir / safe
        if dest.exists():
            stem = Path(safe).stem
            suf = Path(safe).suffix
            dest = dest_dir / f"{stem}_{attachment_id}{suf}"
        shutil.copy2(src, dest)
        return dest

    def _next_ticket_number(self) -> int:
        self.session.flush()
        m = self.session.scalar(select(func.coalesce(func.max(Task.ticket_number), -1)))
        return int(m) + 1

    def list_tasks(
        self,
        *,
        include_closed: bool = True,
        status: str | None = None,
        tag_id: int | None = None,
    ) -> list[Task]:
        q: Select[tuple[Task]] = select(Task).options(
            selectinload(Task.todos),
            selectinload(Task.tags),
            selectinload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
            selectinload(Task.area).selectinload(TaskArea.subcategory).selectinload(TaskSubCategory.category),
            selectinload(Task.person),
        )
        if not include_closed:
            q = q.where(Task.status != TaskStatus.CLOSED)
        if status:
            q = q.where(Task.status == status)
        if tag_id is not None:
            q = q.join(Task.tags).where(Tag.id == tag_id)
        # Due dates present first, then by due date, priority, title
        q = q.order_by(Task.ticket_number.is_(None), Task.ticket_number, Task.due_date.is_(None), Task.due_date, Task.priority, Task.title)
        return list(self.session.scalars(q).unique().all())

    def _fts_task_ids_and_snippets(
        self, fts_fields: set[str], raw: str
    ) -> tuple[list[int], dict[int, str]]:
        if not fts_fields or not _fts_eligible(raw) or not _fts_table_exists(self.session):
            return [], {}
        match_expr = _fts_match_expression(fts_fields, raw)
        sql = text(
            """
            SELECT rowid AS task_id,
                   snippet(task_search_fts, -1, :h0, :h1, :ellip, :ntok) AS snip
            FROM task_search_fts
            WHERE task_search_fts MATCH :match
            ORDER BY rank
            """
        )
        try:
            rows = (
                self.session.connection()
                .execute(
                    sql,
                    {
                        "match": match_expr,
                        "h0": "**",
                        "h1": "**",
                        "ellip": "…",
                        "ntok": 12,
                    },
                )
                .mappings()
                .all()
            )
        except Exception:
            return [], {}
        ids: list[int] = []
        snippets: dict[int, str] = {}
        for r in rows:
            tid = int(r["task_id"])
            ids.append(tid)
            sn = r["snip"]
            if sn:
                snippets[tid] = sn
        return ids, snippets

    def search_tasks(
        self,
        needle: str,
        *,
        fields: set[str],
        include_closed: bool = True,
        tag_id: int | None = None,
    ) -> list[TaskSearchHit]:
        raw = needle.strip()
        if not raw:
            return [TaskSearchHit(t, None) for t in self.list_tasks(include_closed=include_closed)]
        pat = _like_pattern(raw)
        conds: list[Any] = []
        snippet_by_id: dict[int, str] = {}

        fts_fields = fields & _FTS_INDEXED_FIELDS
        aux_fields = fields & {"todos", "blockers", "audit"}
        use_fts = (
            bool(fts_fields)
            and not aux_fields
            and _fts_eligible(raw)
            and _fts_table_exists(self.session)
        )

        if use_fts:
            fts_ids, snippet_by_id = self._fts_task_ids_and_snippets(fts_fields, raw)
            if fts_ids:
                conds.append(Task.id.in_(fts_ids))
        else:
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
                selectinload(Task.tags),
                selectinload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
                selectinload(Task.area).selectinload(TaskArea.subcategory).selectinload(TaskSubCategory.category),
                selectinload(Task.person),
            )
            .distinct()
        )
        if not include_closed:
            q = q.where(Task.status != TaskStatus.CLOSED)
        if tag_id is not None:
            q = q.join(Task.tags).where(Tag.id == tag_id)
        q = q.order_by(
            Task.ticket_number.is_(None),
            Task.ticket_number,
            Task.due_date.is_(None),
            Task.due_date,
            Task.priority,
            Task.title,
        )
        tasks = list(self.session.scalars(q).unique().all())
        return [TaskSearchHit(t, snippet_by_id.get(t.id)) for t in tasks]

    def get_task(self, task_id: int) -> Task | None:
        # joinedload on collections duplicates parent rows; .unique() is required (SQLAlchemy 2).
        return self.session.scalars(
            select(Task)
            .where(Task.id == task_id)
            .options(
                selectinload(Task.todos),
                selectinload(Task.tags),
                selectinload(Task.notes).selectinload(TaskNote.versions),
                selectinload(Task.blockers),
                selectinload(Task.dependencies_incoming).selectinload(TaskDependency.blocker_task),
                selectinload(Task.dependencies_outgoing).selectinload(TaskDependency.blocked_task),
                selectinload(Task.attachments),
                selectinload(Task.recurring_rule).selectinload(RecurringRule.todo_templates),
                selectinload(Task.area).selectinload(TaskArea.subcategory).selectinload(TaskSubCategory.category),
                selectinload(Task.person),
            )
        ).unique().one_or_none()

    def delete_task(self, task_id: int) -> bool:
        """Remove a task and its FTS row. Returns False if the id did not exist."""
        task = self.session.get(Task, task_id)
        if not task:
            return False
        tid = task.id
        self.session.delete(task)
        self.session.flush()
        sync_task_search_fts(self.session, tid)
        self.session.commit()
        if self.vault_root is not None:
            purge_task_attachments_folder(self.vault_root, tid)
        return True

    def create_task(
        self,
        *,
        title: str,
        received_date: dt.date,
        due_date: dt.date | None = None,
        description: str | None = None,
        resolution: str | None = None,
        status: str = TaskStatus.OPEN,
        impact: int = 2,
        urgency: int = 2,
        area_id: int | None = None,
        person_id: int | None = None,
    ) -> Task:
        pr = compute_priority(impact=impact, urgency=urgency)
        ticket_number = self._next_ticket_number()
        task = Task(
            ticket_number=ticket_number,
            title=title.strip(),
            description=description,
            resolution=(resolution.strip() if resolution is not None and resolution.strip() else None),
            status=status,
            impact=impact,
            urgency=urgency,
            priority=pr,
            received_date=received_date,
            due_date=due_date,
            area_id=area_id,
            person_id=person_id,
        )
        self.session.add(task)
        self.session.flush()
        _log_change(self.session, task.id, "title", None, task.title)
        _log_change(self.session, task.id, "status", None, task.status)
        _log_change(self.session, task.id, "ticket_number", None, str(task.ticket_number))
        if area_id is not None:
            _log_change(self.session, task.id, "area", None, _area_label_by_id(self.session, area_id))
        if person_id is not None:
            _log_change(
                self.session, task.id, "for_person", None, _person_label_by_id(self.session, person_id)
            )
        refresh_next_milestone(self.session, task)
        sync_task_search_fts(self.session, task.id)
        self.session.commit()
        self.session.refresh(task)
        return task

    def update_task_fields(
        self,
        task_id: int,
        *,
        title: str | None = None,
        description: "str | None | object" = _UNSET,
        resolution: "str | None | object" = _UNSET,
        status: str | None = None,
        impact: int | None = None,
        urgency: int | None = None,
        received_date: dt.date | None = None,
        due_date: "dt.date | None | object" = _UNSET,
        closed_date: "dt.date | None | object" = _UNSET,
        area_id: int | None | object = _UNSET,
        person_id: int | None | object = _UNSET,
    ) -> Task | None:
        task = self.session.get(Task, task_id)
        if not task:
            return None

        if title is not None and title.strip() != task.title:
            _log_change(self.session, task.id, "title", task.title, title.strip())
            task.title = title.strip()
        if description is not _UNSET and description != task.description:
            _log_change(self.session, task.id, "description", task.description, description)
            task.description = description  # type: ignore[assignment]
        if resolution is not _UNSET:
            new_resolution = (
                None
                if resolution is None or not str(resolution).strip()
                else str(resolution).strip()
            )
            if new_resolution != task.resolution:
                _log_change(self.session, task.id, "resolution", task.resolution, new_resolution)
                task.resolution = new_resolution
        if status is not None and status != task.status:
            _log_change(self.session, task.id, "status", task.status, status)
            task.status = status
        if received_date is not None and received_date != task.received_date:
            _log_change(self.session, task.id, "received_date", task.received_date, received_date)
            task.received_date = received_date
        if due_date is not _UNSET and due_date != task.due_date:
            _log_change(self.session, task.id, "due_date", task.due_date, due_date)
            task.due_date = due_date  # type: ignore[assignment]
        if closed_date is not _UNSET and closed_date != task.closed_date:
            _log_change(self.session, task.id, "closed_date", task.closed_date, closed_date)
            task.closed_date = closed_date  # type: ignore[assignment]
        if area_id is not _UNSET and area_id != task.area_id:
            _log_change(
                self.session,
                task.id,
                "area",
                _area_label_by_id(self.session, task.area_id),
                _area_label_by_id(self.session, int(area_id) if area_id is not None else None),
            )
            task.area_id = area_id
        if person_id is not _UNSET and person_id != task.person_id:
            _log_change(
                self.session,
                task.id,
                "for_person",
                _person_label_by_id(self.session, task.person_id),
                _person_label_by_id(self.session, int(person_id) if person_id is not None else None),
            )
            task.person_id = person_id

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
        sync_task_search_fts(self.session, task.id)
        self.session.commit()
        self.session.refresh(task)
        return task

    def close_task(
        self,
        task_id: int,
        *,
        closed_on: dt.date | None = None,
        resolution: str | None = None,
    ) -> tuple[Task | None, Task | None]:
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
            if resolution is None or not str(resolution).strip():
                raise ValueError("Resolution is required when closing a task.")
            old_status = task.status
            old_closed = task.closed_date
            old_resolution = task.resolution
            new_resolution = str(resolution).strip()
            task.status = TaskStatus.CLOSED
            task.closed_date = close_day
            task.resolution = new_resolution
            _log_change(self.session, task.id, "status", old_status, TaskStatus.CLOSED)
            _log_change(self.session, task.id, "closed_date", old_closed, close_day)
            _log_change(self.session, task.id, "resolution", old_resolution, new_resolution)
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

        if new_task is not None:
            sync_task_search_fts(self.session, new_task.id)
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
            area_id=closed.area_id,
            person_id=closed.person_id,
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
        resolution: str | None = None,
        milestone_date: dt.date | None = None,
    ) -> TodoItem | None:
        task = self.session.get(Task, task_id)
        if not task:
            return None
        order = max((t.sort_order for t in task.todos), default=-1) + 1
        todo = TodoItem(
            task_id=task_id,
            sort_order=order,
            title=title.strip(),
            resolution=(resolution.strip() if resolution is not None and resolution.strip() else None),
            milestone_date=milestone_date,
        )
        self.session.add(todo)
        refresh_next_milestone(self.session, task)
        self.session.commit()
        self.session.refresh(todo)
        return todo

    def delete_todo(self, todo_id: int) -> bool:
        """Remove a todo row from its parent task.

        Returns ``True`` when a row was deleted so UI code can refresh
        without guessing. The parent task's denormalized
        ``next_milestone_date`` is recomputed so any newly-exposed
        milestone shows up in sidebars and calendars immediately.
        """
        todo = self.session.get(TodoItem, todo_id)
        if todo is None:
            return False
        task_id = todo.task_id
        self.session.delete(todo)
        self.session.flush()
        task = self.session.get(Task, task_id)
        if task is not None:
            refresh_next_milestone(self.session, task)
        self.session.commit()
        return True

    def complete_todo(self, todo_id: int, *, resolution: str | None = None) -> None:
        todo = self.session.get(TodoItem, todo_id)
        if not todo or todo.completed_at:
            return
        if resolution is not None:
            todo.resolution = resolution.strip() or None
        todo.completed_at = dt.datetime.now(dt.UTC)
        task = self.session.get(Task, todo.task_id)
        if task:
            refresh_next_milestone(self.session, task)
        self.session.commit()

    def get_todo(self, todo_id: int) -> TodoItem | None:
        """Return the ``TodoItem`` with this id, or ``None`` if missing."""
        return self.session.get(TodoItem, todo_id)

    def update_todo(
        self,
        todo_id: int,
        *,
        title: str | None = None,
        resolution: "str | None | object" = _UNSET,
        milestone_date: "dt.date | None | object" = _UNSET,
    ) -> TodoItem | None:
        """Edit a todo's title and/or milestone date.

        ``title`` is applied only when non-``None`` and non-empty after strip.
        ``milestone_date`` uses the module-level ``_UNSET`` sentinel to
        distinguish "leave alone" from "clear to ``None``": callers pass the
        new date, pass ``None`` to clear, or omit the argument to leave it.
        The owning task's next-milestone cache is refreshed when either field
        actually changes.
        """
        todo = self.session.get(TodoItem, todo_id)
        if todo is None:
            return None
        changed = False
        if title is not None:
            stripped = title.strip()
            if stripped and stripped != todo.title:
                todo.title = stripped
                changed = True
        if resolution is not _UNSET:
            cleaned = None if resolution is None or not str(resolution).strip() else str(resolution).strip()
            if cleaned != todo.resolution:
                todo.resolution = cleaned
                changed = True
        if milestone_date is not _UNSET and milestone_date != todo.milestone_date:
            todo.milestone_date = milestone_date  # type: ignore[assignment]
            changed = True
        if changed:
            task = self.session.get(Task, todo.task_id)
            if task is not None:
                refresh_next_milestone(self.session, task)
            self.session.commit()
            self.session.refresh(todo)
        return todo

    def shift_task_milestones(
        self,
        task_id: int,
        delta_days: int,
        *,
        business_days: bool = False,
    ) -> int:
        """Shift every open todo milestone on ``task_id`` by ``delta_days``.

        Intended for the calendar quick-edit dialog's "also shift todo
        milestones" checkbox: the dialog applies the task's own due-date
        change through :meth:`update_task_fields`, then calls this
        helper to fan the same delta out to the todo rows. Todos with
        ``milestone_date`` set to ``None`` are skipped. Returns the
        number of rows updated so the caller can notify the user.

        Uses :func:`shift_business_days` when ``business_days`` is set;
        otherwise does plain calendar arithmetic.
        """
        if delta_days == 0:
            return 0
        task = self.session.get(Task, task_id)
        if task is None:
            return 0
        holidays = _holidays_set(self.session) if business_days else set()
        touched = 0
        for td in list(task.todos):
            if td.milestone_date is None:
                continue
            if business_days:
                new = shift_business_days(
                    td.milestone_date, delta_days, holidays,
                    skip_weekends=True, skip_holidays=True,
                )
            else:
                new = td.milestone_date + dt.timedelta(days=delta_days)
            if new != td.milestone_date:
                td.milestone_date = new
                touched += 1
        if touched:
            refresh_next_milestone(self.session, task)
            self.session.commit()
        return touched

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
        self.session.flush()
        sync_task_search_fts(self.session, task_id)
        self.session.commit()
        self.session.refresh(note)
        return note

    def update_note_body(self, note_id: int, body_html: str) -> None:
        note = self.session.get(TaskNote, note_id, options=[joinedload(TaskNote.versions)])
        if not note or note.is_system:
            return
        seq = max((v.version_seq for v in note.versions), default=0) + 1
        self.session.add(TaskNoteVersion(note_id=note.id, version_seq=seq, body_html=body_html))
        self.session.flush()
        sync_task_search_fts(self.session, note.task_id)
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
                    "category",
                    "subcategory",
                    "area",
                    "for_person",
                    "for_person_employee_id",
                ]
            )
            for t in tasks:
                cat_name, sub_name, area_name = _task_taxonomy_labels(t)
                person_name = ""
                person_emp = ""
                if t.person is not None:
                    person_name = f"{t.person.last_name}, {t.person.first_name}"
                    person_emp = t.person.employee_id
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
                        cat_name,
                        sub_name,
                        area_name,
                        person_name,
                        person_emp,
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
            "category",
            "subcategory",
            "area",
            "for_person",
            "for_person_employee_id",
        ]
        ws.append(headers)
        for t in tasks:
            cat_name, sub_name, area_name = _task_taxonomy_labels(t)
            person_name = ""
            person_emp = ""
            if t.person is not None:
                person_name = f"{t.person.last_name}, {t.person.first_name}"
                person_emp = t.person.employee_id
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
                    cat_name,
                    sub_name,
                    area_name,
                    person_name,
                    person_emp,
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

    # ------------------------------------------------------------------
    # Dashboard aggregation
    # ------------------------------------------------------------------
    # The Dashboard tab (plan 01) renders a small fixed set of
    # "what needs attention right now" cards. Each card has a row count
    # and a compact list of the top N tasks that drive it. Rather than
    # spread five near-identical queries across the UI layer, we build
    # them once here against a single prefetched pool of non-terminal
    # tasks so card math stays internally consistent (overdue + due
    # today never disagree by an off-by-one bucket boundary).

    # Statuses that keep a task off dashboard cards entirely. Closed and
    # cancelled are terminal states and out of scope for active triage.
    _DASHBOARD_EXCLUDED_STATUSES: frozenset[str] = frozenset(
        {TaskStatus.CLOSED, TaskStatus.CANCELLED}
    )

    def dashboard_sections(
        self,
        *,
        as_of: dt.date | None = None,
        top_n: int = 8,
    ) -> dict[str, dict[str, Any]]:
        """Return card payloads keyed by card id.

        Each value is a dict with ``count`` (total matching tasks) and
        ``rows`` (up to ``top_n`` Task rows, ordered for display).

        Card ids are stable and consumed both by the UI layer and by
        tests; see :data:`DASHBOARD_CARD_IDS` for the authoritative
        tuple and the declared ordering.

        The function is deliberately tolerant of today's input: it
        prefetches the active task pool once and reuses it across
        cards so the numbers cannot drift mid-render, and it treats
        "top priority" as P1 + P2 only (anything lower is already on
        the list and does not need a dedicated signal).
        """
        today = as_of or dt.date.today()
        week_end = today + dt.timedelta(days=6)
        pool = [
            t
            for t in self.list_tasks(include_closed=False)
            if t.status not in self._DASHBOARD_EXCLUDED_STATUSES
        ]

        def _sort_key(t: Task) -> tuple[int, dt.date, int, str]:
            # Tasks with a due date first (ascending), then priority
            # ascending (1 = Critical), then title for a stable tail.
            no_due = 1 if t.due_date is None else 0
            return (no_due, t.due_date or dt.date.max, t.priority, t.title)

        def _bucket(pred) -> list[Task]:
            return sorted([t for t in pool if pred(t)], key=_sort_key)

        overdue = _bucket(lambda t: t.due_date is not None and t.due_date < today)
        due_today = _bucket(lambda t: t.due_date == today)
        due_this_week = _bucket(
            lambda t: t.due_date is not None and today <= t.due_date <= week_end
        )
        blocked = _bucket(lambda t: t.status == TaskStatus.BLOCKED)
        top_priority = _bucket(lambda t: t.priority <= 2)

        def _payload(rows: list[Task]) -> dict[str, Any]:
            return {"count": len(rows), "rows": rows[:top_n]}

        return {
            "overdue": _payload(overdue),
            "due_today": _payload(due_today),
            "due_this_week": _payload(due_this_week),
            "blocked": _payload(blocked),
            "top_priority": _payload(top_priority),
        }

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

    def list_categories(self) -> list[TaskCategory]:
        q = (
            select(TaskCategory)
            .options(
                selectinload(TaskCategory.subcategories).selectinload(TaskSubCategory.areas),
            )
            .order_by(TaskCategory.name)
        )
        return list(self.session.scalars(q).unique().all())

    def add_category(self, name: str) -> TaskCategory | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        existing = self.session.scalar(select(TaskCategory).where(TaskCategory.name == cleaned))
        if existing:
            return existing
        item = TaskCategory(name=cleaned)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete_category(self, category_id: int) -> None:
        cat = self.session.get(
            TaskCategory,
            category_id,
            options=[selectinload(TaskCategory.subcategories).selectinload(TaskSubCategory.areas)],
        )
        if not cat:
            return
        area_ids = [a.id for s in cat.subcategories for a in s.areas]
        if area_ids:
            for task in self.session.scalars(select(Task).where(Task.area_id.in_(area_ids))).all():
                task.area_id = None
        self.session.delete(cat)
        self.session.commit()

    def list_subcategories(self, category_id: int) -> list[TaskSubCategory]:
        q = (
            select(TaskSubCategory)
            .where(TaskSubCategory.category_id == category_id)
            .options(selectinload(TaskSubCategory.areas))
            .order_by(TaskSubCategory.name)
        )
        return list(self.session.scalars(q).unique().all())

    def add_subcategory(self, category_id: int, name: str) -> TaskSubCategory | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        category = self.session.get(TaskCategory, category_id)
        if not category:
            return None
        existing = self.session.scalar(
            select(TaskSubCategory).where(
                TaskSubCategory.category_id == category_id,
                TaskSubCategory.name == cleaned,
            )
        )
        if existing:
            return existing
        item = TaskSubCategory(category_id=category_id, name=cleaned)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete_subcategory(self, subcategory_id: int) -> None:
        sub = self.session.get(
            TaskSubCategory,
            subcategory_id,
            options=[selectinload(TaskSubCategory.areas)],
        )
        if not sub:
            return
        area_ids = [a.id for a in sub.areas]
        if area_ids:
            for task in self.session.scalars(select(Task).where(Task.area_id.in_(area_ids))).all():
                task.area_id = None
        self.session.delete(sub)
        self.session.commit()

    def list_areas(self, subcategory_id: int) -> list[TaskArea]:
        q = (
            select(TaskArea)
            .where(TaskArea.subcategory_id == subcategory_id)
            .order_by(TaskArea.name)
        )
        return list(self.session.scalars(q).all())

    def add_area(self, subcategory_id: int, name: str) -> TaskArea | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        sub = self.session.get(TaskSubCategory, subcategory_id)
        if not sub:
            return None
        existing = self.session.scalar(
            select(TaskArea).where(
                TaskArea.subcategory_id == subcategory_id,
                TaskArea.name == cleaned,
            )
        )
        if existing:
            return existing
        item = TaskArea(subcategory_id=subcategory_id, name=cleaned)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete_area(self, area_id: int) -> None:
        area = self.session.get(TaskArea, area_id)
        if not area:
            return
        for task in self.session.scalars(select(Task).where(Task.area_id == area_id)).all():
            task.area_id = None
        self.session.delete(area)
        self.session.commit()

    def list_people(self) -> list[TaskPerson]:
        q = select(TaskPerson).order_by(TaskPerson.last_name, TaskPerson.first_name, TaskPerson.employee_id)
        return list(self.session.scalars(q).all())

    def add_person(self, first_name: str, last_name: str, employee_id: str) -> TaskPerson | None:
        first = first_name.strip()
        last = last_name.strip()
        emp = employee_id.strip()
        if not first or not last or not emp:
            return None
        existing = self.session.scalar(select(TaskPerson).where(TaskPerson.employee_id == emp))
        if existing:
            if existing.first_name != first or existing.last_name != last:
                existing.first_name = first
                existing.last_name = last
                self.session.commit()
                self.session.refresh(existing)
            return existing
        item = TaskPerson(first_name=first, last_name=last, employee_id=emp)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def delete_person(self, person_id: int) -> None:
        person = self.session.get(TaskPerson, person_id)
        if not person:
            return
        for task in self.session.scalars(select(Task).where(Task.person_id == person_id)).all():
            task.person_id = None
        self.session.delete(person)
        self.session.commit()

    def update_person(
        self, person_id: int, first_name: str, last_name: str, employee_id: str
    ) -> TaskPerson | None:
        first = first_name.strip()
        last = last_name.strip()
        emp = employee_id.strip()
        if not first or not last or not emp:
            return None
        person = self.session.get(TaskPerson, person_id)
        if not person:
            return None
        if emp != person.employee_id:
            taken = self.session.scalar(
                select(TaskPerson).where(TaskPerson.employee_id == emp, TaskPerson.id != person_id)
            )
            if taken:
                return None
        person.first_name = first
        person.last_name = last
        person.employee_id = emp
        self.session.commit()
        self.session.refresh(person)
        return person

    def rename_category(self, category_id: int, name: str) -> TaskCategory | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        cat = self.session.get(TaskCategory, category_id)
        if not cat:
            return None
        if cat.name == cleaned:
            return cat
        taken = self.session.scalar(select(TaskCategory).where(TaskCategory.name == cleaned))
        if taken:
            return None
        cat.name = cleaned
        self.session.commit()
        self.session.refresh(cat)
        return cat

    def rename_subcategory(self, subcategory_id: int, name: str) -> TaskSubCategory | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        sub = self.session.get(TaskSubCategory, subcategory_id)
        if not sub:
            return None
        if sub.name == cleaned:
            return sub
        taken = self.session.scalar(
            select(TaskSubCategory).where(
                TaskSubCategory.category_id == sub.category_id,
                TaskSubCategory.name == cleaned,
            )
        )
        if taken:
            return None
        sub.name = cleaned
        self.session.commit()
        self.session.refresh(sub)
        return sub

    def rename_area(self, area_id: int, name: str) -> TaskArea | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        area = self.session.get(TaskArea, area_id)
        if not area:
            return None
        if area.name == cleaned:
            return area
        taken = self.session.scalar(
            select(TaskArea).where(
                TaskArea.subcategory_id == area.subcategory_id,
                TaskArea.name == cleaned,
            )
        )
        if taken:
            return None
        area.name = cleaned
        self.session.commit()
        self.session.refresh(area)
        return area

    def export_reference_data(self, path: Path) -> None:
        categories_out: list[dict[str, Any]] = []
        for cat in self.list_categories():
            sub_out: list[dict[str, Any]] = []
            for sub in sorted(cat.subcategories, key=lambda x: x.name.lower()):
                sub_out.append(
                    {
                        "name": sub.name,
                        "areas": [a.name for a in sorted(sub.areas, key=lambda x: x.name.lower())],
                    }
                )
            categories_out.append({"name": cat.name, "subcategories": sub_out})
        people_out = [
            {
                "first_name": p.first_name,
                "last_name": p.last_name,
                "employee_id": p.employee_id,
            }
            for p in self.list_people()
        ]
        payload = {"categories": categories_out, "people": people_out}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_reference_data(self, path: Path) -> dict[str, int]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        categories = raw.get("categories", []) if isinstance(raw, dict) else []
        people = raw.get("people", []) if isinstance(raw, dict) else []

        for cat in categories:
            if not isinstance(cat, dict):
                continue
            cobj = self.add_category(str(cat.get("name", "")))
            if cobj is None:
                continue
            for sub in cat.get("subcategories", []):
                if not isinstance(sub, dict):
                    continue
                sobj = self.add_subcategory(cobj.id, str(sub.get("name", "")))
                if sobj is None:
                    continue
                for area_name in sub.get("areas", []):
                    if not isinstance(area_name, str):
                        continue
                    self.add_area(sobj.id, area_name)

        for person in people:
            if not isinstance(person, dict):
                continue
            self.add_person(
                str(person.get("first_name", "")),
                str(person.get("last_name", "")),
                str(person.get("employee_id", "")),
            )
        # Return current totals after merge/import for a simple confirmation summary.
        sub_total = self.session.scalar(select(func.count(TaskSubCategory.id))) or 0
        area_total = self.session.scalar(select(func.count(TaskArea.id))) or 0
        return {
            "categories": len(self.list_categories()),
            "subcategories": int(sub_total),
            "areas": int(area_total),
            "people": len(self.list_people()),
        }

    def list_task_templates(self) -> list[TaskTemplate]:
        q = (
            select(TaskTemplate)
            .options(selectinload(TaskTemplate.todos))
            .order_by(TaskTemplate.sort_order, TaskTemplate.name)
        )
        return list(self.session.scalars(q).unique().all())

    def get_task_template(self, template_id: int) -> TaskTemplate | None:
        return self.session.scalars(
            select(TaskTemplate)
            .where(TaskTemplate.id == template_id)
            .options(selectinload(TaskTemplate.todos))
        ).unique().one_or_none()

    def create_task_template(
        self,
        *,
        name: str,
        title_pattern: str,
        description_pattern: str | None = None,
        default_area_id: int | None = None,
        default_person_id: int | None = None,
        default_impact: int = 2,
        default_urgency: int = 2,
        default_status: str = TaskStatus.OPEN,
        todo_specs: list[tuple[str, int, int | None]],
    ) -> TaskTemplate | None:
        cleaned = name.strip()
        if not cleaned:
            return None
        if self.session.scalar(select(TaskTemplate).where(TaskTemplate.name == cleaned)):
            return None
        mx = self.session.scalar(select(func.coalesce(func.max(TaskTemplate.sort_order), -1)))
        sort_order = int(mx) + 1
        tt = TaskTemplate(
            name=cleaned,
            title_pattern=title_pattern.strip(),
            description_pattern=description_pattern,
            default_area_id=default_area_id,
            default_person_id=default_person_id,
            default_impact=default_impact,
            default_urgency=default_urgency,
            default_status=default_status,
            sort_order=sort_order,
        )
        self.session.add(tt)
        self.session.flush()
        for t_title, t_order, off in todo_specs:
            self.session.add(
                TaskTemplateTodo(
                    template_id=tt.id,
                    sort_order=t_order,
                    title=t_title.strip(),
                    milestone_offset_days=off,
                )
            )
        self.session.commit()
        self.session.refresh(tt)
        return tt

    def update_task_template(
        self,
        template_id: int,
        *,
        name: str | None = None,
        title_pattern: str | None = None,
        description_pattern: "str | None | object" = _UNSET,
        default_area_id: "int | None | object" = _UNSET,
        default_person_id: "int | None | object" = _UNSET,
        default_impact: int | None = None,
        default_urgency: int | None = None,
        default_status: str | None = None,
        todo_specs: list[tuple[str, int, int | None]] | None = None,
    ) -> TaskTemplate | None:
        tt = self.session.get(
            TaskTemplate, template_id, options=[selectinload(TaskTemplate.todos)]
        )
        if not tt:
            return None
        if name is not None:
            nn = name.strip()
            if nn and nn != tt.name:
                taken = self.session.scalar(
                    select(TaskTemplate).where(
                        TaskTemplate.name == nn, TaskTemplate.id != template_id
                    )
                )
                if taken:
                    return None
                tt.name = nn
        if title_pattern is not None:
            tt.title_pattern = title_pattern.strip()
        if description_pattern is not _UNSET:
            tt.description_pattern = description_pattern  # type: ignore[assignment]
        if default_area_id is not _UNSET:
            tt.default_area_id = default_area_id  # type: ignore[assignment]
        if default_person_id is not _UNSET:
            tt.default_person_id = default_person_id  # type: ignore[assignment]
        if default_impact is not None:
            tt.default_impact = default_impact
        if default_urgency is not None:
            tt.default_urgency = default_urgency
        if default_status is not None:
            tt.default_status = default_status
        if todo_specs is not None:
            for old in list(tt.todos):
                self.session.delete(old)
            self.session.flush()
            for t_title, t_order, off in todo_specs:
                self.session.add(
                    TaskTemplateTodo(
                        template_id=tt.id,
                        sort_order=t_order,
                        title=t_title.strip(),
                        milestone_offset_days=off,
                    )
                )
        self.session.commit()
        self.session.refresh(tt)
        return tt

    def delete_task_template(self, template_id: int) -> None:
        tt = self.session.get(TaskTemplate, template_id)
        if tt:
            self.session.delete(tt)
            self.session.commit()

    def move_task_template(self, template_id: int, delta: int) -> None:
        rows = list(
            self.session.scalars(
                select(TaskTemplate).order_by(TaskTemplate.sort_order, TaskTemplate.name)
            ).all()
        )
        idx = next((i for i, r in enumerate(rows) if r.id == template_id), None)
        if idx is None or delta == 0:
            return
        j = idx + delta
        if j < 0 or j >= len(rows):
            return
        rows[idx], rows[j] = rows[j], rows[idx]
        for i, r in enumerate(rows):
            r.sort_order = i
        self.session.commit()

    def expand_task_template(
        self,
        template_id: int,
        *,
        received_date: dt.date,
        due_date: dt.date | None = None,
    ) -> TemplateApplySnapshot | None:
        _ = due_date  # reserved for future pattern tokens tied to due date
        tt = self.session.scalars(
            select(TaskTemplate)
            .where(TaskTemplate.id == template_id)
            .options(selectinload(TaskTemplate.todos))
        ).unique().one_or_none()
        if not tt:
            return None
        holidays = _holidays_set(self.session)
        title_raw = expand_task_template_placeholders(tt.title_pattern, received_date) or ""
        title = title_raw.strip()
        desc_raw = expand_task_template_placeholders(tt.description_pattern, received_date)
        description: str | None
        if desc_raw is None or not str(desc_raw).strip():
            description = None
        else:
            ds = str(desc_raw).strip()
            if ds.startswith("<") and ">" in ds:
                description = ds
            else:
                description = f"<p>{html.escape(ds)}</p>"
        area_id = tt.default_area_id
        if area_id is not None and self.session.get(TaskArea, area_id) is None:
            area_id = None
        person_id = tt.default_person_id
        if person_id is not None and self.session.get(TaskPerson, person_id) is None:
            person_id = None
        todo_rows: list[tuple[str, int, dt.date | None]] = []
        for td in sorted(tt.todos, key=lambda x: (x.sort_order, x.id)):
            ms: dt.date | None = None
            if td.milestone_offset_days is not None:
                ms = shift_business_days(
                    received_date,
                    td.milestone_offset_days,
                    holidays,
                    skip_weekends=True,
                    skip_holidays=True,
                )
            t_title = expand_task_template_placeholders(td.title, received_date) or td.title
            todo_rows.append((t_title.strip(), td.sort_order, ms))
        return TemplateApplySnapshot(
            title=title,
            description=description,
            area_id=area_id,
            person_id=person_id,
            impact=tt.default_impact,
            urgency=tt.default_urgency,
            status=tt.default_status,
            todos=tuple(todo_rows),
        )

    def _resolve_area_id_from_path(self, path: str | None) -> int | None:
        if not path or not isinstance(path, str):
            return None
        parts = [p.strip() for p in path.split("/") if p.strip()]
        if len(parts) != 3:
            return None
        cat_n, sub_n, area_n = parts[0], parts[1], parts[2]
        for cat in self.list_categories():
            if cat.name != cat_n:
                continue
            for sub in cat.subcategories:
                if sub.name != sub_n:
                    continue
                for area in sub.areas:
                    if area.name == area_n:
                        return area.id
        return None

    def export_task_templates(self, path: Path) -> None:
        payload: dict[str, Any] = {"version": 1, "templates": []}
        for tt in self.list_task_templates():
            area_path = _area_label_by_id(self.session, tt.default_area_id)
            emp: str | None = None
            if tt.default_person_id is not None:
                p = self.session.get(TaskPerson, tt.default_person_id)
                if p:
                    emp = p.employee_id
            payload["templates"].append(
                {
                    "name": tt.name,
                    "title_pattern": tt.title_pattern,
                    "description_pattern": tt.description_pattern,
                    "default_impact": tt.default_impact,
                    "default_urgency": tt.default_urgency,
                    "default_status": tt.default_status,
                    "sort_order": tt.sort_order,
                    "area_path": area_path,
                    "person_employee_id": emp,
                    "todos": [
                        {
                            "title": x.title,
                            "sort_order": x.sort_order,
                            "milestone_offset_days": x.milestone_offset_days,
                        }
                        for x in sorted(tt.todos, key=lambda z: (z.sort_order, z.id))
                    ],
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_task_templates(self, path: Path) -> dict[str, int]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Invalid JSON root")
        templates = raw.get("templates", [])
        if not isinstance(templates, list):
            raise ValueError("Invalid templates array")
        created = 0
        updated = 0
        for ent in templates:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name", "")).strip()
            if not name:
                continue
            area_id = self._resolve_area_id_from_path(
                ent.get("area_path") if isinstance(ent.get("area_path"), str) else None
            )
            person_id: int | None = None
            emp = ent.get("person_employee_id")
            if emp is not None and str(emp).strip():
                p = self.session.scalar(
                    select(TaskPerson).where(TaskPerson.employee_id == str(emp).strip())
                )
                if p:
                    person_id = p.id
            todo_specs: list[tuple[str, int, int | None]] = []
            raw_todos = ent.get("todos", [])
            if isinstance(raw_todos, list):
                for i, row in enumerate(raw_todos):
                    if not isinstance(row, dict):
                        continue
                    t_title = str(row.get("title", "")).strip()
                    if not t_title:
                        continue
                    t_order = int(row.get("sort_order", i))
                    off_raw = row.get("milestone_offset_days")
                    if off_raw is None or (isinstance(off_raw, str) and not str(off_raw).strip()):
                        off_i: int | None = None
                    else:
                        off_i = int(off_raw)
                    todo_specs.append((t_title, t_order, off_i))
            title_pattern = str(ent.get("title_pattern", "")).strip()
            if not title_pattern:
                continue
            desc_raw = ent.get("description_pattern")
            desc_s = str(desc_raw) if desc_raw is not None else None
            impact = int(ent.get("default_impact", 2))
            urgency = int(ent.get("default_urgency", 2))
            status = str(ent.get("default_status", TaskStatus.OPEN))
            existing = self.session.scalar(select(TaskTemplate).where(TaskTemplate.name == name))
            if existing:
                upd = self.update_task_template(
                    existing.id,
                    name=name,
                    title_pattern=title_pattern,
                    description_pattern=desc_s,
                    default_area_id=area_id,
                    default_person_id=person_id,
                    default_impact=impact,
                    default_urgency=urgency,
                    default_status=status,
                    todo_specs=todo_specs,
                )
                if upd is not None:
                    updated += 1
            else:
                c = self.create_task_template(
                    name=name,
                    title_pattern=title_pattern,
                    description_pattern=desc_s,
                    default_area_id=area_id,
                    default_person_id=person_id,
                    default_impact=impact,
                    default_urgency=urgency,
                    default_status=status,
                    todo_specs=todo_specs,
                )
                if c is not None:
                    created += 1
        return {"created": created, "updated": updated}

    def taxonomy_selection_for_area(
        self, area_id: int | None
    ) -> tuple[int | None, int | None, int | None]:
        """Return ``(category_id, subcategory_id, area_id)`` for taxonomy combos, or Nones."""
        if area_id is None:
            return None, None, None
        area = self.session.get(
            TaskArea,
            area_id,
            options=[
                joinedload(TaskArea.subcategory).joinedload(TaskSubCategory.category),
            ],
        )
        if area is None:
            return None, None, None
        sub = area.subcategory
        cat = sub.category
        return cat.id, sub.id, area.id
