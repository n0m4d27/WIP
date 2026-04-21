"""Dialog: Customize task panel layout (section order).

Sections on the Tasks tab live in two containers: a stacked "Inline" column
below the core fields, and a shared "Tabs" pane for heavier content (Notes,
Activity). Each container's order is reordered independently here; on accept
the two lists are concatenated into a single list of section ids that the
caller persists via ``normalize_section_order``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from tasktracker.ui.settings_store import (
    TASK_SECTION_IDS,
    TASK_SECTION_LABELS,
    TASK_SECTION_PLACEMENT,
)


def _build_group(title: str, section_ids: list[str]) -> tuple[QGroupBox, QListWidget]:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)

    lw = QListWidget()
    for sid in section_ids:
        if sid in TASK_SECTION_LABELS:
            it = QListWidgetItem(TASK_SECTION_LABELS[sid])
            it.setData(Qt.ItemDataRole.UserRole, sid)
            lw.addItem(it)
    lay.addWidget(lw)

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
    lay.addLayout(btn_row)

    return box, lw


def _collect_order(lw: QListWidget) -> list[str]:
    out: list[str] = []
    for i in range(lw.count()):
        it = lw.item(i)
        sid = it.data(Qt.ItemDataRole.UserRole)
        if sid:
            out.append(str(sid))
    return out


def run_task_panel_layout_dialog(parent, current_order: list[str]) -> list[str] | None:
    """Return new section id order, or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Customize task panel layout")
    d.resize(520, 420)

    root = QVBoxLayout(d)
    intro = QLabel(
        "Rearrange how sections appear on the Tasks tab. "
        "<b>Inline sections</b> stack below the core fields. "
        "<b>Tabbed sections</b> share a tab strip for heavier content "
        "(notes, activity) so long lists do not push everything else off-screen."
    )
    intro.setWordWrap(True)
    intro.setTextFormat(Qt.TextFormat.RichText)
    root.addWidget(intro)

    inline_ids = [s for s in current_order if TASK_SECTION_PLACEMENT.get(s) == "inline"]
    tab_ids = [s for s in current_order if TASK_SECTION_PLACEMENT.get(s) == "tab"]
    for sid in TASK_SECTION_IDS:
        if sid in inline_ids or sid in tab_ids:
            continue
        if TASK_SECTION_PLACEMENT.get(sid) == "tab":
            tab_ids.append(sid)
        else:
            inline_ids.append(sid)

    columns = QHBoxLayout()
    inline_box, inline_lw = _build_group("Inline sections", inline_ids)
    tabs_box, tabs_lw = _build_group("Tabs", tab_ids)
    columns.addWidget(inline_box, 1)
    columns.addWidget(tabs_box, 1)
    root.addLayout(columns)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    root.addWidget(bb)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None

    new_order = _collect_order(inline_lw) + _collect_order(tabs_lw)
    seen = set(new_order)
    for sid in TASK_SECTION_IDS:
        if sid not in seen:
            new_order.append(sid)
    return new_order
