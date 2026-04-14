"""Reusable date controls with a Today shortcut."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QPushButton, QWidget


def date_edit_with_today_button(parent=None) -> tuple[QWidget, QDateEdit]:
    """Return a row widget and the ``QDateEdit`` (calendar popup enabled)."""
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    de = QDateEdit()
    de.setCalendarPopup(True)
    lay.addWidget(de, 1)
    btn = QPushButton("Today")
    btn.setToolTip("Set date to today")
    btn.clicked.connect(lambda: de.setDate(QDate.currentDate()))
    lay.addWidget(btn)
    return row, de
