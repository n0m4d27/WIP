"""Dialog to add a todo with title and optional milestone date."""

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

from tasktracker.ui.date_widgets import date_edit_with_today_button


def _qdate_to_py(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


def run_add_todo_dialog(parent=None) -> tuple[str, dt.date | None] | None:
    """Return ``(title, milestone_date_or_None)`` or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Add todo")
    d.setMinimumWidth(400)

    title = QLineEdit()
    has_ms = QCheckBox("Milestone date")
    has_ms.setChecked(True)
    ms_row, ms_date = date_edit_with_today_button(d)
    ms_date.setDate(QDate.currentDate())

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
