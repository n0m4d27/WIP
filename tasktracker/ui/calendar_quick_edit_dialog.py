"""Quick-edit dialog launched from the Calendar tab.

In addition to the high-traffic fields a user typically wants to tweak
when acting on a calendar event (status, due / closed dates, impact /
urgency, for-person, area) this dialog now also hosts:

* an inline todos / milestones editor so users can adjust an
  individual milestone without leaving the calendar;
* a read-only notes viewer so the user can check recent context
  before rescheduling (double-click opens a read-only full view);
* a "Also shift todo milestones" checkbox that, on save, applies the
  same delta the user just made to the task's due date to every
  attached todo milestone (with a "Business days" sub-toggle that
  skips weekends and configured holidays);
* a compact selection-shift strip above the todos table that lets the
  user shift only the selected rows by N days.

Anything still richer - blockers, recurrence, descriptions - stays in
the full Tasks-tab editor; the "Open in Tasks tab for full edit"
button on this dialog jumps there in one click.

Save semantics mirror ``MainWindow._save_task_detail``: when the user
flips status to ``closed`` (from anything else) we delegate to
``TaskService.close_task`` so recurrence successors still spawn from a
calendar quick-edit.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from tasktracker.db.models import Task, TaskNote, TodoItem
from tasktracker.domain.enums import TaskStatus
from tasktracker.domain.priority import compute_priority, priority_display
from tasktracker.domain.ticket import format_task_ticket
from tasktracker.services.shift_service import ShiftResult, ShiftService
from tasktracker.services.task_service import TaskService
from tasktracker.ui.date_format import format_date, format_from_parent
from tasktracker.ui.date_widgets import date_edit_with_today_button, qdate_is_blank
from tasktracker.ui.todo_dialog import run_add_todo_dialog, run_edit_todo_dialog


def _qdate_to_py(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


def _py_to_qdate(d: dt.date) -> QDate:
    return QDate(d.year, d.month, d.day)


# ---------------------------------------------------------------------------
# Note viewer (nested read-only dialog)
# ---------------------------------------------------------------------------


class _NoteViewerDialog(QDialog):
    """Small read-only viewer for a single note.

    Opened from the quick-edit dialog's notes list (double-click a row)
    so users can read the full content without switching to the Tasks
    tab. Notes stay read-only here on purpose - the calendar view is a
    reschedule-oriented workflow, and editing rich notes belongs on the
    full task panel.
    """

    def __init__(self, parent, title: str, body_html: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 400)
        lay = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(body_html or "<p>(empty)</p>")
        lay.addWidget(browser, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


# ---------------------------------------------------------------------------
# Quick edit
# ---------------------------------------------------------------------------


class CalendarQuickEditDialog(QDialog):
    """Focused modal for rescheduling tasks from the calendar view."""

    open_full_editor_requested = Signal(int)

    def __init__(self, parent: QWidget | None, svc: TaskService, task: Task) -> None:
        super().__init__(parent)
        self._svc = svc
        self._parent = parent
        self._task_id = task.id
        self._task_ticket = format_task_ticket(task.ticket_number)
        self.setWindowTitle(f"Quick edit - {self._task_ticket} {task.title}")
        self.setModal(True)
        self.resize(720, 720)
        self.saved: bool = False
        self.spawned_successor: Task | None = None
        self.last_shift_result: ShiftResult | None = None

        # Original due date so the save path can compute the delta and
        # fan it out to todos via shift_task_milestones.
        self._original_due: dt.date | None = task.due_date

        # Cached so every QDateEdit and milestone-cell rendering uses the
        # same user-configured format without re-walking the parent chain.
        self._date_fmt = format_from_parent(parent)

        outer = QVBoxLayout(self)

        # --- Core fields form ------------------------------------------------
        form_host = QWidget()
        form = QFormLayout(form_host)

        self.f_title = QLineEdit(task.title)
        self.f_title.setReadOnly(True)
        form.addRow("Title:", self.f_title)

        self.f_status = QComboBox()
        for s in TaskStatus:
            self.f_status.addItem(s.value.replace("_", " ").title(), s.value)
        idx = self.f_status.findData(task.status)
        if idx >= 0:
            self.f_status.setCurrentIndex(idx)
        form.addRow("Status:", self.f_status)

        due_row, self.f_due = date_edit_with_today_button(
            self, clearable=True, display_format=self._date_fmt
        )
        if task.due_date is not None:
            self.f_due.setDate(_py_to_qdate(task.due_date))
        else:
            self.f_due.setDate(self.f_due.minimumDate())
        form.addRow("Due:", due_row)

        closed_row, self.f_closed = date_edit_with_today_button(
            self, clearable=True, display_format=self._date_fmt
        )
        if task.closed_date is not None:
            self.f_closed.setDate(_py_to_qdate(task.closed_date))
        else:
            self.f_closed.setDate(self.f_closed.minimumDate())
        form.addRow("Closed:", closed_row)

        iu_row = QWidget()
        iu_lay = QHBoxLayout(iu_row)
        iu_lay.setContentsMargins(0, 0, 0, 0)
        self.f_impact = QSpinBox()
        self.f_impact.setRange(1, 3)
        self.f_impact.setValue(task.impact)
        self.f_urgency = QSpinBox()
        self.f_urgency.setRange(1, 3)
        self.f_urgency.setValue(task.urgency)
        self.f_priority_label = QLabel("")
        self.f_impact.valueChanged.connect(self._refresh_priority_label)
        self.f_urgency.valueChanged.connect(self._refresh_priority_label)
        iu_lay.addWidget(QLabel("I"))
        iu_lay.addWidget(self.f_impact)
        iu_lay.addWidget(QLabel("U"))
        iu_lay.addWidget(self.f_urgency)
        iu_lay.addWidget(self.f_priority_label, 1)
        form.addRow("Impact / Urgency:", iu_row)
        self._refresh_priority_label()

        self.f_for_person = QComboBox()
        self.f_for_person.addItem("- None -", None)
        for p in svc.list_people():
            label = f"{p.last_name}, {p.first_name} ({p.employee_id})"
            self.f_for_person.addItem(label, p.id)
        cur_pid = task.person.id if task.person is not None else None
        pidx = self.f_for_person.findData(cur_pid)
        self.f_for_person.setCurrentIndex(pidx if pidx >= 0 else 0)
        form.addRow("For person:", self.f_for_person)

        self.f_area = QComboBox()
        self.f_area.addItem("- None -", None)
        cur_area_id = task.area.id if task.area is not None else None
        for cat in svc.list_categories():
            for sub in cat.subcategories:
                for area in sub.areas:
                    self.f_area.addItem(f"{cat.name} / {sub.name} / {area.name}", area.id)
        aidx = self.f_area.findData(cur_area_id)
        self.f_area.setCurrentIndex(aidx if aidx >= 0 else 0)
        form.addRow("Area:", self.f_area)

        # "Also shift todo milestones" + "Business days" checkboxes live
        # right under the core form so the user can see them while they
        # tweak the task's due date.
        self.chk_shift_todos = QCheckBox(
            "Also shift todo milestones by the same number of days"
        )
        self.chk_shift_todos.setChecked(True)
        self.chk_shift_todos.setToolTip(
            "When on, saving a change to the task's due date applies the "
            "same delta to every attached todo milestone."
        )
        self.chk_shift_business = QCheckBox(
            "Business days (skip weekends + holidays)"
        )
        self.chk_shift_business.setChecked(True)
        self.chk_shift_business.setEnabled(self.chk_shift_todos.isChecked())
        self.chk_shift_todos.toggled.connect(self.chk_shift_business.setEnabled)
        form.addRow("", self.chk_shift_todos)
        form.addRow("", self.chk_shift_business)

        outer.addWidget(form_host)

        # --- Splitter: todos on top, notes below ---------------------------
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_todos_section())
        splitter.addWidget(self._build_notes_section())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        # --- Buttons row ----------------------------------------------------
        btn_row = QHBoxLayout()
        self.btn_open_full = QPushButton("Open in Tasks tab for full edit")
        self.btn_open_full.setFlat(True)
        self.btn_open_full.clicked.connect(self._on_open_full)
        btn_row.addWidget(self.btn_open_full)
        btn_row.addStretch(1)
        self.bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.bbox.accepted.connect(self._on_save)
        self.bbox.rejected.connect(self.reject)
        btn_row.addWidget(self.bbox)
        outer.addLayout(btn_row)

        self._reload_todos()
        self._reload_notes()

    # ------------------------------------------------------------------
    # Todos section
    # ------------------------------------------------------------------

    def _build_todos_section(self) -> QWidget:
        box = QGroupBox("Todos / milestones")
        v = QVBoxLayout(box)

        # Selection-shift strip. Applies a delta to only the selected
        # todo rows via ShiftService.preview_todo_shift + apply_shift.
        strip = QHBoxLayout()
        strip.addWidget(QLabel("Shift selected:"))
        self.sp_sel_delta = QSpinBox()
        self.sp_sel_delta.setRange(-365, 365)
        self.sp_sel_delta.setValue(5)
        self.sp_sel_delta.setSuffix(" day(s)")
        strip.addWidget(self.sp_sel_delta)
        self.chk_sel_business = QCheckBox("Business days")
        self.chk_sel_business.setChecked(True)
        strip.addWidget(self.chk_sel_business)
        self.btn_sel_apply = QPushButton("Apply to selection")
        self.btn_sel_apply.clicked.connect(self._apply_selection_shift)
        strip.addWidget(self.btn_sel_apply)
        strip.addStretch(1)
        v.addLayout(strip)

        # Todos table. The rows are not directly editable - users open
        # the add/edit dialog via the buttons below, which keeps the
        # edit flow the same as the Tasks-tab editor.
        self.tbl_todos = QTableWidget(0, 3)
        self.tbl_todos.setHorizontalHeaderLabels(["Title", "Milestone", "Done"])
        self.tbl_todos.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.tbl_todos.horizontalHeader().setStretchLastSection(False)
        self.tbl_todos.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tbl_todos.verticalHeader().setVisible(False)
        self.tbl_todos.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_todos.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tbl_todos.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_todos.itemDoubleClicked.connect(lambda _it: self._edit_selected_todo())
        v.addWidget(self.tbl_todos, 1)

        btn_row = QHBoxLayout()
        self.btn_todo_add = QPushButton("Add…")
        self.btn_todo_add.clicked.connect(self._add_todo)
        self.btn_todo_edit = QPushButton("Edit…")
        self.btn_todo_edit.clicked.connect(self._edit_selected_todo)
        self.btn_todo_done = QPushButton("Mark done")
        self.btn_todo_done.clicked.connect(self._complete_selected_todos)
        self.btn_todo_delete = QPushButton("Delete")
        self.btn_todo_delete.clicked.connect(self._delete_selected_todos)
        btn_row.addWidget(self.btn_todo_add)
        btn_row.addWidget(self.btn_todo_edit)
        btn_row.addWidget(self.btn_todo_done)
        btn_row.addWidget(self.btn_todo_delete)
        btn_row.addStretch(1)
        v.addLayout(btn_row)
        return box

    def _reload_todos(self) -> None:
        """Re-query todos from the DB and repopulate the table.

        Called after any mutation (add/edit/delete/complete/shift) so
        the table always reflects what's actually saved. Re-selects
        whatever rows had `keep_ids` before the reload when possible.
        """
        keep_ids: set[int] = set()
        for it in self.tbl_todos.selectedItems():
            if it.column() == 0:
                tid = it.data(Qt.ItemDataRole.UserRole)
                if tid is not None:
                    keep_ids.add(int(tid))

        task = self._svc.get_task(self._task_id)
        todos: list[TodoItem] = (
            sorted(task.todos, key=lambda x: x.sort_order) if task is not None else []
        )
        self.tbl_todos.setRowCount(len(todos))
        for r, td in enumerate(todos):
            title_item = QTableWidgetItem(td.title)
            title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            title_item.setData(Qt.ItemDataRole.UserRole, td.id)
            ms_item = QTableWidgetItem(format_date(td.milestone_date, self._date_fmt))
            ms_item.setFlags(ms_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            done_item = QTableWidgetItem("yes" if td.completed_at else "")
            done_item.setFlags(done_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_todos.setItem(r, 0, title_item)
            self.tbl_todos.setItem(r, 1, ms_item)
            self.tbl_todos.setItem(r, 2, done_item)
            if td.id in keep_ids:
                self.tbl_todos.selectRow(r)
        self.tbl_todos.resizeColumnToContents(1)
        self.tbl_todos.resizeColumnToContents(2)

    def _selected_todo_ids(self) -> list[int]:
        out: list[int] = []
        for it in self.tbl_todos.selectedItems():
            if it.column() == 0:
                tid = it.data(Qt.ItemDataRole.UserRole)
                if tid is not None:
                    out.append(int(tid))
        return out

    def _add_todo(self) -> None:
        result = run_add_todo_dialog(self)
        if result is None:
            return
        title, ms = result
        self._svc.add_todo(self._task_id, title=title, milestone_date=ms)
        self._reload_todos()

    def _edit_selected_todo(self) -> None:
        ids = self._selected_todo_ids()
        if not ids:
            QMessageBox.information(self, "Todo", "Select a todo row to edit.")
            return
        if len(ids) > 1:
            QMessageBox.information(
                self, "Todo",
                "Pick exactly one row to edit (multi-row edit is not supported).",
            )
            return
        current = self._svc.get_todo(ids[0])
        if current is None:
            return
        result = run_edit_todo_dialog(
            self,
            current_title=current.title,
            current_milestone=current.milestone_date,
        )
        if result is None:
            return
        new_title, new_ms = result
        self._svc.update_todo(ids[0], title=new_title, milestone_date=new_ms)
        self._reload_todos()

    def _complete_selected_todos(self) -> None:
        for tid in self._selected_todo_ids():
            self._svc.complete_todo(tid)
        self._reload_todos()

    def _delete_selected_todos(self) -> None:
        ids = self._selected_todo_ids()
        if not ids:
            return
        reply = QMessageBox.question(
            self, "Delete todos",
            f"Delete {len(ids)} todo(s)? This can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for tid in ids:
            self._svc.delete_todo(tid)
        self._reload_todos()

    def _apply_selection_shift(self) -> None:
        ids = self._selected_todo_ids()
        if not ids:
            QMessageBox.information(
                self, "Shift todos",
                "Select one or more todos first.",
            )
            return
        delta = self.sp_sel_delta.value()
        if delta == 0:
            QMessageBox.information(self, "Shift todos", "Delta is zero - nothing to do.")
            return
        business = self.chk_sel_business.isChecked()
        ss = ShiftService(self._svc.session)
        plan = ss.preview_todo_shift(ids, delta, business_days=business)
        if not plan.rows:
            QMessageBox.information(self, "Shift todos", "None of the selected todos have milestones to shift.")
            return
        try:
            result = ss.apply_shift(plan)
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "Shift failed", str(exc))
            return
        self.last_shift_result = result
        # Feed the shift into the parent MainWindow's undo slot when
        # available so Edit > Undo last bulk shift picks it up.
        parent = self._parent
        if parent is not None and hasattr(parent, "record_bulk_shift"):
            parent.record_bulk_shift(result)
        self._reload_todos()

    # ------------------------------------------------------------------
    # Notes section
    # ------------------------------------------------------------------

    def _build_notes_section(self) -> QWidget:
        box = QGroupBox("Notes (read-only snapshot)")
        v = QVBoxLayout(box)
        hint = QLabel(
            "Double-click a note to read the full content. Editing notes "
            "is done from the Tasks tab."
        )
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.lst_notes = QListWidget()
        self.lst_notes.itemDoubleClicked.connect(self._on_note_double_clicked)
        v.addWidget(self.lst_notes, 1)
        return box

    def _reload_notes(self) -> None:
        self.lst_notes.clear()
        task = self._svc.get_task(self._task_id)
        if task is None:
            return
        for n in sorted(task.notes, key=lambda x: x.created_at, reverse=True):
            latest_body = ""
            if n.versions:
                latest = max(n.versions, key=lambda v: v.version_seq)
                latest_body = latest.body_html
            snippet = _snippet(latest_body)
            prefix = "[System] " if n.is_system else ""
            label = f"{n.created_at.strftime('%Y-%m-%d %H:%M')}  {prefix}{snippet}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, n.id)
            self.lst_notes.addItem(item)

    def _on_note_double_clicked(self, item: QListWidgetItem) -> None:
        nid = item.data(Qt.ItemDataRole.UserRole)
        if nid is None:
            return
        note = self._svc.session.get(TaskNote, int(nid))
        if note is None:
            return
        body = ""
        if note.versions:
            latest = max(note.versions, key=lambda v: v.version_seq)
            body = latest.body_html
        viewer = _NoteViewerDialog(
            self,
            f"Note - {note.created_at.strftime('%Y-%m-%d %H:%M')}",
            body,
        )
        viewer.exec()

    # ------------------------------------------------------------------
    # Priority readout / save
    # ------------------------------------------------------------------

    def _refresh_priority_label(self) -> None:
        try:
            pr = compute_priority(impact=self.f_impact.value(), urgency=self.f_urgency.value())
            self.f_priority_label.setText(priority_display(pr))
        except ValueError:
            self.f_priority_label.setText("-")

    def _on_open_full(self) -> None:
        self.open_full_editor_requested.emit(self._task_id)
        self.reject()

    def _on_save(self) -> None:
        existing = self._svc.get_task(self._task_id)
        if existing is None:
            self.reject()
            return

        st = self.f_status.currentData()
        due_py = None if qdate_is_blank(self.f_due) else _qdate_to_py(self.f_due.date())
        closed_py = (
            None if qdate_is_blank(self.f_closed) else _qdate_to_py(self.f_closed.date())
        )

        was_closed = existing.status == TaskStatus.CLOSED
        closing_now = (st == TaskStatus.CLOSED) and not was_closed

        # Mirrors MainWindow._save_task_detail: hand the actual close
        # transition off to TaskService.close_task so recurrence successors
        # spawn correctly even when the user closes via the quick-edit dialog.
        self._svc.update_task_fields(
            self._task_id,
            status=None if closing_now else st,
            impact=self.f_impact.value(),
            urgency=self.f_urgency.value(),
            due_date=due_py,
            closed_date=closed_py if (st == TaskStatus.CLOSED and not closing_now) else None,
            area_id=self.f_area.currentData(),
            person_id=self.f_for_person.currentData(),
        )
        if closing_now:
            _, self.spawned_successor = self._svc.close_task(
                self._task_id, closed_on=closed_py
            )

        # Fan the due-date delta out to todos when requested.
        if (
            self.chk_shift_todos.isChecked()
            and self._original_due is not None
            and due_py is not None
            and due_py != self._original_due
        ):
            delta = (due_py - self._original_due).days
            if delta != 0:
                self._svc.shift_task_milestones(
                    self._task_id,
                    delta,
                    business_days=self.chk_shift_business.isChecked(),
                )

        self.saved = True
        self.accept()


def _snippet(html_body: str, *, limit: int = 80) -> str:
    """Best-effort short preview of a note's rendered body for the list."""
    import html as htmllib
    import re

    if not html_body:
        return "(empty)"
    # Strip head/style/script + tags + collapse whitespace.
    text = re.sub(r"<head\b[^>]*>.*?</head>", " ", html_body, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = htmllib.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "(empty)"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def run_calendar_quick_edit_dialog(
    parent: QWidget | None, svc: TaskService, task_id: int
) -> tuple[bool, Task | None, bool]:
    """Open the quick-edit dialog. Returns ``(saved, spawned_successor,
    open_full_requested)``."""
    task = svc.get_task(task_id)
    if task is None:
        return (False, None, False)
    dlg = CalendarQuickEditDialog(parent, svc, task)
    open_full_flag = {"value": False}

    def _on_open_full(_tid: int) -> None:
        open_full_flag["value"] = True

    dlg.open_full_editor_requested.connect(_on_open_full)
    dlg.exec()
    return (dlg.saved, dlg.spawned_successor, open_full_flag["value"])
