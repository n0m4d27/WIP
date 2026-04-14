from __future__ import annotations

import calendar
import datetime as dt
import html as htmllib
import re
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QAction, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
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
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy.orm import joinedload

from tasktracker.db.models import TaskNote
from tasktracker.domain.enums import RecurrenceGenerationMode, TaskStatus
from tasktracker.domain.priority import compute_priority, priority_display
from tasktracker.domain.ticket import format_task_ticket
from tasktracker.services.task_service import TaskService
from tasktracker.ui.date_widgets import date_edit_with_today_button
from tasktracker.ui.priority_matrix_dialog import PriorityMatrixDialog
from tasktracker.ui.todo_dialog import run_add_todo_dialog
from tasktracker.ui.user_guide_dialog import run_user_guide_dialog


def _qdate_to_py(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


def _py_to_qdate(d: dt.date) -> QDate:
    return QDate(d.year, d.month, d.day)


_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _plain_from_html(value: str | None) -> str:
    if not value:
        return ""
    text = _HEAD_RE.sub(" ", value)
    text = _STYLE_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = htmllib.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _clip(text: str, limit: int = 56) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _system_note_title(body_plain: str) -> str:
    low = body_plain.lower()
    if "priority updated automatically" in low:
        return "Priority auto-updated"
    return "System update"


class MainWindow(QMainWindow):
    def __init__(
        self,
        session_factory,
        *,
        engine=None,
        secure_shutdown=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Task Tracker (WIP)")
        self.resize(1100, 720)

        self._engine = engine
        self._secure_shutdown = secure_shutdown
        self._session_factory = session_factory
        self._session = session_factory()
        self._svc = TaskService(self._session)
        self._current_task_id: int | None = None

        self._build_ui()
        self._build_menu_toolbar()
        self._reload_task_list()

    def _session_reset(self) -> None:
        self._session.close()
        self._session = self._session_factory()
        self._svc = TaskService(self._session)

    @staticmethod
    def _select_list_item_by_id(list_widget: QListWidget, item_id: int | None) -> bool:
        """Select item in list by UserRole id; return True when found."""
        if item_id is None:
            return False
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == item_id:
                list_widget.setCurrentItem(item)
                return True
        return False

    def _build_menu_toolbar(self) -> None:
        tb = QToolBar()
        self.addToolBar(tb)
        act_new = QAction("New task", self)
        act_new.triggered.connect(self._new_task)
        tb.addAction(act_new)
        act_save = QAction("Save task", self)
        act_save.triggered.connect(self._save_task_detail)
        tb.addAction(act_save)
        act_close = QAction("Close task", self)
        act_close.triggered.connect(self._close_current_task)
        tb.addAction(act_close)
        act_matrix = QAction("Priority matrix…", self)
        act_matrix.triggered.connect(self._show_matrix)
        tb.addAction(act_matrix)

        m_file = self.menuBar().addMenu("&File")
        m_file.addAction("Export tasks to CSV…", self._export_csv)
        m_file.addAction("Export tasks to Excel…", self._export_excel)
        m_file.addSeparator()
        m_file.addAction("Quit", self.close)

        m_help = self.menuBar().addMenu("&Help")
        m_help.addAction("User guide…", self._show_user_guide)
        m_help.addSeparator()
        m_help.addAction("About", self._about)

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        tabs.addTab(self._build_tasks_tab(), "Tasks")
        tabs.addTab(self._build_calendar_tab(), "Calendar")
        tabs.addTab(self._build_reports_tab(), "Reports")
        tabs.addTab(self._build_holidays_tab(), "Holidays")

    def _build_tasks_tab(self) -> QWidget:
        w = QWidget()
        split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        search_box = QGroupBox("Search")
        sl = QVBoxLayout(search_box)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search…")
        self.search_edit.returnPressed.connect(self._reload_task_list)
        sl.addWidget(self.search_edit)
        chk_row = QHBoxLayout()
        self.search_title = QCheckBox("Title")
        self.search_title.setChecked(True)
        self.search_description = QCheckBox("Description")
        self.search_notes = QCheckBox("Notes")
        self.search_todos = QCheckBox("Todos")
        self.search_blockers = QCheckBox("Blockers")
        self.search_audit = QCheckBox("Audit")
        self.search_ticket = QCheckBox("Ticket (T12 or 12)")
        for c in (
            self.search_title,
            self.search_description,
            self.search_notes,
            self.search_todos,
            self.search_blockers,
            self.search_audit,
            self.search_ticket,
        ):
            chk_row.addWidget(c)
        sl.addLayout(chk_row)
        sbtn = QHBoxLayout()
        self.btn_search = QPushButton("Search")
        self.btn_search.clicked.connect(self._reload_task_list)
        self.btn_search_clear = QPushButton("Clear")
        self.btn_search_clear.clicked.connect(self._clear_search)
        sbtn.addWidget(self.btn_search)
        sbtn.addWidget(self.btn_search_clear)
        sl.addLayout(sbtn)
        ll.addWidget(search_box)

        self.chk_hide_closed = QCheckBox("Hide closed tasks")
        self.chk_hide_closed.setChecked(True)
        self.chk_hide_closed.toggled.connect(self._reload_task_list)
        ll.addWidget(self.chk_hide_closed)
        self.task_list = QListWidget()
        self.task_list.currentItemChanged.connect(self._on_task_selected)
        ll.addWidget(self.task_list)

        right = QScrollArea()
        right.setWidgetResizable(True)
        detail = QWidget()
        self.detail_widget = detail
        fl = QFormLayout(detail)

        self.lbl_ticket = QLabel("—")
        self.lbl_ticket.setStyleSheet("font-weight: bold;")
        self.f_title = QLineEdit()
        self.f_description = QTextEdit()
        self.f_description.setAcceptRichText(True)
        self.f_description.setMinimumHeight(80)
        self.f_status = QComboBox()
        for s in TaskStatus:
            self.f_status.addItem(s.value.replace("_", " ").title(), s.value)

        iu_row = QWidget()
        iu_lay = QHBoxLayout(iu_row)
        iu_lay.setContentsMargins(0, 0, 0, 0)
        self.f_impact = QSpinBox()
        self.f_impact.setRange(1, 3)
        self.f_impact.setValue(2)
        self.f_urgency = QSpinBox()
        self.f_urgency.setRange(1, 3)
        self.f_urgency.setValue(2)
        self.f_priority_label = QLabel("")
        self.f_impact.valueChanged.connect(self._refresh_priority_label)
        self.f_urgency.valueChanged.connect(self._refresh_priority_label)
        iu_lay.addWidget(QLabel("Impact"))
        iu_lay.addWidget(self.f_impact)
        iu_lay.addWidget(QLabel("Urgency"))
        iu_lay.addWidget(self.f_urgency)
        iu_lay.addWidget(QLabel("→"))
        iu_lay.addWidget(self.f_priority_label)
        iu_lay.addStretch()

        recv_row, self.f_received = date_edit_with_today_button()
        self.f_received.setDate(QDate.currentDate())
        due_row, self.f_due = date_edit_with_today_button()
        self.f_due.setSpecialValueText("")
        self.f_due.setDate(QDate.currentDate().addDays(7))
        closed_row, self.f_closed = date_edit_with_today_button()
        self.f_closed.setSpecialValueText("—")
        self.f_closed.setDate(QDate.currentDate())

        fl.addRow("Ticket", self.lbl_ticket)
        fl.addRow("Title", self.f_title)
        fl.addRow("Description", self.f_description)
        fl.addRow("Status", self.f_status)
        fl.addRow("I / U / P", iu_row)
        fl.addRow("Received", recv_row)
        fl.addRow("Due", due_row)
        fl.addRow("Closed", closed_row)

        self.lbl_next_ms = QLabel("—")
        fl.addRow("Next milestone", self.lbl_next_ms)

        todo_box = QGroupBox("Todos (ordered)")
        todo_l = QVBoxLayout(todo_box)
        self.todo_list = QListWidget()
        todo_l.addWidget(self.todo_list)
        t_btn = QHBoxLayout()
        self.btn_todo_add = QPushButton("Add todo…")
        self.btn_todo_add.clicked.connect(self._add_todo)
        self.btn_todo_done = QPushButton("Mark done")
        self.btn_todo_done.clicked.connect(self._complete_todo)
        self.btn_todo_up = QPushButton("Up")
        self.btn_todo_up.clicked.connect(lambda: self._move_todo(-1))
        self.btn_todo_dn = QPushButton("Down")
        self.btn_todo_dn.clicked.connect(lambda: self._move_todo(1))
        t_btn.addWidget(self.btn_todo_add)
        t_btn.addWidget(self.btn_todo_done)
        t_btn.addWidget(self.btn_todo_up)
        t_btn.addWidget(self.btn_todo_dn)
        todo_l.addLayout(t_btn)
        fl.addRow(todo_box)

        note_box = QGroupBox("Notes (rich text)")
        note_l = QVBoxLayout(note_box)
        self.note_list = QListWidget()
        self.note_list.currentItemChanged.connect(self._on_note_selected)
        note_l.addWidget(self.note_list)
        self.note_editor = QTextEdit()
        self.note_editor.setAcceptRichText(True)
        self.note_editor.setMinimumHeight(120)
        note_l.addWidget(self.note_editor)
        n_btn = QHBoxLayout()
        self.btn_note_new = QPushButton("New note")
        self.btn_note_new.clicked.connect(self._new_note)
        self.btn_note_save = QPushButton("Save note")
        self.btn_note_save.clicked.connect(self._save_note)
        n_btn.addWidget(self.btn_note_new)
        n_btn.addWidget(self.btn_note_save)
        note_l.addLayout(n_btn)
        fl.addRow(note_box)

        blk_box = QGroupBox("Blockers")
        blk_l = QVBoxLayout(blk_box)
        self.blocker_list = QListWidget()
        blk_l.addWidget(self.blocker_list)
        b_btn = QHBoxLayout()
        self.btn_blk_add = QPushButton("Add blocker…")
        self.btn_blk_add.clicked.connect(self._add_blocker)
        self.btn_blk_clear = QPushButton("Clear selected")
        self.btn_blk_clear.clicked.connect(self._clear_blocker)
        b_btn.addWidget(self.btn_blk_add)
        b_btn.addWidget(self.btn_blk_clear)
        blk_l.addLayout(b_btn)
        fl.addRow(blk_box)

        rec_box = QGroupBox("Recurring (template todos for next instance)")
        rec_l = QVBoxLayout(rec_box)
        self.rec_enable = QCheckBox("This task is recurring")
        rec_l.addWidget(self.rec_enable)
        self.rec_mode = QComboBox()
        self.rec_mode.addItem("Generate on close", RecurrenceGenerationMode.ON_CLOSE)
        self.rec_mode.addItem("Scheduled (manual run later)", RecurrenceGenerationMode.SCHEDULED)
        rec_l.addWidget(self.rec_mode)
        rr = QHBoxLayout()
        rr.addWidget(QLabel("Interval (business days)"))
        self.rec_interval = QSpinBox()
        self.rec_interval.setRange(1, 365)
        self.rec_interval.setValue(7)
        rr.addWidget(self.rec_interval)
        self.rec_skip_w = QCheckBox("Skip weekends")
        self.rec_skip_w.setChecked(True)
        self.rec_skip_h = QCheckBox("Skip holidays")
        self.rec_skip_h.setChecked(True)
        rr.addWidget(self.rec_skip_w)
        rr.addWidget(self.rec_skip_h)
        rec_l.addLayout(rr)
        self.rec_template = QPlainTextEdit()
        self.rec_template.setPlaceholderText("One line per template todo: Title|days_after_received\nExample:\nKickoff|0\nReview|3")
        self.rec_template.setMaximumHeight(100)
        rec_l.addWidget(self.rec_template)
        self.btn_rec_save = QPushButton("Save recurrence settings")
        self.btn_rec_save.clicked.connect(self._save_recurrence)
        rec_l.addWidget(self.btn_rec_save)
        fl.addRow(rec_box)

        tl_box = QGroupBox("Activity (audit + notes)")
        tl_l = QVBoxLayout(tl_box)
        self.timeline = QPlainTextEdit()
        self.timeline.setReadOnly(True)
        self.timeline.setMaximumHeight(160)
        tl_l.addWidget(self.timeline)
        btn_tl = QPushButton("Refresh timeline")
        btn_tl.clicked.connect(self._refresh_timeline)
        tl_l.addWidget(btn_tl)
        fl.addRow(tl_box)

        right.setWidget(detail)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(w)
        lay.addWidget(split)
        self._refresh_priority_label()
        return w

    def _build_calendar_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        cal_side = QVBoxLayout()
        cal_top = QHBoxLayout()
        self.cal_widget = QCalendarWidget()
        self.cal_widget.selectionChanged.connect(self._on_calendar_date_changed)
        self.cal_widget.currentPageChanged.connect(lambda _y, _m: self._highlight_calendar_month())
        cal_top.addWidget(self.cal_widget, 1)
        cal_today_col = QVBoxLayout()
        self.btn_cal_today = QPushButton("Today")
        self.btn_cal_today.setToolTip("Jump calendar to today")
        self.btn_cal_today.clicked.connect(self._calendar_go_today)
        cal_today_col.addWidget(self.btn_cal_today)
        cal_today_col.addStretch()
        cal_top.addLayout(cal_today_col)
        cal_side.addLayout(cal_top)

        toggles = QGroupBox("Overlays")
        tg = QVBoxLayout(toggles)
        self.cal_show_due = QCheckBox("Task due dates")
        self.cal_show_due.setChecked(True)
        self.cal_show_ms = QCheckBox("Todo milestones")
        self.cal_show_ms.setChecked(True)
        self.cal_show_recv = QCheckBox("Received dates")
        self.cal_show_closed = QCheckBox("Closed dates")
        self.cal_include_closed_tasks = QCheckBox("Include closed tasks on calendar")
        for c in (
            self.cal_show_due,
            self.cal_show_ms,
            self.cal_show_recv,
            self.cal_show_closed,
            self.cal_include_closed_tasks,
        ):
            c.toggled.connect(self._on_calendar_date_changed)
        tg.addWidget(self.cal_show_due)
        tg.addWidget(self.cal_show_ms)
        tg.addWidget(self.cal_show_recv)
        self.cal_show_closed.toggled.connect(self._on_calendar_date_changed)
        tg.addWidget(self.cal_show_closed)
        tg.addWidget(self.cal_include_closed_tasks)
        self.btn_apply_due = QPushButton("Set current task due date to selected day")
        self.btn_apply_due.clicked.connect(self._apply_calendar_to_due)
        tg.addWidget(self.btn_apply_due)
        cal_side.addWidget(toggles)

        legend = QLabel(
            "<b>Legend</b><br>"
            "<span style='color:#1565c0'>■</span> Due &nbsp;"
            "<span style='color:#2e7d32'>■</span> Milestone &nbsp;"
            "<span style='color:#757575'>■</span> Received &nbsp;"
            "<span style='color:#ef6c00'>■</span> Closed &nbsp;"
            "<span style='color:#c62828'>■</span> Holiday<br>"
            "Within each day, items are sorted by priority (P1 first). "
            "Task chips can show priority in the label."
        )
        legend.setWordWrap(True)
        cal_side.addWidget(legend)

        lay.addLayout(cal_side, 1)

        self.cal_event_list = QListWidget()
        lay.addWidget(self.cal_event_list, 1)
        self._on_calendar_date_changed()
        return w

    def _calendar_go_today(self) -> None:
        today = QDate.currentDate()
        self.cal_widget.setSelectedDate(today)
        self.cal_widget.setCurrentPage(today.year(), today.month())

    def _build_reports_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.report_out = QPlainTextEdit()
        self.report_out.setReadOnly(True)
        lay.addWidget(self.report_out)
        row = QHBoxLayout()
        b1 = QPushButton("Overdue (open)")
        b1.clicked.connect(self._run_report_overdue)
        b2 = QPushButton("Due in next 7 days")
        b2.clicked.connect(self._run_report_week)
        b3 = QPushButton("Closure velocity (30d)")
        b3.clicked.connect(self._run_report_velocity)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addWidget(b3)
        lay.addLayout(row)
        return w

    def _build_holidays_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.holiday_table = QListWidget()
        lay.addWidget(self.holiday_table)
        row = QHBoxLayout()
        self.btn_h_add = QPushButton("Add holiday…")
        self.btn_h_add.clicked.connect(self._add_holiday_dialog)
        self.btn_h_del = QPushButton("Remove selected")
        self.btn_h_del.clicked.connect(self._remove_holiday)
        row.addWidget(self.btn_h_add)
        row.addWidget(self.btn_h_del)
        lay.addLayout(row)
        self._reload_holidays_list()
        return w

    def _search_field_names(self) -> set[str]:
        m = {
            "title": self.search_title,
            "description": self.search_description,
            "notes": self.search_notes,
            "todos": self.search_todos,
            "blockers": self.search_blockers,
            "audit": self.search_audit,
            "ticket": self.search_ticket,
        }
        return {k for k, w in m.items() if w.isChecked()}

    def _tasks_for_sidebar(self):
        include_closed = not self.chk_hide_closed.isChecked()
        q = self.search_edit.text().strip()
        if q:
            fields = self._search_field_names()
            if not fields:
                fields = {"title"}
            return self._svc.search_tasks(q, fields=fields, include_closed=include_closed)
        return self._svc.list_tasks(include_closed=include_closed)

    def _clear_search(self) -> None:
        self.search_edit.clear()
        self._reload_task_list()

    def _reload_task_list(self) -> None:
        saved_id = self._current_task_id
        self.task_list.blockSignals(True)
        try:
            self.task_list.clear()
            for t in self._tasks_for_sidebar():
                pr = priority_display(t.priority)
                due = t.due_date.isoformat() if t.due_date else "no due"
                tk = format_task_ticket(t.ticket_number)
                self.task_list.addItem(f"{tk} [{pr}] {t.title} — {due} ({t.status})")
                it = self.task_list.item(self.task_list.count() - 1)
                it.setData(Qt.ItemDataRole.UserRole, t.id)
            if saved_id is not None:
                for i in range(self.task_list.count()):
                    it = self.task_list.item(i)
                    if it and it.data(Qt.ItemDataRole.UserRole) == saved_id:
                        self.task_list.setCurrentItem(it)
                        break
        finally:
            self.task_list.blockSignals(False)
        cur = self.task_list.currentItem()
        if cur is not None and cur.data(Qt.ItemDataRole.UserRole) is not None:
            self._current_task_id = int(cur.data(Qt.ItemDataRole.UserRole))
            self._load_task_detail()
        else:
            self._current_task_id = None
            self._blank_detail_pane()
        self._refresh_priority_label()

    def _blank_detail_pane(self) -> None:
        self.lbl_ticket.setText("—")
        self.f_title.clear()
        self.f_description.clear()
        self.todo_list.clear()
        self.note_list.clear()
        self.note_editor.clear()
        self.blocker_list.clear()
        self.timeline.clear()
        self.rec_enable.setChecked(False)
        self.rec_template.clear()
        self.lbl_next_ms.setText("—")

    def _on_task_selected(self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if not cur:
            self._current_task_id = None
            self._blank_detail_pane()
            return
        tid = cur.data(Qt.ItemDataRole.UserRole)
        self._current_task_id = int(tid) if tid is not None else None
        self._load_task_detail()

    def _load_task_detail(self) -> None:
        tid = self._current_task_id
        if tid is None:
            return
        task = self._svc.get_task(tid)
        if not task:
            return
        self.lbl_ticket.setText(format_task_ticket(task.ticket_number))
        self.f_title.setText(task.title)
        self.f_description.setHtml(task.description or "")
        idx = self.f_status.findData(task.status)
        self.f_status.setCurrentIndex(max(0, idx))
        self.f_impact.setValue(task.impact)
        self.f_urgency.setValue(task.urgency)
        self._refresh_priority_label()
        self.f_received.setDate(_py_to_qdate(task.received_date))
        if task.due_date:
            self.f_due.setDate(_py_to_qdate(task.due_date))
        else:
            self.f_due.setDate(QDate.currentDate())
        if task.closed_date:
            self.f_closed.setDate(_py_to_qdate(task.closed_date))
        else:
            self.f_closed.setDate(QDate.currentDate())
        self.lbl_next_ms.setText(
            task.next_milestone_date.isoformat() if task.next_milestone_date else "—"
        )

        self.todo_list.clear()
        for td in sorted(task.todos, key=lambda x: x.sort_order):
            ms = td.milestone_date.isoformat() if td.milestone_date else ""
            done = "✓ " if td.completed_at else ""
            self.todo_list.addItem(f"{done}{td.title} [{ms}]")
            it = self.todo_list.item(self.todo_list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, td.id)

        self.note_list.clear()
        for n in sorted(task.notes, key=lambda x: x.created_at):
            latest_body = ""
            if n.versions:
                latest = max(n.versions, key=lambda v: v.version_seq)
                latest_body = _plain_from_html(latest.body_html)

            if n.is_system:
                title = _system_note_title(latest_body)
                suffix = f" — {_clip(latest_body, 44)}" if latest_body else ""
                label = f"(sys) {title}{suffix}"
            else:
                label = _clip(latest_body) if latest_body else "New note"

            self.note_list.addItem(label)
            it = self.note_list.item(self.note_list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, n.id)
            it.setData(Qt.ItemDataRole.UserRole + 1, n.is_system)

        self.blocker_list.clear()
        for b in task.blockers:
            state = "open" if b.cleared_at is None else "cleared"
            self.blocker_list.addItem(f"[{state}] {b.title}")
            it = self.blocker_list.item(self.blocker_list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, b.id)

        rule = task.recurring_rule
        self.rec_enable.setChecked(rule is not None)
        if rule:
            mi = self.rec_mode.findData(rule.generation_mode)
            self.rec_mode.setCurrentIndex(max(0, mi))
            self.rec_interval.setValue(rule.interval_days)
            self.rec_skip_w.setChecked(rule.skip_weekends)
            self.rec_skip_h.setChecked(rule.skip_holidays)
            lines = []
            for tmpl in sorted(rule.todo_templates, key=lambda x: x.sort_order):
                off = tmpl.milestone_offset_days
                suf = f"|{off}" if off is not None else ""
                lines.append(f"{tmpl.title}{suf}")
            self.rec_template.setPlainText("\n".join(lines))
        else:
            self.rec_template.clear()

        self._refresh_timeline()

    def _refresh_priority_label(self) -> None:
        try:
            pr = compute_priority(impact=self.f_impact.value(), urgency=self.f_urgency.value())
            self.f_priority_label.setText(priority_display(pr))
        except ValueError:
            self.f_priority_label.setText("—")

    def _save_task_detail(self) -> None:
        if self._current_task_id is None:
            QMessageBox.information(self, "Save", "Select a task first.")
            return
        due = self.f_due.date()
        due_py = _qdate_to_py(due) if due.isValid() else None
        closed = self.f_closed.date()
        closed_py = _qdate_to_py(closed) if closed.isValid() else None
        st = self.f_status.currentData()
        desc_html = self.f_description.toHtml()
        desc_plain = self.f_description.toPlainText().strip()
        if not desc_plain:
            desc_html = None
        self._svc.update_task_fields(
            self._current_task_id,
            title=self.f_title.text(),
            description=desc_html,
            status=st,
            impact=self.f_impact.value(),
            urgency=self.f_urgency.value(),
            received_date=_qdate_to_py(self.f_received.date()),
            due_date=due_py,
            closed_date=closed_py if st == TaskStatus.CLOSED else None,
        )
        self._reload_task_list()
        self._load_task_detail()
        QMessageBox.information(self, "Save", "Task saved.")

    def _close_current_task(self) -> None:
        if self._current_task_id is None:
            return
        task, new_t = self._svc.close_task(self._current_task_id)
        msg = "Task closed."
        if new_t:
            msg += f" Created successor {format_task_ticket(new_t.ticket_number)} (id {new_t.id})."
        QMessageBox.information(self, "Close", msg)
        self._reload_task_list()
        self._load_task_detail()

    def _new_task(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("New task")
        form = QFormLayout(d)
        title = QLineEdit()
        recv_row, recv = date_edit_with_today_button(d)
        recv.setDate(QDate.currentDate())
        due_row, due = date_edit_with_today_button(d)
        due.setDate(QDate.currentDate().addDays(7))
        form.addRow("Title", title)
        form.addRow("Received", recv_row)
        form.addRow("Due", due_row)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(bb)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        if d.exec() != QDialog.DialogCode.Accepted or not title.text().strip():
            return
        t = self._svc.create_task(
            title=title.text(),
            received_date=_qdate_to_py(recv.date()),
            due_date=_qdate_to_py(due.date()),
        )
        self._reload_task_list()
        for i in range(self.task_list.count()):
            it = self.task_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == t.id:
                self.task_list.setCurrentItem(it)
                break

    def _add_todo(self) -> None:
        if self._current_task_id is None:
            return
        result = run_add_todo_dialog(self)
        if result is None:
            return
        text, ms = result
        created = self._svc.add_todo(self._current_task_id, title=text, milestone_date=ms)
        self._load_task_detail()
        self._reload_task_list()
        if created is not None:
            self._select_list_item_by_id(self.todo_list, created.id)

    def _complete_todo(self) -> None:
        it = self.todo_list.currentItem()
        if not it:
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if tid:
            keep_id = int(tid)
            self._svc.complete_todo(int(tid))
            self._load_task_detail()
            self._reload_task_list()
            self._select_list_item_by_id(self.todo_list, keep_id)

    def _move_todo(self, delta: int) -> None:
        it = self.todo_list.currentItem()
        if not it:
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if not tid:
            return
        keep_id = int(tid)
        row = self.todo_list.row(it)
        self._svc.reorder_todo(int(tid), row + delta)
        self._load_task_detail()
        self._select_list_item_by_id(self.todo_list, keep_id)

    def _on_note_selected(self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if not cur:
            self.note_editor.clear()
            return
        is_sys = cur.data(Qt.ItemDataRole.UserRole + 1)
        nid = cur.data(Qt.ItemDataRole.UserRole)
        if nid is None:
            return
        note = self._session.get(
            TaskNote, int(nid), options=[joinedload(TaskNote.versions)]
        )
        if not note:
            return
        body = ""
        if note.versions:
            latest = max(note.versions, key=lambda v: v.version_seq)
            body = latest.body_html
        self.note_editor.setHtml(body)
        self.note_editor.setReadOnly(bool(is_sys))

    def _new_note(self) -> None:
        if self._current_task_id is None:
            return
        created = self._svc.add_note(self._current_task_id, body_html="<p></p>", is_system=False)
        self._load_task_detail()
        if created is not None:
            self._select_list_item_by_id(self.note_list, created.id)

    def _save_note(self) -> None:
        it = self.note_list.currentItem()
        if not it:
            return
        if it.data(Qt.ItemDataRole.UserRole + 1):
            QMessageBox.information(self, "Note", "System notes are not editable here.")
            return
        nid = it.data(Qt.ItemDataRole.UserRole)
        if nid:
            self._svc.update_note_body(int(nid), self.note_editor.toHtml())
            keep_id = int(nid)
            self._load_task_detail()
            self._select_list_item_by_id(self.note_list, keep_id)

    def _add_blocker(self) -> None:
        if self._current_task_id is None:
            return
        title, ok = QInputDialog.getText(self, "Blocker", "Title:")
        if not ok or not title.strip():
            return
        reason, ok2 = QInputDialog.getMultiLineText(self, "Blocker", "Reason (optional):", "")
        r = reason.strip() if ok2 else None
        created = self._svc.add_blocker(self._current_task_id, title=title.strip(), reason=r or None)
        self._load_task_detail()
        self._reload_task_list()
        if created is not None:
            self._select_list_item_by_id(self.blocker_list, created.id)

    def _clear_blocker(self) -> None:
        it = self.blocker_list.currentItem()
        if not it:
            return
        bid = it.data(Qt.ItemDataRole.UserRole)
        if bid:
            keep_id = int(bid)
            self._svc.clear_blocker(int(bid))
            self._load_task_detail()
            self._reload_task_list()
            self._select_list_item_by_id(self.blocker_list, keep_id)

    def _save_recurrence(self) -> None:
        if self._current_task_id is None:
            return
        if not self.rec_enable.isChecked():
            self._svc.clear_recurring_rule(self._current_task_id)
            QMessageBox.information(self, "Recurrence", "Recurring disabled for this task.")
            self._load_task_detail()
            return
        mode = self.rec_mode.currentData()
        interval = self.rec_interval.value()
        templates: list[tuple[int, str, int | None]] = []
        for i, line in enumerate(self.rec_template.toPlainText().splitlines()):
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                title_part, _, off_part = line.partition("|")
                title_part = title_part.strip()
                try:
                    off = int(off_part.strip()) if off_part.strip() else None
                except ValueError:
                    QMessageBox.warning(self, "Template", f"Bad offset in line: {line}")
                    return
            else:
                title_part = line
                off = None
            templates.append((i, title_part, off))
        self._svc.set_recurring_rule(
            self._current_task_id,
            generation_mode=mode,
            skip_weekends=self.rec_skip_w.isChecked(),
            skip_holidays=self.rec_skip_h.isChecked(),
            interval_days=interval,
            todo_templates=templates,
        )
        QMessageBox.information(self, "Recurrence", "Recurrence settings saved.")
        self._load_task_detail()

    def _refresh_timeline(self) -> None:
        if self._current_task_id is None:
            self.timeline.clear()
            return
        lines = []
        for e in self._svc.combined_timeline(self._current_task_id):
            lines.append(f"{e.at.isoformat()} [{e.kind}] {e.summary}")
            if e.detail:
                lines.append(f"    {e.detail}")
        self.timeline.setPlainText("\n".join(lines))

    def _on_calendar_date_changed(self) -> None:
        qd = self.cal_widget.selectedDate()
        day = _qdate_to_py(qd)
        evs = self._svc.calendar_events(
            include_due=self.cal_show_due.isChecked(),
            include_milestones=self.cal_show_ms.isChecked(),
            include_received=self.cal_show_recv.isChecked(),
            include_closed=self.cal_show_closed.isChecked(),
            include_closed_tasks=self.cal_include_closed_tasks.isChecked(),
            from_date=day,
            to_date=day,
        )
        self.cal_event_list.clear()
        colors = {
            "due": QColor("#1565c0"),
            "milestone": QColor("#2e7d32"),
            "received": QColor("#757575"),
            "closed": QColor("#ef6c00"),
            "holiday": QColor("#c62828"),
        }
        for ev in evs:
            pr = ev.get("priority", 5)
            label = f"P{pr} [{ev['type']}] {ev['label']}"
            item = QListWidgetItem(label)
            c = colors.get(ev["type"], QColor("#000000"))
            item.setForeground(c)
            item.setData(Qt.ItemDataRole.UserRole, ev.get("task_id"))
            self.cal_event_list.addItem(item)
        self._highlight_calendar_month()

    def _highlight_calendar_month(self) -> None:
        y, m = self.cal_widget.yearShown(), self.cal_widget.monthShown()
        blank = QTextCharFormat()
        for d in range(1, calendar.monthrange(y, m)[1] + 1):
            self.cal_widget.setDateTextFormat(QDate(y, m, d), blank)
        start = dt.date(y, m, 1)
        end = dt.date(y, m, calendar.monthrange(y, m)[1])
        evs = self._svc.calendar_events(
            include_due=self.cal_show_due.isChecked(),
            include_milestones=self.cal_show_ms.isChecked(),
            include_received=self.cal_show_recv.isChecked(),
            include_closed=self.cal_show_closed.isChecked(),
            include_closed_tasks=self.cal_include_closed_tasks.isChecked(),
            from_date=start,
            to_date=end,
        )
        fmt_dot = QTextCharFormat()
        fmt_dot.setBackground(QColor("#bbdefb"))
        seen: set[dt.date] = set()
        for ev in evs:
            d = ev["date"]
            if d in seen:
                continue
            seen.add(d)
            self.cal_widget.setDateTextFormat(_py_to_qdate(d), fmt_dot)

    def _apply_calendar_to_due(self) -> None:
        if self._current_task_id is None:
            QMessageBox.information(self, "Calendar", "Select a task on the Tasks tab first.")
            return
        day = _qdate_to_py(self.cal_widget.selectedDate())
        self._svc.update_task_fields(self._current_task_id, due_date=day)
        self._reload_task_list()
        self._on_calendar_date_changed()
        QMessageBox.information(self, "Calendar", f"Due date set to {day.isoformat()}.")

    def _run_report_overdue(self) -> None:
        rows = self._svc.report_overdue()
        lines = [f"Overdue ({len(rows)} open tasks):"]
        for t in sorted(rows, key=lambda x: (x.priority, x.due_date or dt.date.min)):
            lines.append(f"  P{t.priority} — {t.title} (due {t.due_date})")
        self.report_out.setPlainText("\n".join(lines) if lines else "None.")

    def _run_report_week(self) -> None:
        rows = self._svc.report_due_this_week()
        lines = [f"Due in next 7 days ({len(rows)}):"]
        for t in sorted(rows, key=lambda x: (x.due_date or dt.date.max, x.priority)):
            lines.append(f"  P{t.priority} — {t.title} (due {t.due_date})")
        self.report_out.setPlainText("\n".join(lines) if lines else "None.")

    def _run_report_velocity(self) -> None:
        r = self._svc.report_closure_velocity(30)
        self.report_out.setPlainText(
            f"Closed in last {r['days_window']} days (since {r['since']}): {r['closed_count']} tasks."
        )

    def _reload_holidays_list(self) -> None:
        selected = self.holiday_table.currentItem()
        selected_id = int(selected.data(Qt.ItemDataRole.UserRole)) if selected else None
        self.holiday_table.clear()
        for h in self._svc.list_holidays():
            label = h.label or ""
            self.holiday_table.addItem(f"{h.holiday_date.isoformat()}  {label}")
            it = self.holiday_table.item(self.holiday_table.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, h.id)
        if not self._select_list_item_by_id(self.holiday_table, selected_id):
            if self.holiday_table.count() > 0:
                self.holiday_table.setCurrentRow(0)

    def _add_holiday_dialog(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("Add holiday")
        lay = QVBoxLayout(d)
        form = QFormLayout()
        date_row, de = date_edit_with_today_button(d)
        de.setDate(QDate.currentDate())
        label = QLineEdit()
        form.addRow("Date", date_row)
        form.addRow("Label (optional)", label)
        lay.addLayout(form)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        lay.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        hol = _qdate_to_py(de.date())
        lbl = label.text().strip() or None
        created = self._svc.add_holiday(hol, lbl)
        if created is None:
            QMessageBox.warning(self, "Holiday", "That date already exists.")
            return
        self._reload_holidays_list()
        self._select_list_item_by_id(self.holiday_table, created.id)

    def _remove_holiday(self) -> None:
        it = self.holiday_table.currentItem()
        if not it:
            return
        hid = it.data(Qt.ItemDataRole.UserRole)
        if hid:
            self._svc.delete_holiday(int(hid))
            self._reload_holidays_list()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if not path:
            return
        self._svc.export_tasks_csv(Path(path))
        QMessageBox.information(self, "Export", "Saved.")

    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "Excel (*.xlsx)")
        if not path:
            return
        self._svc.export_tasks_excel(Path(path))
        QMessageBox.information(self, "Export", "Saved.")

    def _show_matrix(self) -> None:
        PriorityMatrixDialog(self).exec()

    def _show_user_guide(self) -> None:
        run_user_guide_dialog(self)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            "Task Tracker (WIP)\nDesktop task tracking — Python 3.11, PySide6, SQLite.",
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.close()
        if self._secure_shutdown is not None:
            self._secure_shutdown()
        super().closeEvent(event)
