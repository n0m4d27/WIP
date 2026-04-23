"""Settings dialog for vault task templates (plan 03)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tasktracker.db.models import TaskTemplate
from tasktracker.domain.enums import TaskStatus
from tasktracker.services.task_service import TaskService
from tasktracker.ui.date_widgets import date_edit_with_today_button, qdate_is_blank
from tasktracker.ui.settings_store import get_date_format_qt


def _qdate_to_py(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


def _parse_todo_template_lines(text: str) -> list[tuple[str, int, int | None]]:
    specs: list[tuple[str, int, int | None]] = []
    order = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            tit, _, rest = line.partition("|")
            tit = tit.strip()
            off_s = rest.strip()
            off: int | None = int(off_s) if off_s != "" else None
        else:
            tit = line
            off = None
        specs.append((tit, order, off))
        order += 1
    return specs


def _format_todo_lines(tt: TaskTemplate) -> str:
    lines: list[str] = []
    for td in sorted(tt.todos, key=lambda x: (x.sort_order, x.id)):
        if td.milestone_offset_days is not None:
            lines.append(f"{td.title}|{td.milestone_offset_days}")
        else:
            lines.append(td.title)
    return "\n".join(lines)


def _populate_area_combo(combo: QComboBox, svc: TaskService, selected_id: int | None) -> None:
    combo.clear()
    combo.addItem("— None —", None)
    for cat in svc.list_categories():
        for sub in cat.subcategories:
            for area in sub.areas:
                label = f"{cat.name} / {sub.name} / {area.name}"
                combo.addItem(label, area.id)
    if selected_id is not None:
        for i in range(combo.count()):
            if combo.itemData(i) == selected_id:
                combo.setCurrentIndex(i)
                return


def _populate_person_combo(combo: QComboBox, svc: TaskService, selected_id: int | None) -> None:
    combo.clear()
    combo.addItem("— None —", None)
    for p in svc.list_people():
        combo.addItem(f"{p.last_name}, {p.first_name} ({p.employee_id})", p.id)
    if selected_id is not None:
        for i in range(combo.count()):
            if combo.itemData(i) == selected_id:
                combo.setCurrentIndex(i)
                return


def _status_combo(parent: QWidget) -> QComboBox:
    c = QComboBox(parent)
    for st in (
        TaskStatus.OPEN,
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.ON_HOLD,
        TaskStatus.CANCELLED,
        TaskStatus.CLOSED,
    ):
        c.addItem(st.replace("_", " ").title(), st)
    return c


class _TaskTemplatesDialog(QDialog):
    def __init__(self, svc: TaskService, ui_settings: dict, parent=None) -> None:
        super().__init__(parent)
        self._svc = svc
        self._ui_settings = ui_settings
        self._current_template_id: int | None = None
        self.setWindowTitle("Task templates")
        self.resize(720, 560)

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_row_changed)
        left.addWidget(self._list)
        row = QHBoxLayout()
        for label, slot in (
            ("Add…", self._add_template),
            ("Remove", self._remove_template),
            ("Move up", lambda: self._move(-1)),
            ("Move down", lambda: self._move(1)),
        ):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        tip = QLabel(
            "Placeholders in title, description, and todo lines: {today}, {yyyy}, {mm}, {dd}, {week}. "
            "Todos: one per line, optional Title|business_day_offset from received date."
        )
        tip.setWordWrap(True)
        right.addWidget(tip)

        form = QFormLayout()
        self._name = QLineEdit()
        self._title_pat = QLineEdit()
        self._desc_pat = QPlainTextEdit()
        self._desc_pat.setPlaceholderText("Description pattern (plain or HTML)…")
        self._desc_pat.setMaximumHeight(88)
        self._area = QComboBox()
        self._person = QComboBox()
        self._impact = QSpinBox()
        self._impact.setRange(1, 3)
        self._urgency = QSpinBox()
        self._urgency.setRange(1, 3)
        self._status = _status_combo(self)
        self._todos = QPlainTextEdit()
        self._todos.setPlaceholderText("First todo\nSecond todo|5")
        form.addRow("Name", self._name)
        form.addRow("Title pattern", self._title_pat)
        form.addRow("Description pattern", self._desc_pat)
        form.addRow("Default area", self._area)
        form.addRow("Default for-person", self._person)
        form.addRow("Impact", self._impact)
        form.addRow("Urgency", self._urgency)
        form.addRow("Status", self._status)
        form.addRow("Todo lines", self._todos)
        right.addLayout(form)

        save_row = QHBoxLayout()
        b_save = QPushButton("Save template")
        b_save.clicked.connect(self._save_current)
        save_row.addWidget(b_save)
        save_row.addStretch()
        right.addLayout(save_row)

        io = QHBoxLayout()
        b_exp = QPushButton("Export JSON…")
        b_exp.clicked.connect(self._export_json)
        b_imp = QPushButton("Import JSON…")
        b_imp.clicked.connect(self._import_json)
        io.addWidget(b_exp)
        io.addWidget(b_imp)
        io.addStretch()
        right.addLayout(io)

        root.addLayout(right, 2)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        right.addWidget(bb)

        self._reload_list()
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _reload_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for tt in self._svc.list_task_templates():
            self._list.addItem(tt.name)
            it = self._list.item(self._list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, tt.id)
        self._list.blockSignals(False)

    def _selected_template_id(self) -> int | None:
        it = self._list.currentItem()
        if it is None:
            return None
        raw = it.data(Qt.ItemDataRole.UserRole)
        return int(raw) if raw is not None else None

    def _on_row_changed(self, cur: QListWidgetItem | None, _prev) -> None:
        if cur is None:
            self._current_template_id = None
            self._clear_editor()
            return
        tid = cur.data(Qt.ItemDataRole.UserRole)
        self._current_template_id = int(tid) if tid is not None else None
        self._load_editor(self._current_template_id)

    def _clear_editor(self) -> None:
        self._name.clear()
        self._title_pat.clear()
        self._desc_pat.clear()
        _populate_area_combo(self._area, self._svc, None)
        _populate_person_combo(self._person, self._svc, None)
        self._impact.setValue(2)
        self._urgency.setValue(2)
        self._status.setCurrentIndex(0)
        self._todos.clear()

    def _load_editor(self, template_id: int | None) -> None:
        if template_id is None:
            self._clear_editor()
            return
        tt = self._svc.get_task_template(template_id)
        if not tt:
            self._clear_editor()
            return
        self._name.setText(tt.name)
        self._title_pat.setText(tt.title_pattern)
        self._desc_pat.setPlainText(tt.description_pattern or "")
        _populate_area_combo(self._area, self._svc, tt.default_area_id)
        _populate_person_combo(self._person, self._svc, tt.default_person_id)
        self._impact.setValue(tt.default_impact)
        self._urgency.setValue(tt.default_urgency)
        idx = self._status.findData(tt.default_status)
        self._status.setCurrentIndex(max(0, idx))
        self._todos.setPlainText(_format_todo_lines(tt))

    def _save_current(self) -> None:
        tid = self._selected_template_id()
        name = self._name.text().strip()
        title_pat = self._title_pat.text().strip()
        if not name or not title_pat:
            QMessageBox.warning(self, "Task templates", "Name and title pattern are required.")
            return
        desc = self._desc_pat.toPlainText().strip() or None
        area_id = self._area.currentData()
        person_id = self._person.currentData()
        st = self._status.currentData()
        specs = _parse_todo_template_lines(self._todos.toPlainText())
        if tid is None:
            created = self._svc.create_task_template(
                name=name,
                title_pattern=title_pat,
                description_pattern=desc,
                default_area_id=area_id,
                default_person_id=person_id,
                default_impact=self._impact.value(),
                default_urgency=self._urgency.value(),
                default_status=str(st) if st else TaskStatus.OPEN,
                todo_specs=specs,
            )
            if created is None:
                QMessageBox.warning(
                    self, "Task templates", "Could not create (duplicate name or invalid data)."
                )
                return
            self._reload_list()
            self._select_by_template_id(created.id)
        else:
            updated = self._svc.update_task_template(
                tid,
                name=name,
                title_pattern=title_pat,
                description_pattern=desc,
                default_area_id=area_id,
                default_person_id=person_id,
                default_impact=self._impact.value(),
                default_urgency=self._urgency.value(),
                default_status=str(st) if st else TaskStatus.OPEN,
                todo_specs=specs,
            )
            if updated is None:
                QMessageBox.warning(self, "Task templates", "Could not save (duplicate name?).")
                return
            self._reload_list()
            self._select_by_template_id(tid)

    def _select_by_template_id(self, template_id: int) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == template_id:
                self._list.setCurrentItem(it)
                return

    def _add_template(self) -> None:
        name, ok = QInputDialog.getText(self, "New template", "Template name:")
        if not ok or not name.strip():
            return
        created = self._svc.create_task_template(
            name=name.strip(),
            title_pattern="{today} — New task",
            description_pattern=None,
            default_area_id=None,
            default_person_id=None,
            default_impact=2,
            default_urgency=2,
            default_status=TaskStatus.OPEN,
            todo_specs=[],
        )
        if created is None:
            QMessageBox.warning(self, "Task templates", "Could not create (duplicate name?).")
            return
        self._reload_list()
        self._select_by_template_id(created.id)

    def _remove_template(self) -> None:
        tid = self._selected_template_id()
        if tid is None:
            return
        if (
            QMessageBox.question(
                self,
                "Remove template",
                "Remove this template?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._svc.delete_task_template(tid)
        self._reload_list()
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._clear_editor()

    def _move(self, delta: int) -> None:
        tid = self._selected_template_id()
        if tid is None:
            return
        self._svc.move_task_template(tid, delta)
        self._reload_list()
        self._select_by_template_id(tid)

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export task templates", "", "JSON (*.json)"
        )
        if not path:
            return
        self._svc.export_task_templates(Path(path))
        QMessageBox.information(self, "Task templates", "Exported.")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import task templates", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            summary = self._svc.import_task_templates(Path(path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Task templates", f"Import failed: {exc}")
            return
        self._reload_list()
        QMessageBox.information(
            self,
            "Task templates",
            f"Import complete.\nCreated: {summary['created']}\nUpdated: {summary['updated']}",
        )


def run_manage_task_templates_dialog(parent, svc: TaskService, ui_settings: dict) -> None:
    _TaskTemplatesDialog(svc, ui_settings, parent).exec()


def run_pick_task_template_dialog(
    parent, svc: TaskService, ui_settings: dict
) -> tuple[int, dt.date, dt.date | None] | None:
    """Return ``(template_id, received_date, due_date_or_none)`` or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("New task from template")
    d.resize(480, 420)
    lay = QVBoxLayout(d)
    flt = QLineEdit()
    flt.setPlaceholderText("Filter templates…")
    lay.addWidget(flt)
    lw = QListWidget()
    lay.addWidget(lw, 1)

    def repopulate() -> None:
        q = flt.text().strip().lower()
        lw.clear()
        for tt in svc.list_task_templates():
            if q and q not in tt.name.lower():
                continue
            lw.addItem(tt.name)
            it = lw.item(lw.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, tt.id)

    flt.textChanged.connect(lambda _t: repopulate())
    repopulate()

    fmt = get_date_format_qt(ui_settings)
    dates = QGroupBox("Dates for this instance")
    dl = QFormLayout(dates)
    recv_row, recv = date_edit_with_today_button(d, display_format=fmt)
    recv.setDate(QDate.currentDate())
    due_row, due = date_edit_with_today_button(d, clearable=True, display_format=fmt)
    dl.addRow("Received", recv_row)
    dl.addRow("Due", due_row)
    lay.addWidget(dates)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)

    result: list[tuple[int, dt.date, dt.date | None] | None] = [None]

    def accept_ok() -> None:
        it = lw.currentItem()
        if it is None:
            QMessageBox.warning(d, "Template", "Select a template.")
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if tid is None:
            return
        rdate = _qdate_to_py(recv.date())
        ddate = None if qdate_is_blank(due) else _qdate_to_py(due.date())
        result[0] = (int(tid), rdate, ddate)
        d.accept()

    bb.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(accept_ok)

    def on_dbl(_item: QListWidgetItem) -> None:
        accept_ok()

    lw.itemDoubleClicked.connect(on_dbl)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return result[0]
