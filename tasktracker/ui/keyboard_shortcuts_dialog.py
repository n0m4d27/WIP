"""Dialog: customize main window keyboard shortcuts."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from tasktracker.ui.settings_store import DEFAULT_SHORTCUTS


def run_keyboard_shortcuts_dialog(parent, current: dict[str, str]) -> dict[str, str] | None:
    """Return merged shortcut map, or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Keyboard shortcuts")
    d.resize(480, 200)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Set shortcuts for task commands. Conflicts between these three are not allowed. "
        "Defaults: New Task Ctrl+N, Save Task Ctrl+S, Close Task Ctrl+Shift+C."
    )
    intro.setWordWrap(True)
    root.addWidget(intro)

    form = QFormLayout()
    keys = dict(DEFAULT_SHORTCUTS)
    keys.update({k: v for k, v in current.items() if k in DEFAULT_SHORTCUTS})

    ed_new = QKeySequenceEdit(QKeySequence(keys["new_task"]))
    ed_save = QKeySequenceEdit(QKeySequence(keys["save_task"]))
    ed_close = QKeySequenceEdit(QKeySequence(keys["close_task"]))

    form.addRow("New Task", ed_new)
    form.addRow("Save Task", ed_save)
    form.addRow("Close Task", ed_close)
    root.addLayout(form)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None

    def seq_str(edit: QKeySequenceEdit) -> str:
        qs = edit.keySequence()
        if qs.isEmpty():
            return ""
        return qs.toString(QKeySequence.SequenceFormat.PortableText)

    out = {
        "new_task": seq_str(ed_new),
        "save_task": seq_str(ed_save),
        "close_task": seq_str(ed_close),
    }
    for k, v in out.items():
        if not v.strip():
            QMessageBox.warning(d, "Shortcuts", f"Shortcut for {k} cannot be empty.")
            return None

    seqs = list(out.values())
    if len(set(seqs)) != len(seqs):
        QMessageBox.warning(
            d,
            "Shortcuts",
            "Two or more actions use the same shortcut. Choose distinct shortcuts.",
        )
        return None

    return out
