from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Monotonic display id per database (T0, T1, …). Distinct from row id for stable user-facing references.
    ticket_number: Mapped[int | None] = mapped_column(Integer, unique=True, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    impact: Mapped[int] = mapped_column(Integer, nullable=False, default=2)  # 1–3
    urgency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)  # 1–5 computed

    received_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    closed_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    next_milestone_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    todos: Mapped[list["TodoItem"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TodoItem.sort_order"
    )
    notes: Mapped[list["TaskNote"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskNote.created_at"
    )
    blockers: Mapped[list["TaskBlocker"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    update_logs: Mapped[list["TaskUpdateLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskUpdateLog.changed_at"
    )
    recurring_rule: Mapped["RecurringRule | None"] = relationship(
        back_populates="task", cascade="all, delete-orphan", uselist=False
    )


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    milestone_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="todos")


class TaskNote(Base):
    __tablename__ = "task_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    versions: Mapped[list["TaskNoteVersion"]] = relationship(
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="TaskNoteVersion.version_seq",
    )

    task: Mapped["Task"] = relationship(back_populates="notes")


class TaskNoteVersion(Base):
    __tablename__ = "task_note_versions"
    __table_args__ = (UniqueConstraint("note_id", "version_seq", name="uq_note_version_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("task_notes.id", ondelete="CASCADE"), index=True)
    version_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    note: Mapped["TaskNote"] = relationship(back_populates="versions")


class TaskBlocker(Base):
    __tablename__ = "task_blockers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribution: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raised_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cleared_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="blockers")


class TaskUpdateLog(Base):
    __tablename__ = "task_update_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    task: Mapped["Task"] = relationship(back_populates="update_logs")


class RecurringRule(Base):
    __tablename__ = "recurring_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), unique=True, index=True
    )
    generation_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="on_close")
    skip_weekends: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    skip_holidays: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    task: Mapped["Task"] = relationship(back_populates="recurring_rule")
    todo_templates: Mapped[list["RecurringTodoTemplate"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan", order_by="RecurringTodoTemplate.sort_order"
    )


class RecurringTodoTemplate(Base):
    __tablename__ = "recurring_todo_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("recurring_rules.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    milestone_offset_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    rule: Mapped["RecurringRule"] = relationship(back_populates="todo_templates")


class BusinessHoliday(Base):
    __tablename__ = "business_holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    holiday_date: Mapped[dt.date] = mapped_column(Date, nullable=False, unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
