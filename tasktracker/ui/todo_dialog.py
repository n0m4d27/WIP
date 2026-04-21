"""Dialog to add or edit a todo with title and optional milestone date."""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from tasktracker.ui.date_format import format_from_parent
from tasktracker.ui.date_widgets import date_edit_with_today_button


def _qdate_to_py(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


def _py_to_qdate(d: dt.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def run_add_todo_dialog(
    parent=None,
    *,
    initial_title: str = "",
    initial_milestone: dt.date | None = None,
    window_title: str = "Add todo",
) -> tuple[str, dt.date | None] | None:
    """Return ``(title, milestone_date_or_None)`` or ``None`` if cancelled.

    Pass ``initial_title`` / ``initial_milestone`` to pre-fill the form when
    editing an existing todo; in that case the milestone checkbox reflects
    whether a milestone is currently set (unchecked means "no milestone"
    and the date field is disabled).
    """
    d = QDialog(parent)
    d.setWindowTitle(window_title)
    d.setMinimumWidth(400)

    title = QLineEdit()
    title.setText(initial_title)
    has_ms = QCheckBox("Milestone date")
    has_ms.setChecked(initial_milestone is not None)
    ms_row, ms_date = date_edit_with_today_button(d, display_format=format_from_parent(parent))
    ms_date.setDate(
        _py_to_qdate(initial_milestone) if initial_milestone is not None else QDate.currentDate()
    )
    ms_row.setEnabled(has_ms.isChecked())

    def toggle_ms(checked: bool) -> None:
        ms_row.setEnabled(checked)

    has_ms.toggled.connect(toggle_ms)

    form = QFormLayout()
    form.addRow("Title", title)
    form.addRow("", has_ms)
    form.addRow("Milestone", ms_row)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)

    root = QVBoxLayout(d)
    root.addLayout(form)
    root.addWidget(bb)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    t = title.text().strip()
    if not t:
        return None
    ms: dt.date | None = _qdate_to_py(ms_date.date()) if has_ms.isChecked() else None
    return (t, ms)


def run_edit_todo_dialog(
    parent,
    *,
    current_title: str,
    current_milestone: dt.date | None,
) -> tuple[str, dt.date | None] | None:
    """Pre-filled variant of :func:`run_add_todo_dialog` for editing a todo."""
    return run_add_todo_dialog(
        parent,
        initial_title=current_title,
        initial_milestone=current_milestone,
        window_title="Edit todo",
    )
