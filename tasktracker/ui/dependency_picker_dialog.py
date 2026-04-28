from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tasktracker.domain.ticket import format_task_ticket


@dataclass(frozen=True)
class DependencyCandidate:
    task_id: int
    ticket_number: int | None
    title: str
    status: str


def candidate_matches_query(candidate: DependencyCandidate, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    ticket = format_task_ticket(candidate.ticket_number).lower()
    return q in candidate.title.lower() or q in ticket or q in candidate.status.lower()


class DependencyPickerDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        candidates: Iterable[DependencyCandidate],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add dependency")
        self.resize(720, 480)
        self._all = sorted(
            list(candidates),
            key=lambda c: (
                1 if c.ticket_number is None else 0,
                c.ticket_number if c.ticket_number is not None else 0,
                c.title.lower(),
            ),
        )

        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Search"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type task number (e.g. T42), title, or status…")
        self.search.textChanged.connect(self._refresh)
        row.addWidget(self.search, 1)
        root.addLayout(row)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _it: self.accept())
        root.addWidget(self.list, 1)

        self.meta = QLabel("")
        root.addWidget(self.meta)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self._refresh()

    def _refresh(self) -> None:
        q = self.search.text()
        self.list.clear()
        rows = [c for c in self._all if candidate_matches_query(c, q)]
        for c in rows:
            label = f"{format_task_ticket(c.ticket_number)}  {c.title}  ({c.status})"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, c.task_id)
            self.list.addItem(it)
        if rows:
            self.list.setCurrentRow(0)
            self.meta.setText(f"{len(rows)} matches")
        else:
            self.meta.setText("No matching open tasks.")

    def selected_task_id(self) -> int | None:
        it = self.list.currentItem()
        if it is None:
            return None
        raw = it.data(Qt.ItemDataRole.UserRole)
        return int(raw) if raw is not None else None


def run_dependency_picker_dialog(
    parent: QWidget | None, *, candidates: Iterable[DependencyCandidate]
) -> int | None:
    dlg = DependencyPickerDialog(parent, candidates=candidates)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return dlg.selected_task_id()
