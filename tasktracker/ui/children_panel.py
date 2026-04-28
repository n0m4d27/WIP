from __future__ import annotations

import datetime as dt
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tasktracker.db.models import Task
from tasktracker.domain.priority import priority_display
from tasktracker.domain.ticket import format_task_ticket


class ChildrenPanel(QGroupBox):
    jump_to_task_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Children", parent)
        root = QVBoxLayout(self)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Task", "Status", "Due", "Priority", "Done"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.itemDoubleClicked.connect(self._emit_jump)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, hdr.ResizeMode.Stretch)
        root.addWidget(self._table, 1)

        row = QHBoxLayout()
        self._btn_jump = QPushButton("Jump to child")
        self._btn_jump.clicked.connect(self._emit_jump)
        row.addWidget(self._btn_jump)
        row.addStretch(1)
        root.addLayout(row)

    def set_children(self, children: Iterable[Task]) -> None:
        rows = list(children)
        self._table.setRowCount(len(rows))
        for r, child in enumerate(rows):
            self._set_item(r, 0, f"{format_task_ticket(child.ticket_number)}  {child.title}", child.id)
            self._set_item(r, 1, child.status)
            due = child.due_date.isoformat() if isinstance(child.due_date, dt.date) else ""
            self._set_item(r, 2, due)
            self._set_item(r, 3, priority_display(child.priority))
            done = "Yes" if child.status == "closed" else ""
            self._set_item(r, 4, done)

    def _set_item(self, row: int, col: int, text: str, task_id: int | None = None) -> None:
        item = QTableWidgetItem(text)
        if task_id is not None:
            item.setData(Qt.ItemDataRole.UserRole, task_id)
        self._table.setItem(row, col, item)

    def _emit_jump(self, *_args: object) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if task_id is not None:
            self.jump_to_task_requested.emit(int(task_id))
