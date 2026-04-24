"""Minimal task capture dialog (plan 05)."""

from __future__ import annotations

import datetime as dt
import html
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tasktracker.domain.enums import TaskStatus
from tasktracker.services.task_service import TaskService
from tasktracker.ui.date_widgets import date_edit_with_today_button
from tasktracker.ui.spin_widgets import StepInvertedSpinBox


class QuickCaptureDialog(QDialog):
    """Create a task with minimal fields; ``result()`` returns ``(task_id, open_after)``."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        session_factory: Callable[[], Any],
        vault_root: Any,
        ui_settings: dict[str, Any],
        date_format_qt: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quick capture")
        self.setModal(True)
        self._session_factory = session_factory
        self._vault_root = vault_root
        self._result_task_id: int | None = None
        self._open_after = False

        qc = ui_settings.get("quick_capture")
        if not isinstance(qc, dict):
            qc = {}

        root = QVBoxLayout(self)
        hint = QLabel("Title is required. Enter creates with the default button.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        root.addWidget(hint)

        form = QFormLayout()
        self._title = QLineEdit()
        self._title.setPlaceholderText("What needs doing?")
        form.addRow("Title", self._title)

        self._impact = StepInvertedSpinBox()
        self._impact.setRange(1, 3)
        self._impact.setValue(int(qc.get("default_impact", 2)))
        self._urgency = StepInvertedSpinBox()
        self._urgency.setRange(1, 3)
        self._urgency.setValue(int(qc.get("default_urgency", 2)))
        iu = QHBoxLayout()
        iu.addWidget(QLabel("Impact"))
        iu.addWidget(self._impact)
        iu.addWidget(QLabel("Urgency"))
        iu.addWidget(self._urgency)
        iu.addStretch()
        form.addRow("Priority inputs", iu)

        self._area = QComboBox()
        self._area.addItem("— None —", None)
        self._person = QComboBox()
        self._person.addItem("— None —", None)

        session = session_factory()
        try:
            svc = TaskService(session, vault_root)
            for cat in svc.list_categories():
                for sub in cat.subcategories:
                    for area in sub.areas:
                        self._area.addItem(f"{cat.name} / {sub.name} / {area.name}", area.id)
            for p in svc.list_people():
                self._person.addItem(f"{p.last_name}, {p.first_name} ({p.employee_id})", p.id)
            aidx = self._area.findData(qc.get("default_area_id"))
            self._area.setCurrentIndex(aidx if aidx >= 0 else 0)
            pidx = self._person.findData(qc.get("default_person_id"))
            self._person.setCurrentIndex(pidx if pidx >= 0 else 0)
        finally:
            session.close()

        form.addRow("Area", self._area)
        form.addRow("For person", self._person)

        self._desc = QLineEdit()
        self._desc.setPlaceholderText("Optional one-line description")
        form.addRow("Description", self._desc)

        self._more = QWidget()
        more_lay = QFormLayout(self._more)
        recv_row, self._received = date_edit_with_today_button(
            self, display_format=date_format_qt
        )
        self._received.setDate(QDate.currentDate())
        more_lay.addRow("Received", recv_row)
        self._more.setVisible(False)

        self._toggle_more = QToolButton()
        self._toggle_more.setText("More…")
        self._toggle_more.setCheckable(True)
        self._toggle_more.toggled.connect(self._on_more_toggled)

        root.addLayout(form)
        row_more = QHBoxLayout()
        row_more.addWidget(self._toggle_more)
        row_more.addStretch()
        root.addLayout(row_more)
        root.addWidget(self._more)

        bbox = QDialogButtonBox()
        self._btn_create = QPushButton("Create")
        self._btn_create.setDefault(True)
        self._btn_open = QPushButton("Create and open")
        self._btn_cancel = QPushButton("Cancel")
        bbox.addButton(self._btn_create, QDialogButtonBox.ButtonRole.AcceptRole)
        bbox.addButton(self._btn_open, QDialogButtonBox.ButtonRole.ActionRole)
        bbox.addButton(self._btn_cancel, QDialogButtonBox.ButtonRole.RejectRole)
        root.addWidget(bbox)

        self._btn_create.clicked.connect(lambda: self._submit(open_after=False))
        self._btn_open.clicked.connect(lambda: self._submit(open_after=True))
        self._btn_cancel.clicked.connect(self.reject)
        self._title.returnPressed.connect(lambda: self._submit(open_after=False))

    def _on_more_toggled(self, checked: bool) -> None:
        self._more.setVisible(checked)
        self._toggle_more.setText("Fewer…" if checked else "More…")

    def _submit(self, *, open_after: bool) -> None:
        t = self._title.text().strip()
        if not t:
            QMessageBox.warning(self, "Quick capture", "Enter a title.")
            return
        if self._more.isVisible():
            received: dt.date = self._received.date().toPython()
        else:
            received = dt.date.today()
        d_plain = self._desc.text().strip()
        if not d_plain:
            description = None
        else:
            description = f"<p>{html.escape(d_plain)}</p>"
        area_id = self._area.currentData()
        person_id = self._person.currentData()
        session = self._session_factory()
        try:
            svc = TaskService(session, self._vault_root)
            task = svc.create_task(
                title=t,
                received_date=received,
                description=description,
                status=TaskStatus.OPEN,
                impact=self._impact.value(),
                urgency=self._urgency.value(),
                area_id=int(area_id) if area_id is not None else None,
                person_id=int(person_id) if person_id is not None else None,
            )
            self._result_task_id = int(task.id)
            self._open_after = open_after
        finally:
            session.close()
        self.accept()

    def result_payload(self) -> tuple[int, bool] | None:
        if self._result_task_id is None:
            return None
        return self._result_task_id, self._open_after


def run_quick_capture_dialog(
    parent: QWidget | None,
    *,
    session_factory: Callable[[], Any],
    vault_root: Any,
    ui_settings: dict[str, Any],
    date_format_qt: str,
) -> tuple[int, bool] | None:
    dlg = QuickCaptureDialog(
        parent,
        session_factory=session_factory,
        vault_root=vault_root,
        ui_settings=ui_settings,
        date_format_qt=date_format_qt,
    )
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return dlg.result_payload()
