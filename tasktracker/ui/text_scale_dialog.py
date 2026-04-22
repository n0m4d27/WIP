"""Settings dialog: interface text size (application font scale)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from tasktracker.ui.settings_store import (
    MAX_UI_TEXT_SCALE,
    MIN_UI_TEXT_SCALE,
    coerce_ui_text_scale,
)


def run_text_scale_dialog(parent, current: float) -> float | None:
    """Return chosen scale, or ``None`` if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Text size")
    d.resize(440, 200)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Scale all interface text relative to the default size. "
        "Applies after the color theme; switching theme keeps this scale."
    )
    intro.setWordWrap(True)
    root.addWidget(intro)

    form = QFormLayout()
    preset = QComboBox()
    presets: list[tuple[str, float | None]] = [
        ("90%", 0.9),
        ("100% (default)", 1.0),
        ("110%", 1.1),
        ("125%", 1.25),
        ("150%", 1.5),
        ("Custom (below)", None),
    ]
    for label, val in presets:
        preset.addItem(label, val)

    spin = QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setRange(MIN_UI_TEXT_SCALE, MAX_UI_TEXT_SCALE)
    spin.setSingleStep(0.05)
    cur = coerce_ui_text_scale(current)
    spin.setValue(cur)

    def _sync_preset_index() -> None:
        v = spin.value()
        idx = next(
            (i for i in range(preset.count()) if preset.itemData(i) is not None and abs(float(preset.itemData(i)) - v) < 0.001),
            None,
        )
        if idx is not None:
            preset.blockSignals(True)
            preset.setCurrentIndex(idx)
            preset.blockSignals(False)
        else:
            preset.blockSignals(True)
            preset.setCurrentIndex(len(presets) - 1)
            preset.blockSignals(False)

    def _on_preset(_i: int) -> None:
        data = preset.currentData()
        if data is not None:
            spin.setValue(float(data))

    def _on_spin(_v: float) -> None:
        _sync_preset_index()

    preset.currentIndexChanged.connect(_on_preset)
    spin.valueChanged.connect(_on_spin)
    _sync_preset_index()

    form.addRow("Preset:", preset)
    form.addRow("Scale:", spin)
    root.addLayout(form)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return coerce_ui_text_scale(spin.value())
