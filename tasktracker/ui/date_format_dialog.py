"""Settings dialog: pick the Qt date display format.

Presents the curated :data:`DATE_FORMAT_PRESETS` in a combo plus a
"Custom…" option that reveals a free-text line edit for power users
who already know Qt's ``QDateEdit`` pattern syntax. A live preview line
shows today's date rendered in the currently-selected format so the
user can see the effect before committing.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from tasktracker.ui.date_format import (
    DATE_FORMAT_PRESETS,
    format_date,
)
from tasktracker.ui.settings_store import DEFAULT_DATE_FORMAT


_CUSTOM_SENTINEL = "__custom__"


def run_date_format_dialog(parent, current: str | None) -> str | None:
    """Return the chosen Qt format string, or ``None`` if cancelled.

    ``current`` pre-selects the matching preset. A value that doesn't
    match any preset pre-selects Custom with the value loaded into the
    free-text field.
    """
    d = QDialog(parent)
    d.setWindowTitle("Date format")
    d.resize(520, 220)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Choose how dates are displayed in pickers, the Reports tab, "
        "the status bar, and other UI labels. Exports (CSV / Excel) "
        "always use ISO <code>yyyy-MM-dd</code> regardless of this "
        "setting so spreadsheets sort correctly."
    )
    intro.setWordWrap(True)
    intro.setTextFormat(Qt.TextFormat.RichText)
    root.addWidget(intro)

    form = QFormLayout()

    preset = QComboBox()
    for p in DATE_FORMAT_PRESETS:
        preset.addItem(p.label, p.qt_format)
    preset.addItem("Custom…", _CUSTOM_SENTINEL)
    form.addRow("Preset:", preset)

    custom_row = QHBoxLayout()
    custom_edit = QLineEdit()
    custom_edit.setPlaceholderText("e.g. yyyy/MM/dd or d MMM yyyy")
    custom_edit.setEnabled(False)
    custom_row.addWidget(custom_edit, 1)
    form.addRow("Custom format:", custom_row)

    preview = QLabel()
    preview.setTextFormat(Qt.TextFormat.RichText)
    form.addRow("Preview:", preview)

    root.addLayout(form)

    help_lbl = QLabel(
        "Tokens: <code>yyyy</code> / <code>yy</code> year, "
        "<code>MM</code> month, <code>MMM</code> short month name, "
        "<code>MMMM</code> full month name, <code>dd</code> day, "
        "<code>ddd</code> / <code>dddd</code> weekday."
    )
    help_lbl.setTextFormat(Qt.TextFormat.RichText)
    help_lbl.setWordWrap(True)
    root.addWidget(help_lbl)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    today = dt.date.today()

    def _current_format() -> str:
        data = preset.currentData()
        if data == _CUSTOM_SENTINEL:
            return custom_edit.text().strip() or DEFAULT_DATE_FORMAT
        return str(data)

    def _refresh_preview() -> None:
        fmt = _current_format()
        rendered = format_date(today, fmt)
        preview.setText(f"<b>{rendered}</b> &nbsp; <i>({fmt})</i>")

    def _on_preset_changed(_idx: int) -> None:
        is_custom = preset.currentData() == _CUSTOM_SENTINEL
        custom_edit.setEnabled(is_custom)
        _refresh_preview()

    preset.currentIndexChanged.connect(_on_preset_changed)
    custom_edit.textChanged.connect(lambda _t: _refresh_preview())

    # Pre-select based on ``current``.
    current_fmt = (current or DEFAULT_DATE_FORMAT).strip() or DEFAULT_DATE_FORMAT
    preset_idx = next(
        (i for i, p in enumerate(DATE_FORMAT_PRESETS) if p.qt_format == current_fmt),
        None,
    )
    if preset_idx is not None:
        preset.setCurrentIndex(preset_idx)
    else:
        # Select the Custom row and load the user's stored format.
        preset.setCurrentIndex(len(DATE_FORMAT_PRESETS))
        custom_edit.setText(current_fmt)
    _on_preset_changed(preset.currentIndex())

    if d.exec() != QDialog.DialogCode.Accepted:
        return None

    chosen = _current_format()
    # A custom entry that collapsed to empty after strip falls back to
    # the default so the user doesn't end up with an invisible format.
    if not chosen.strip():
        return DEFAULT_DATE_FORMAT
    return chosen
