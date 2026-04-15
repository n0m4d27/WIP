"""Dialog: Customize task panel layout (section order)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from tasktracker.ui.settings_store import TASK_SECTION_IDS, TASK_SECTION_LABELS


def run_task_panel_layout_dialog(parent, current_order: list[str]) -> list[str] | None:
    """Return new section id order, or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Customize task panel layout")
    d.resize(420, 320)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Choose the order of sections below the core task fields (ticket, title, dates, etc.). "
        "Use Move up / Move down."
    )
    intro.setWordWrap(True)
    root.addWidget(intro)

    lw = QListWidget()
    order = list(current_order)
    for sid in order:
        if sid in TASK_SECTION_LABELS:
            it = QListWidgetItem(TASK_SECTION_LABELS[sid])
            it.setData(Qt.ItemDataRole.UserRole, sid)
            lw.addItem(it)
    root.addWidget(lw)

    btn_row = QHBoxLayout()
    up = QPushButton("Move up")
    dn = QPushButton("Move down")

    def move(delta: int) -> None:
        row = lw.currentRow()
        if row < 0:
            return
        nr = row + delta
        if nr < 0 or nr >= lw.count():
            return
        item = lw.takeItem(row)
        lw.insertItem(nr, item)
        lw.setCurrentRow(nr)

    up.clicked.connect(lambda: move(-1))
    dn.clicked.connect(lambda: move(1))
    btn_row.addWidget(up)
    btn_row.addWidget(dn)
    btn_row.addStretch()
    root.addLayout(btn_row)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None

    new_order: list[str] = []
    for i in range(lw.count()):
        it = lw.item(i)
        sid = it.data(Qt.ItemDataRole.UserRole)
        if sid:
            new_order.append(str(sid))
    # Ensure complete
    seen = set(new_order)
    for sid in TASK_SECTION_IDS:
        if sid not in seen:
            new_order.append(sid)
    return new_order
