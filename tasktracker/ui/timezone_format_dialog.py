"""Settings dialog: pick timezone for activity and note timestamps."""

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

from tasktracker.ui.date_format import DISPLAY_TIMEZONE_LOCAL, format_activity_timestamp
from tasktracker.ui.settings_store import DEFAULT_DISPLAY_TIMEZONE

_OTHER = "__other__"

# (label, stored key). ``local`` follows the computer's current zone.
DISPLAY_TIMEZONE_PRESETS: tuple[tuple[str, str], ...] = (
    ("Use system timezone", DISPLAY_TIMEZONE_LOCAL),
    ("UTC", "UTC"),
    ("America/New_York (US Eastern)", "America/New_York"),
    ("America/Chicago (US Central)", "America/Chicago"),
    ("America/Denver (US Mountain)", "America/Denver"),
    ("America/Los_Angeles (US Pacific)", "America/Los_Angeles"),
    ("Europe/London", "Europe/London"),
    ("Europe/Paris", "Europe/Paris"),
    ("Asia/Tokyo", "Asia/Tokyo"),
    ("Australia/Sydney", "Australia/Sydney"),
)


def run_display_timezone_dialog(parent, current: str | None) -> str | None:
    """Return the chosen timezone key, or ``None`` if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Display timezone")
    d.resize(560, 260)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Choose how timestamps are shown in the task <b>Activity</b> panel and "
        "in calendar quick-edit note previews. Task dates and exports are "
        "unchanged (exports stay ISO / UTC)."
    )
    intro.setWordWrap(True)
    intro.setTextFormat(Qt.TextFormat.RichText)
    root.addWidget(intro)

    form = QFormLayout()
    preset = QComboBox()
    for label, key in DISPLAY_TIMEZONE_PRESETS:
        preset.addItem(label, key)
    preset.addItem("Other (IANA name)…", _OTHER)
    form.addRow("Preset:", preset)

    custom_row = QHBoxLayout()
    custom_edit = QLineEdit()
    custom_edit.setPlaceholderText("e.g. America/Phoenix")
    custom_edit.setEnabled(False)
    custom_row.addWidget(custom_edit, 1)
    form.addRow("Custom zone:", custom_row)

    preview = QLabel()
    preview.setTextFormat(Qt.TextFormat.RichText)
    form.addRow("Preview (now):", preview)
    root.addLayout(form)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    def _effective_key() -> str:
        data = preset.currentData()
        if data == _OTHER:
            return custom_edit.text().strip() or DEFAULT_DISPLAY_TIMEZONE
        return str(data)

    def _refresh_preview() -> None:
        key = _effective_key()
        sample = format_activity_timestamp(dt.datetime.now(dt.UTC), key)
        preview.setText(f"<b>{sample}</b> &nbsp; <i>({key})</i>")

    def _on_preset_changed(_idx: int) -> None:
        is_other = preset.currentData() == _OTHER
        custom_edit.setEnabled(is_other)
        _refresh_preview()

    preset.currentIndexChanged.connect(_on_preset_changed)
    custom_edit.textChanged.connect(lambda _t: _refresh_preview())

    cur = (current or DEFAULT_DISPLAY_TIMEZONE).strip() or DEFAULT_DISPLAY_TIMEZONE
    idx = next((i for i in range(preset.count()) if preset.itemData(i) == cur), None)
    if idx is not None:
        preset.setCurrentIndex(idx)
    else:
        preset.setCurrentIndex(len(DISPLAY_TIMEZONE_PRESETS))
        custom_edit.setText(cur)
    _on_preset_changed(preset.currentIndex())

    if d.exec() != QDialog.DialogCode.Accepted:
        return None

    chosen = _effective_key()
    if chosen != DISPLAY_TIMEZONE_LOCAL and not is_valid_iana_timezone(chosen):
        return DEFAULT_DISPLAY_TIMEZONE
    return chosen
