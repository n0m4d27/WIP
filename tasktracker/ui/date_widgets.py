"""Reusable date controls with Today / Clear shortcuts."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QHBoxLayout, QPushButton, QWidget

from tasktracker.ui.settings_store import DEFAULT_DATE_FORMAT


def date_edit_with_today_button(
    parent=None,
    *,
    clearable: bool = False,
    blank_text: str = "",
    display_format: str | None = None,
) -> tuple[QWidget, QDateEdit]:
    """Return a row widget and the ``QDateEdit`` (calendar popup enabled).

    When ``clearable`` is True the field supports an explicit "no date" state:
    its value sits at ``minimumDate()`` and is rendered as ``blank_text``
    (empty by default) via ``specialValueText``. A "Clear" button is added
    next to "Today" so the user can re-empty the field after picking a date.
    Use :func:`qdate_is_blank` to test whether the field currently holds the
    blank sentinel.

    ``display_format`` is a Qt display-format string (e.g. ``"yyyy-MM-dd"``).
    When ``None`` the default ISO format is used; callers that want to honour
    the user's Settings choice should pass ``get_date_format_qt(ui_settings)``
    explicitly, since this helper lives below the UI layer and doesn't read
    from settings itself.
    """
    row = QWidget(parent)
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    de = QDateEdit()
    de.setCalendarPopup(True)
    de.setDisplayFormat(display_format or DEFAULT_DATE_FORMAT)
    if clearable:
        de.setSpecialValueText(blank_text)
        de.setDate(de.minimumDate())
    lay.addWidget(de, 1)
    btn_today = QPushButton("Today")
    btn_today.setToolTip("Set date to today")
    btn_today.clicked.connect(lambda: de.setDate(QDate.currentDate()))
    lay.addWidget(btn_today)
    if clearable:
        btn_clear = QPushButton("Clear")
        btn_clear.setToolTip("Clear the date")
        btn_clear.clicked.connect(lambda: de.setDate(de.minimumDate()))
        lay.addWidget(btn_clear)
    return row, de


def qdate_is_blank(de: QDateEdit) -> bool:
    """True when a clearable date edit is in its "no date" state."""
    return de.date() == de.minimumDate()
