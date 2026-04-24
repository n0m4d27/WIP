"""Dialog: customize main window keyboard shortcuts and quick-capture options."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from tasktracker.ui.settings_store import DEFAULT_QUICK_CAPTURE, DEFAULT_SHORTCUTS

if TYPE_CHECKING:
    from tasktracker.services.task_service import TaskService


def run_keyboard_shortcuts_dialog(
    parent,
    settings: dict[str, Any],
    svc: TaskService | None = None,
) -> bool:
    """Edit ``settings['shortcuts']`` and ``settings['quick_capture']`` in place.

    Returns ``True`` if the user accepted and values were validated.
    """
    d = QDialog(parent)
    d.setWindowTitle("Keyboard shortcuts")
    d.resize(520, 420)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Task command shortcuts apply when the main window has focus. "
        "The quick-capture hotkey is registered system-wide on Windows when the app is running."
    )
    intro.setWordWrap(True)
    root.addWidget(intro)

    form = QFormLayout()
    keys = dict(DEFAULT_SHORTCUTS)
    shortcuts = settings.get("shortcuts") if isinstance(settings.get("shortcuts"), dict) else {}
    keys.update({k: v for k, v in shortcuts.items() if k in DEFAULT_SHORTCUTS})

    ed_new = QKeySequenceEdit(QKeySequence(keys["new_task"]))
    ed_save = QKeySequenceEdit(QKeySequence(keys["save_task"]))
    ed_close = QKeySequenceEdit(QKeySequence(keys["close_task"]))

    form.addRow("New Task", ed_new)
    form.addRow("Save Task", ed_save)
    form.addRow("Close Task", ed_close)
    root.addLayout(form)

    qc = (
        dict(DEFAULT_QUICK_CAPTURE)
        if not isinstance(settings.get("quick_capture"), dict)
        else _merge_qc_defaults(settings["quick_capture"])
    )

    qc_box = QGroupBox("Quick capture")
    qc_form = QFormLayout(qc_box)
    ed_qc_hotkey = QKeySequenceEdit(QKeySequence(qc["hotkey"]))
    qc_form.addRow("Global hotkey (Windows)", ed_qc_hotkey)
    chk_tray = QCheckBox("Keep running in system tray when the main window is closed")
    chk_tray.setChecked(bool(qc["keep_running_in_tray"]))
    chk_tray.setToolTip(
        "When checked, closing the main window hides it instead of locking the vault. "
        "Use the tray icon to capture tasks, reopen the window, or exit completely."
    )
    qc_form.addRow(chk_tray)
    chk_click = QCheckBox("Tray icon click opens quick capture (otherwise opens main window)")
    chk_click.setChecked(bool(qc["tray_click_opens_capture"]))
    qc_form.addRow(chk_click)

    sp_imp = QSpinBox()
    sp_imp.setRange(1, 3)
    sp_imp.setValue(int(qc["default_impact"]))
    sp_urg = QSpinBox()
    sp_urg.setRange(1, 3)
    sp_urg.setValue(int(qc["default_urgency"]))
    qc_form.addRow("Default impact (capture dialog)", sp_imp)
    qc_form.addRow("Default urgency (capture dialog)", sp_urg)

    cb_area = QComboBox()
    cb_area.addItem("— None —", None)
    cb_person = QComboBox()
    cb_person.addItem("— None —", None)
    if svc is not None:
        for cat in svc.list_categories():
            for sub in cat.subcategories:
                for area in sub.areas:
                    cb_area.addItem(f"{cat.name} / {sub.name} / {area.name}", area.id)
        for p in svc.list_people():
            cb_person.addItem(f"{p.last_name}, {p.first_name} ({p.employee_id})", p.id)
        aidx = cb_area.findData(qc.get("default_area_id"))
        cb_area.setCurrentIndex(aidx if aidx >= 0 else 0)
        pidx = cb_person.findData(qc.get("default_person_id"))
        cb_person.setCurrentIndex(pidx if pidx >= 0 else 0)
    qc_form.addRow("Default area", cb_area)
    qc_form.addRow("Default for-person", cb_person)

    root.addWidget(qc_box)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    if d.exec() != QDialog.DialogCode.Accepted:
        return False

    def seq_str(edit: QKeySequenceEdit) -> str:
        qs = edit.keySequence()
        if qs.isEmpty():
            return ""
        return qs.toString(QKeySequence.SequenceFormat.PortableText)

    out_sc = {
        "new_task": seq_str(ed_new),
        "save_task": seq_str(ed_save),
        "close_task": seq_str(ed_close),
    }
    for k, v in out_sc.items():
        if not v.strip():
            QMessageBox.warning(d, "Shortcuts", f"Shortcut for {k} cannot be empty.")
            return False

    seqs = list(out_sc.values())
    if len(set(seqs)) != len(seqs):
        QMessageBox.warning(
            d,
            "Shortcuts",
            "Two or more task actions use the same shortcut. Choose distinct shortcuts.",
        )
        return False

    qc_hot = seq_str(ed_qc_hotkey)
    if not qc_hot.strip():
        QMessageBox.warning(d, "Shortcuts", "Quick capture hotkey cannot be empty.")
        return False
    if qc_hot in seqs:
        QMessageBox.warning(
            d,
            "Shortcuts",
            "Quick capture hotkey must differ from New/Save/Close task shortcuts.",
        )
        return False

    settings["shortcuts"] = out_sc
    settings["quick_capture"] = {
        "hotkey": qc_hot,
        "keep_running_in_tray": chk_tray.isChecked(),
        "tray_click_opens_capture": chk_click.isChecked(),
        "default_impact": sp_imp.value(),
        "default_urgency": sp_urg.value(),
        "default_area_id": cb_area.currentData(),
        "default_person_id": cb_person.currentData(),
    }
    return True


def _merge_qc_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_QUICK_CAPTURE)
    merged.update(raw)
    return merged
