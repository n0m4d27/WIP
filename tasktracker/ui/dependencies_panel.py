from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tasktracker.db.models import TaskDependency


class DependenciesPanel(QGroupBox):
    jump_to_task_requested = Signal(int)
    add_requested = Signal()
    remove_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Dependencies", parent)
        root = QVBoxLayout(self)

        row_lists = QHBoxLayout()
        up_box = QVBoxLayout()
        up_box.addWidget(QLabel("Blocked by"))
        self._up = QListWidget()
        up_box.addWidget(self._up)
        row_lists.addLayout(up_box, 1)

        dn_box = QVBoxLayout()
        dn_box.addWidget(QLabel("Blocking"))
        self._down = QListWidget()
        dn_box.addWidget(self._down)
        row_lists.addLayout(dn_box, 1)
        root.addLayout(row_lists, 1)

        row_btn = QHBoxLayout()
        self._btn_add = QPushButton("Add link…")
        self._btn_add.clicked.connect(self.add_requested.emit)
        row_btn.addWidget(self._btn_add)
        self._btn_remove = QPushButton("Remove selected")
        self._btn_remove.clicked.connect(self._emit_remove)
        row_btn.addWidget(self._btn_remove)
        self._btn_jump = QPushButton("Jump to task")
        self._btn_jump.clicked.connect(self._emit_jump)
        row_btn.addWidget(self._btn_jump)
        row_btn.addStretch(1)
        root.addLayout(row_btn)

    def set_data(self, upstream: Iterable[TaskDependency], downstream: Iterable[TaskDependency]) -> None:
        self._up.clear()
        self._down.clear()
        for dep in upstream:
            t = dep.blocker_task
            label = f"{t.ticket_number if t else '?'}  {t.title if t else '(missing)'}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, dep.id)
            it.setData(Qt.ItemDataRole.UserRole + 1, dep.blocker_task_id)
            self._up.addItem(it)
        for dep in downstream:
            t = dep.blocked_task
            label = f"{t.ticket_number if t else '?'}  {t.title if t else '(missing)'}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, dep.id)
            it.setData(Qt.ItemDataRole.UserRole + 1, dep.blocked_task_id)
            self._down.addItem(it)

    def _current_item(self) -> QListWidgetItem | None:
        return self._up.currentItem() or self._down.currentItem()

    def _emit_remove(self) -> None:
        it = self._current_item()
        if it is None:
            return
        dep_id = it.data(Qt.ItemDataRole.UserRole)
        if dep_id is not None:
            self.remove_requested.emit(int(dep_id))

    def _emit_jump(self) -> None:
        it = self._current_item()
        if it is None:
            return
        task_id = it.data(Qt.ItemDataRole.UserRole + 1)
        if task_id is not None:
            self.jump_to_task_requested.emit(int(task_id))
