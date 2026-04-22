from __future__ import annotations

import calendar
import datetime as dt
import html as htmllib
import json
import re
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy.orm import joinedload

from tasktracker.db.models import TaskNote
from tasktracker.domain.enums import RecurrenceGenerationMode, TaskStatus
from tasktracker.domain.priority import compute_priority, priority_display
from tasktracker.domain.ticket import format_task_ticket
from tasktracker.services.excel_export import (
    build_rich_workbook,
    write_reports_bundle_csvs,
)
from tasktracker.services.reporting_service import ReportingService, ReportResult
from tasktracker.services.shift_service import ShiftResult
from tasktracker.services.task_service import TaskService
from tasktracker.ui.calendar_quick_edit_dialog import run_calendar_quick_edit_dialog
from tasktracker.ui.date_format import (
    format_activity_timestamp,
    format_date as fmt_date,
    iso_string_to_display,
    reformat_iso_dates_in_text,
)
from tasktracker.ui.date_format_dialog import run_date_format_dialog
from tasktracker.ui.timezone_format_dialog import run_display_timezone_dialog
from tasktracker.ui.date_widgets import date_edit_with_today_button, qdate_is_blank
from tasktracker.ui.keyboard_shortcuts_dialog import run_keyboard_shortcuts_dialog
from tasktracker.ui.shift_scope_dialog import ShiftScopeDialog
from tasktracker.ui.priority_matrix_dialog import PriorityMatrixDialog
from tasktracker.ui.reference_data_dialog import run_manage_reference_data_dialog
from tasktracker.ui.spin_widgets import StepInvertedSpinBox
from tasktracker.ui.settings_store import (
    KNOWN_TAB_IDS,
    TASK_SECTION_LABELS,
    TASK_SECTION_PLACEMENT,
    TASK_SECTION_TAB_LABELS,
    add_saved_view,
    get_date_format_qt,
    get_display_timezone,
    get_last_tab,
    get_report_params,
    get_saved_views,
    get_theme_id,
    get_ui_text_scale,
    load_ui_settings,
    move_saved_view,
    normalize_section_order,
    remove_saved_view,
    rename_saved_view,
    save_ui_settings,
    set_date_format_qt,
    set_display_timezone,
    set_ui_text_scale,
    set_last_tab,
    set_report_params,
    set_theme_id,
)
from tasktracker.ui.dashboard import DASHBOARD_CARD_META, DashboardWidget
from tasktracker.ui.saved_views import SavedViewsWidget
from tasktracker.ui.text_scale import apply_app_text_scale, propagate_font_to_widget_tree
from tasktracker.ui.themes import apply_theme, calendar_event_colors, list_themes
from tasktracker.ui.task_panel_layout_dialog import run_task_panel_layout_dialog
from tasktracker.ui.text_scale_dialog import run_text_scale_dialog
from tasktracker.ui.todo_dialog import run_add_todo_dialog, run_edit_todo_dialog
from tasktracker.ui.user_guide_dialog import run_user_guide_dialog


def _qdate_to_py(qd: QDate) -> dt.date:
    return dt.date(qd.year(), qd.month(), qd.day())


def _py_to_qdate(d: dt.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _current_date_format_qt(settings: dict) -> str:
    """Shim so call sites don't need the longer ``get_date_format_qt`` name."""
    return get_date_format_qt(settings)


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


def _person_label(first_name: str, last_name: str, employee_id: str) -> str:
    return f"{last_name}, {first_name} ({employee_id})"


class MainWindow(QMainWindow):
    def __init__(
        self,
        session_factory,
        *,
        engine=None,
        secure_shutdown=None,
        parent=None,
        startup_notice: str | None = None,
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
        self._loading_task_form = False
        self._ui_settings = load_ui_settings()
        # Cached result of the most recent bulk shift (preview + apply
        # from ShiftService) so Edit > Undo last bulk shift can reverse
        # it. Only one level of undo is supported - the UI hides the
        # entry when this is ``None`` and overwrites it on each new
        # apply.
        self._last_bulk_shift: ShiftResult | None = None

        self._create_task_actions()
        self._build_ui()
        self._build_menu_toolbar()
        self._apply_task_action_shortcuts()
        self._reload_task_list()
        # Populate the Dashboard tab once so it isn't blank if the user
        # launched straight into it via the last-tab restore.
        self._refresh_dashboard()
        self._reapply_text_scale()

        # Deferred so the status bar exists before the message is shown.
        if startup_notice:
            QTimer.singleShot(0, lambda: self._notify(startup_notice, timeout_ms=8000))

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

    def _create_task_actions(self) -> None:
        self.act_new_task = QAction("New Task", self)
        self.act_new_task.triggered.connect(self._new_task)
        self.act_save_task = QAction("Save Task", self)
        self.act_save_task.triggered.connect(self._save_task_detail)
        self.act_close_task = QAction("Close Task", self)
        self.act_close_task.triggered.connect(self._close_current_task)

    def _apply_task_action_shortcuts(self) -> None:
        sc = self._ui_settings.get("shortcuts", {})
        ctx = Qt.ShortcutContext.ApplicationShortcut
        self.act_new_task.setShortcut(QKeySequence(sc.get("new_task", "Ctrl+N")))
        self.act_new_task.setShortcutContext(ctx)
        self.act_save_task.setShortcut(QKeySequence(sc.get("save_task", "Ctrl+S")))
        self.act_save_task.setShortcutContext(ctx)
        self.act_close_task.setShortcut(QKeySequence(sc.get("close_task", "Ctrl+Shift+C")))
        self.act_close_task.setShortcutContext(ctx)
        self._sync_task_action_tooltips()

    def _sync_task_action_tooltips(self) -> None:
        for act, label in (
            (self.act_new_task, "New Task"),
            (self.act_save_task, "Save Task"),
            (self.act_close_task, "Close Task"),
        ):
            sh = act.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            act.setToolTip(f"{label} ({sh})" if sh else label)

    def _notify(self, msg: str, *, timeout_ms: int = 4000) -> None:
        """Show a transient non-modal confirmation in the main window status bar.

        Used for routine success / gentle-nudge feedback (Task saved, Select a
        task first, etc.) in place of blocking ``QMessageBox.information``
        popups. Errors, warnings, and multi-line summaries still use
        ``QMessageBox`` so they must be acknowledged.
        """
        self.statusBar().showMessage(msg, timeout_ms)

    def _apply_task_section_order(self, order: list[str]) -> None:
        """Reorder movable section group boxes without rebuilding the tab.

        Sections flagged as "inline" in :data:`TASK_SECTION_PLACEMENT` go into
        the stacked VBox below the core fields; "tab" sections go into the
        shared :class:`QTabWidget`. Each section's order within its own
        container is preserved from ``order``; cross-container moves are a
        visual no-op (but the relative order inside each container is kept).
        """
        if not hasattr(self, "_task_sections_layout") or not hasattr(self, "_section_by_id"):
            return
        norm = normalize_section_order(order)

        while self._task_sections_layout.count():
            self._task_sections_layout.takeAt(0)
        if hasattr(self, "_sections_tabs"):
            while self._sections_tabs.count():
                self._sections_tabs.removeTab(0)

        for sid in norm:
            w = self._section_by_id.get(sid)
            if w is None:
                continue
            placement = TASK_SECTION_PLACEMENT.get(sid, "inline")
            if placement == "tab" and hasattr(self, "_sections_tabs"):
                tab_label = TASK_SECTION_TAB_LABELS.get(sid, TASK_SECTION_LABELS.get(sid, sid))
                self._sections_tabs.addTab(w, tab_label)
            else:
                self._task_sections_layout.addWidget(w)

    def _open_task_panel_layout(self) -> None:
        order = run_task_panel_layout_dialog(self, self._ui_settings["task_panel_section_order"])
        if order is None:
            return
        self._ui_settings["task_panel_section_order"] = normalize_section_order(order)
        save_ui_settings(self._ui_settings)
        self._apply_task_section_order(self._ui_settings["task_panel_section_order"])

    def _open_keyboard_shortcuts(self) -> None:
        new_sc = run_keyboard_shortcuts_dialog(self, self._ui_settings.get("shortcuts", {}))
        if new_sc is None:
            return
        self._ui_settings["shortcuts"] = new_sc
        save_ui_settings(self._ui_settings)
        self._apply_task_action_shortcuts()

    def _build_theme_menu(self, view_menu: QMenu) -> None:
        """Populate the View menu with a radio group of theme choices.

        The checked action reflects the currently-saved theme so a
        fresh launch always shows the user's chosen theme ticked.
        We use :class:`QActionGroup` in exclusive mode so Qt enforces
        radio-button behavior for us - flipping one theme automatically
        unchecks the previous one without extra bookkeeping.
        """
        theme_menu = view_menu.addMenu("&Theme")
        group = QActionGroup(self)
        group.setExclusive(True)
        current_id = get_theme_id(self._ui_settings)
        self._theme_actions: dict[str, QAction] = {}
        for theme in list_themes():
            act = QAction(theme.label, self, checkable=True)
            act.setToolTip(theme.description)
            act.setData(theme.id)
            act.setChecked(theme.id == current_id)
            # Bind the theme id into the lambda via default argument so the
            # closure doesn't capture the loop variable by reference.
            act.triggered.connect(lambda _checked, tid=theme.id: self._on_theme_selected(tid))
            group.addAction(act)
            theme_menu.addAction(act)
            self._theme_actions[theme.id] = act

    def _on_theme_selected(self, theme_id: str) -> None:
        """Persist and apply the theme chosen from the View menu.

        We update the running ``QApplication`` in place; widgets repaint
        automatically when ``setPalette`` / ``setStyleSheet`` change.
        Persisting first ensures a crash after apply still leaves the
        next launch in the intended state.
        """
        if get_theme_id(self._ui_settings) == theme_id:
            return
        set_theme_id(self._ui_settings, theme_id)
        save_ui_settings(self._ui_settings)
        app = QApplication.instance()
        theme = apply_theme(app, theme_id) if app is not None else None
        if app is not None:
            self._reapply_text_scale()
        # Calendar day shading pulls its colors from the theme's extras
        # dict (see _highlight_calendar_month); Qt's QCalendarWidget
        # doesn't repaint those tiles on palette-only changes, so we
        # reapply the date formats explicitly here. Guarded because
        # this method runs during construction before the calendar
        # tab is built.
        if hasattr(self, "cal_widget"):
            try:
                self._highlight_calendar_month()
            except Exception:
                # Theme change must never block on a calendar render
                # hiccup; the next tab-entry repaint will self-heal.
                pass
        label = theme.label if theme is not None else theme_id
        self._notify(f"Theme set to {label}.")

    def _open_date_format_settings(self) -> None:
        """Prompt for a new date format and apply it live.

        The new format is persisted before we refresh widgets so an
        exception during the refresh pass (e.g. a dialog being closed
        mid-refresh) doesn't leave settings and UI out of sync. Every
        existing ``QDateEdit`` under this window is updated in place,
        and currently-visible read-only surfaces (Reports table /
        summary, Tasks list subtitles, Holidays tab) are re-rendered
        so the change takes effect without requiring a restart.
        """
        current = get_date_format_qt(self._ui_settings)
        chosen = run_date_format_dialog(self, current)
        if chosen is None or chosen == current:
            return
        set_date_format_qt(self._ui_settings, chosen)
        save_ui_settings(self._ui_settings)
        self._apply_date_format_to_widgets()
        self._refresh_date_dependent_surfaces()
        self._notify(f"Date format set to {chosen}.")

    def _open_display_timezone_settings(self) -> None:
        current = get_display_timezone(self._ui_settings)
        chosen = run_display_timezone_dialog(self, current)
        if chosen is None or chosen == current:
            return
        set_display_timezone(self._ui_settings, chosen)
        save_ui_settings(self._ui_settings)
        self._refresh_timeline()
        self._notify(f"Display timezone set to {get_display_timezone(self._ui_settings)}.")

    def _open_text_scale_settings(self) -> None:
        current = get_ui_text_scale(self._ui_settings)
        chosen = run_text_scale_dialog(self, current)
        if chosen is None or chosen == current:
            return
        set_ui_text_scale(self._ui_settings, chosen)
        save_ui_settings(self._ui_settings)
        self._reapply_text_scale()
        pct = int(round(get_ui_text_scale(self._ui_settings) * 100))
        self._notify(f"Text size set to {pct}%.")

    def _reapply_text_scale(self) -> None:
        """Apply persisted scale, push font through the window tree, sync metrics."""
        app = QApplication.instance()
        if app is None:
            return
        apply_app_text_scale(app, get_ui_text_scale(self._ui_settings))
        propagate_font_to_widget_tree(self, app.font())
        self._apply_text_scale_surfaces()

    def _apply_text_scale_surfaces(self) -> None:
        """Resize font-derived chrome after app font or scale changes."""
        app = QApplication.instance()
        if app is None:
            return
        f = app.font()
        fm_app = QFontMetrics(f)

        if hasattr(self, "f_priority_label"):
            if hasattr(self, "f_description"):
                self.f_description.setFont(f)
                self.f_description.document().setDefaultFont(f)
            if hasattr(self, "note_editor"):
                self.note_editor.setFont(f)
                self.note_editor.document().setDefaultFont(f)

            fm = self.f_priority_label.fontMetrics()
            pd_w = max(fm.horizontalAdvance(priority_display(pr)) for pr in range(1, 6))
            self.f_priority_label.setMinimumWidth(pd_w)

            if hasattr(self, "f_description"):
                hf = self.f_description.fontMetrics().height()
                self.f_description.setMinimumHeight(max(int(round(hf * 14)), 180))
            if hasattr(self, "note_editor"):
                hn = self.note_editor.fontMetrics().height()
                self.note_editor.setMinimumHeight(max(int(round(hn * 10)), 120))
            if hasattr(self, "_sections_tabs"):
                ht = self._sections_tabs.fontMetrics().height()
                self._sections_tabs.setMinimumHeight(max(int(round(ht * 20)), 240))
            if hasattr(self, "rec_template"):
                hr = self.rec_template.fontMetrics().height()
                self.rec_template.setMaximumHeight(max(int(round(hr * 6)), 80))

            self._refresh_priority_label()

        self._sync_reports_scale_metrics(fm_app)

        if hasattr(self, "cal_widget"):
            self.cal_widget.updateGeometry()

    def _sync_reports_scale_metrics(self, fm: QFontMetrics) -> None:
        """Keep Reports tab control sizes aligned with the active font."""
        if not hasattr(self, "_report_param_widgets"):
            return
        date_min = max(int(fm.horizontalAdvance("2026-12-31") * 1.15) + 32, 96)
        if hasattr(self, "reports_list") and self.reports_list.count() > 0:
            list_label_w = max(
                fm.horizontalAdvance(self.reports_list.item(i).text())
                for i in range(self.reports_list.count())
            )
        else:
            list_label_w = fm.horizontalAdvance("Weekly status")
        combo_min = max(list_label_w, fm.horizontalAdvance("By for-person")) + 48
        combo_min = max(combo_min, 160)
        for _rid, controls in self._report_param_widgets.items():
            for w in controls.values():
                if isinstance(w, QDateEdit):
                    w.setMinimumWidth(date_min)
                elif isinstance(w, QComboBox):
                    w.setMinimumWidth(combo_min)
        if hasattr(self, "reports_summary"):
            self.reports_summary.setMaximumHeight(max(int(fm.height() * 8), 100))
        if hasattr(self, "reports_list"):
            labels = [label for _rid, label in self.REPORT_LIST]
            list_w = max(fm.horizontalAdvance(x) for x in labels) + 40
            self.reports_list.setMaximumWidth(max(list_w, 160))

    def _apply_date_format_to_widgets(self) -> None:
        """Update every ``QDateEdit`` under this window's widget tree."""
        fmt = get_date_format_qt(self._ui_settings)
        for de in self.findChildren(QDateEdit):
            de.setDisplayFormat(fmt)

    def _refresh_date_dependent_surfaces(self) -> None:
        """Re-render read-only UI surfaces that already cache formatted dates.

        Covered: the Tasks list, the Holidays list, the task detail pane
        (Next milestone label + todos table), the Reports table + summary
        panel (if a report has been run this session), and the Calendar
        day list. Status-bar messages are ephemeral so they naturally pick
        up the new format on their next call.
        """
        try:
            self._reload_task_list()
        except AttributeError:
            pass
        try:
            self._reload_holidays_list()
        except AttributeError:
            pass
        if getattr(self, "_current_task_id", None):
            try:
                self._load_task_detail()
            except AttributeError:
                pass
        if self._last_report_result is not None:
            self._render_report_result(self._last_report_result)
        # Calendar day list reflects the currently-selected day.
        try:
            self._on_calendar_date_changed()
        except AttributeError:
            pass

    def _open_reference_data_manager(self) -> None:
        run_manage_reference_data_dialog(self, self._svc)
        self._reload_task_taxonomy_inputs()

    def _export_reference_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export reference data",
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        self._svc.export_reference_data(Path(path))
        self._notify("Reference data exported.")

    def _import_reference_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import reference data",
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            summary = self._svc.import_reference_data(Path(path))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            QMessageBox.warning(self, "Reference data", f"Import failed: {exc}")
            return
        self._reload_task_taxonomy_inputs()
        QMessageBox.information(
            self,
            "Reference data",
            "Import complete.\n"
            f"Categories: {summary['categories']}\n"
            f"Sub-categories: {summary['subcategories']}\n"
            f"Areas: {summary['areas']}\n"
            f"People: {summary['people']}",
        )

    def _switch_vault(self) -> None:
        """Confirm and relaunch the app with the vault picker.

        Secure shutdown (same path as the close button) encrypts the
        active vault before we spawn a new process with ``--pick-vault``;
        that new process then runs the picker and unlocks whichever
        vault the user selects. We shut down the current Qt app after
        kicking off the relaunch so there's only ever one MainWindow
        reading from the same SQLite file.
        """
        reply = QMessageBox.question(
            self,
            "Switch vault",
            "Close this vault and relaunch with the vault picker?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Trigger the same secure shutdown close handler does, then
        # relaunch and exit. Deferred via a single-shot timer so the
        # menu click event finishes unwinding before we tear down the
        # QApplication.
        import subprocess
        import sys

        from PySide6.QtWidgets import QApplication

        def relaunch_and_quit() -> None:
            try:
                self._session.close()
            except Exception:  # pragma: no cover - defensive
                pass
            if self._secure_shutdown is not None:
                try:
                    self._secure_shutdown()
                except Exception:  # pragma: no cover - defensive
                    pass
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--pick-vault"]
            else:
                cmd = [sys.executable, "-m", "tasktracker", "--pick-vault"]
            try:
                subprocess.Popen(cmd, close_fds=True)
            except OSError:
                pass
            app = QApplication.instance()
            if app is not None:
                app.quit()

        QTimer.singleShot(0, relaunch_and_quit)

    def _build_menu_toolbar(self) -> None:
        tb = QToolBar()
        self.addToolBar(tb)
        tb.addAction(self.act_new_task)
        tb.addAction(self.act_save_task)
        tb.addAction(self.act_close_task)
        act_matrix = QAction("Priority matrix…", self)
        act_matrix.triggered.connect(self._show_matrix)
        tb.addAction(act_matrix)

        # Menus intentionally added in the standard Windows order
        # (File, Edit, View, Settings, Help) so the menu bar matches
        # muscle memory from other apps.
        m_file = self.menuBar().addMenu("&File")
        m_file.addAction("Export tasks to CSV…", self._export_csv)
        m_file.addAction("Export tasks to Excel…", self._export_excel)
        m_file.addSeparator()
        m_file.addAction("Export rich workbook (xlsx)…", self._export_rich_workbook)
        m_file.addAction("Export reports bundle (CSVs in folder)…", self._export_reports_bundle)
        m_file.addSeparator()
        m_file.addAction("Quit", self.close)

        m_edit = self.menuBar().addMenu("&Edit")
        self.act_shift_selected = QAction("Shift selected tasks…", self)
        self.act_shift_selected.triggered.connect(self._shift_selected_tasks)
        m_edit.addAction(self.act_shift_selected)
        self.act_slip_from_date = QAction("Slip schedule from date…", self)
        self.act_slip_from_date.triggered.connect(self._slip_schedule_from_date)
        m_edit.addAction(self.act_slip_from_date)
        m_edit.addSeparator()
        self.act_undo_bulk_shift = QAction("Undo last bulk shift", self)
        self.act_undo_bulk_shift.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.act_undo_bulk_shift.setShortcutContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.act_undo_bulk_shift.triggered.connect(self._undo_last_bulk_shift)
        self.act_undo_bulk_shift.setEnabled(False)
        self.act_undo_bulk_shift.setToolTip("No bulk shift to undo.")
        m_edit.addAction(self.act_undo_bulk_shift)

        m_view = self.menuBar().addMenu("&View")
        self._build_theme_menu(m_view)

        m_settings = self.menuBar().addMenu("&Settings")
        m_settings.addAction("Customize task panel layout…", self._open_task_panel_layout)
        m_settings.addAction("Keyboard shortcuts…", self._open_keyboard_shortcuts)
        m_settings.addAction("Date format…", self._open_date_format_settings)
        m_settings.addAction("Display timezone…", self._open_display_timezone_settings)
        m_settings.addAction("Text size…", self._open_text_scale_settings)
        m_settings.addSeparator()
        m_settings.addAction("Manage categories and people…", self._open_reference_data_manager)
        m_settings.addAction("Export categories and people…", self._export_reference_data)
        m_settings.addAction("Import categories and people…", self._import_reference_data)
        m_settings.addSeparator()
        m_settings.addAction("Switch vault…", self._switch_vault)

        m_help = self.menuBar().addMenu("&Help")
        m_help.addAction("User guide…", self._show_user_guide)
        m_help.addSeparator()
        m_help.addAction("About", self._about)

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        # Tracked so the Calendar tab's "Open in Tasks tab for full edit"
        # action can switch back without reaching through ``centralWidget``.
        self._tabs = tabs

        # Tab ids are stored (and read) as strings to survive
        # insertions/reorders. The index-based attributes kept below
        # remain for legacy call sites until they migrate.
        self._tab_id_to_index: dict[str, int] = {}
        self._tab_index_to_id: dict[int, str] = {}

        def add_tab(tab_id: str, widget: QWidget, label: str) -> None:
            idx = tabs.addTab(widget, label)
            self._tab_id_to_index[tab_id] = idx
            self._tab_index_to_id[idx] = tab_id

        add_tab("dashboard", self._build_dashboard_tab(), "Dashboard")
        add_tab("tasks", self._build_tasks_tab(), "Tasks")
        add_tab("calendar", self._build_calendar_tab(), "Calendar")
        add_tab("reports", self._build_reports_tab(), "Reports")
        add_tab("holidays", self._build_holidays_tab(), "Holidays")

        self._tab_index_tasks = self._tab_id_to_index["tasks"]
        self._tab_index_calendar = self._tab_id_to_index["calendar"]
        self._tab_index_dashboard = self._tab_id_to_index["dashboard"]

        # Restore last-used tab if known, else default to the Dashboard.
        last_tab = get_last_tab(self._ui_settings)
        if last_tab in self._tab_id_to_index:
            tabs.setCurrentIndex(self._tab_id_to_index[last_tab])
        tabs.currentChanged.connect(self._on_tab_changed)

    def _build_dashboard_tab(self) -> QWidget:
        self.dashboard = DashboardWidget()
        self.dashboard.show_all_clicked.connect(self._apply_dashboard_filter)
        self.dashboard.task_activated.connect(self._jump_to_task_in_tasks_tab)
        return self.dashboard

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

        self.saved_views = SavedViewsWidget()
        self.saved_views.view_applied.connect(self._apply_saved_view)
        self.saved_views.save_requested.connect(self._save_current_filters_as_view)
        self.saved_views.rename_requested.connect(self._rename_saved_view)
        self.saved_views.delete_requested.connect(self._delete_saved_view)
        self.saved_views.move_requested.connect(self._move_saved_view)
        ll.addWidget(self.saved_views)
        self._refresh_saved_views_sidebar()

        self.task_list = QListWidget()
        self.task_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.task_list.currentItemChanged.connect(self._on_task_selected)
        # Right-click on the list brings up bulk-edit actions (shift
        # dates + undo) scoped to the current multi-selection.
        self.task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.task_list.customContextMenuRequested.connect(
            self._on_task_list_context_menu
        )
        ll.addWidget(self.task_list)

        right = QScrollArea()
        right.setWidgetResizable(True)
        detail = QWidget()
        self.detail_widget = detail
        detail_root = QVBoxLayout(detail)

        act_host = QWidget()
        act_row = QHBoxLayout(act_host)
        act_cap = QLabel("Task actions")
        act_cap.setStyleSheet("font-weight: bold;")
        act_cap.setToolTip(
            "Same commands as the window toolbar, placed next to the form so you do not "
            "need to move focus to the top edge after working in the task list."
        )
        act_row.addWidget(act_cap)
        act_row.addStretch()
        for act in (self.act_new_task, self.act_save_task, self.act_close_task):
            tbtn = QToolButton()
            tbtn.setDefaultAction(act)
            act_row.addWidget(tbtn)
        detail_root.addWidget(act_host)

        core = QWidget()
        core_lay = QHBoxLayout(core)
        core_lay.setContentsMargins(0, 0, 0, 0)

        self.lbl_ticket = QLabel("—")
        self.lbl_ticket.setStyleSheet("font-weight: bold;")
        self.f_title = QLineEdit()
        self.f_description = QTextEdit()
        self.f_description.setAcceptRichText(True)
        self.f_description.setMinimumHeight(220)
        self.f_description.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.f_status = QComboBox()
        for s in TaskStatus:
            self.f_status.addItem(s.value.replace("_", " ").title(), s.value)

        self.f_impact = StepInvertedSpinBox()
        self.f_impact.setRange(1, 3)
        self.f_impact.setValue(2)
        self.f_urgency = StepInvertedSpinBox()
        self.f_urgency.setRange(1, 3)
        self.f_urgency.setValue(2)
        self.f_priority_label = QLabel("")
        _pd_w = max(
            self.f_priority_label.fontMetrics().horizontalAdvance(priority_display(pr))
            for pr in range(1, 6)
        )
        self.f_priority_label.setMinimumWidth(_pd_w)
        self.f_priority_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.f_impact.valueChanged.connect(self._refresh_priority_label)
        self.f_urgency.valueChanged.connect(self._refresh_priority_label)

        status_row = QWidget()
        status_lay = QHBoxLayout(status_row)
        status_lay.setContentsMargins(0, 0, 0, 0)
        status_lay.addWidget(self.f_status, 1)
        status_lay.addSpacing(12)
        status_lay.addWidget(QLabel("Impact"))
        status_lay.addWidget(self.f_impact)
        status_lay.addWidget(QLabel("Urgency"))
        status_lay.addWidget(self.f_urgency)
        status_lay.addWidget(QLabel("→"))
        status_lay.addWidget(self.f_priority_label)

        fmt = _current_date_format_qt(self._ui_settings)
        recv_row, self.f_received = date_edit_with_today_button(display_format=fmt)
        self.f_received.setDate(QDate.currentDate())
        due_row, self.f_due = date_edit_with_today_button(clearable=True, display_format=fmt)
        closed_row, self.f_closed = date_edit_with_today_button(
            clearable=True, blank_text="—", display_format=fmt
        )

        self.f_category = QComboBox()
        self.f_subcategory = QComboBox()
        self.f_area = QComboBox()
        self.f_person = QComboBox()
        self.f_category.currentIndexChanged.connect(self._on_category_combo_changed)
        self.f_subcategory.currentIndexChanged.connect(self._on_subcategory_combo_changed)
        self.lbl_next_ms = QLabel("—")

        left_col = QWidget()
        left_form = QFormLayout(left_col)
        left_form.setContentsMargins(0, 0, 0, 0)
        left_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        left_form.addRow("Ticket", self.lbl_ticket)
        left_form.addRow("Title", self.f_title)
        left_form.addRow("Status / I / U / P", status_row)
        left_form.addRow("Description", self.f_description)

        right_col = QWidget()
        right_form = QFormLayout(right_col)
        right_form.setContentsMargins(0, 0, 0, 0)
        right_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        right_form.addRow("Received", recv_row)
        right_form.addRow("Due", due_row)
        right_form.addRow("Closed", closed_row)
        right_form.addRow("Category", self.f_category)
        right_form.addRow("Sub-category", self.f_subcategory)
        right_form.addRow("Area", self.f_area)
        right_form.addRow("For person", self.f_person)
        right_form.addRow("Next milestone", self.lbl_next_ms)

        core_lay.addWidget(left_col, 2)
        core_lay.addWidget(right_col, 1)
        self._reload_task_taxonomy_inputs()

        self._section_by_id: dict[str, QGroupBox] = {}

        todo_box = QGroupBox("Todos (ordered)")
        todo_l = QVBoxLayout(todo_box)
        self.todo_list = QListWidget()
        self.todo_list.itemDoubleClicked.connect(lambda _it: self._edit_todo())
        todo_l.addWidget(self.todo_list)
        t_btn = QHBoxLayout()
        self.btn_todo_add = QPushButton("Add todo…")
        self.btn_todo_add.clicked.connect(self._add_todo)
        self.btn_todo_edit = QPushButton("Edit…")
        self.btn_todo_edit.setToolTip("Edit the selected todo (title / milestone). Double-click a row to do the same.")
        self.btn_todo_edit.clicked.connect(self._edit_todo)
        self.btn_todo_done = QPushButton("Mark done")
        self.btn_todo_done.clicked.connect(self._complete_todo)
        self.btn_todo_up = QPushButton("Up")
        self.btn_todo_up.clicked.connect(lambda: self._move_todo(-1))
        self.btn_todo_dn = QPushButton("Down")
        self.btn_todo_dn.clicked.connect(lambda: self._move_todo(1))
        t_btn.addWidget(self.btn_todo_add)
        t_btn.addWidget(self.btn_todo_edit)
        t_btn.addWidget(self.btn_todo_done)
        t_btn.addWidget(self.btn_todo_up)
        t_btn.addWidget(self.btn_todo_dn)
        todo_l.addLayout(t_btn)
        self._section_by_id["todos"] = todo_box

        note_box = QGroupBox("Notes (rich text)")
        note_l = QVBoxLayout(note_box)
        self.note_list = QListWidget()
        self.note_list.currentItemChanged.connect(self._on_note_selected)
        note_l.addWidget(self.note_list)
        self.note_editor = QTextEdit()
        self.note_editor.setAcceptRichText(True)
        self.note_editor.setMinimumHeight(160)
        self.note_editor.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        note_l.addWidget(self.note_editor, 1)
        n_btn = QHBoxLayout()
        self.btn_note_new = QPushButton("New note")
        self.btn_note_new.clicked.connect(self._new_note)
        self.btn_note_save = QPushButton("Save note")
        self.btn_note_save.clicked.connect(self._save_note)
        n_btn.addWidget(self.btn_note_new)
        n_btn.addWidget(self.btn_note_save)
        note_l.addLayout(n_btn)
        self._section_by_id["notes"] = note_box

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
        self._section_by_id["blockers"] = blk_box

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
        self._section_by_id["recurring"] = rec_box

        tl_box = QGroupBox("Activity (audit + notes)")
        tl_l = QVBoxLayout(tl_box)
        self.timeline = QPlainTextEdit()
        self.timeline.setReadOnly(True)
        self.timeline.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        tl_l.addWidget(self.timeline, 1)
        btn_tl = QPushButton("Refresh timeline")
        btn_tl.clicked.connect(self._refresh_timeline)
        tl_l.addWidget(btn_tl)
        self._section_by_id["activity"] = tl_box

        self._sections_host = QWidget()
        self._task_sections_layout = QVBoxLayout(self._sections_host)
        self._task_sections_layout.setContentsMargins(0, 0, 0, 0)

        self._sections_tabs = QTabWidget()
        self._sections_tabs.setDocumentMode(True)
        self._sections_tabs.setMinimumHeight(320)

        self._apply_task_section_order(self._ui_settings["task_panel_section_order"])

        detail_root.addWidget(core)
        detail_root.addWidget(self._sections_host)
        detail_root.addWidget(self._sections_tabs, 1)

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
        # Edit / jump buttons act on the highlighted event in the
        # right-hand list (or fall back to the currently-selected task on
        # the Tasks tab if the list is empty for the day). Double-clicking
        # an event row also opens the quick-edit dialog.
        self.btn_cal_quick_edit = QPushButton("Edit selected task…")
        self.btn_cal_quick_edit.setToolTip(
            "Open a focused quick-edit dialog for the highlighted task. "
            "You can also double-click the event in the list."
        )
        self.btn_cal_quick_edit.clicked.connect(self._calendar_quick_edit_selected)
        tg.addWidget(self.btn_cal_quick_edit)
        self.btn_cal_open_in_tasks = QPushButton("Open in Tasks tab")
        self.btn_cal_open_in_tasks.setToolTip(
            "Switch to the Tasks tab and select this task for full editing."
        )
        self.btn_cal_open_in_tasks.clicked.connect(self._calendar_open_in_tasks_selected)
        tg.addWidget(self.btn_cal_open_in_tasks)
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
        self.cal_event_list.itemDoubleClicked.connect(self._calendar_event_double_clicked)
        lay.addWidget(self.cal_event_list, 1)
        self._on_calendar_date_changed()
        return w

    def _calendar_go_today(self) -> None:
        today = QDate.currentDate()
        self.cal_widget.setSelectedDate(today)
        self.cal_widget.setCurrentPage(today.year(), today.month())

    # ------------------------------------------------------------------
    # Reports tab
    # ------------------------------------------------------------------

    # Display labels for the report list. Order is the order shown in the UI.
    REPORT_LIST: tuple[tuple[str, str], ...] = (
        ("wip_aging", "WIP & aging"),
        ("throughput", "Throughput"),
        ("workload", "Workload"),
        ("sla", "SLA performance"),
        ("category_mix", "Category mix"),
        ("weekly_status", "Weekly status"),
    )

    def _build_reports_tab(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)

        # Left: report picker.
        self.reports_list = QListWidget()
        for rid, label in self.REPORT_LIST:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, rid)
            self.reports_list.addItem(item)
        self.reports_list.setMaximumWidth(220)
        self.reports_list.currentRowChanged.connect(self._on_report_selected)
        outer.addWidget(self.reports_list)

        # Right: param panel + run controls + table + summary.
        right = QVBoxLayout()

        self.reports_param_stack = QStackedWidget()
        self._report_param_widgets: dict[str, dict[str, QWidget]] = {}
        for rid, _label in self.REPORT_LIST:
            page, controls = self._build_report_param_page(rid)
            self._report_param_widgets[rid] = controls
            self.reports_param_stack.addWidget(page)
        right.addWidget(self.reports_param_stack)

        # Action buttons (Run / Export / Copy).
        actions = QHBoxLayout()
        self.btn_report_run = QPushButton("Run report")
        self.btn_report_run.clicked.connect(self._run_selected_report)
        self.btn_report_export_csv = QPushButton("Export this report (CSV)…")
        self.btn_report_export_csv.clicked.connect(self._export_current_report_csv)
        self.btn_report_export_csv.setEnabled(False)
        self.btn_report_copy_summary = QPushButton("Copy summary to clipboard")
        self.btn_report_copy_summary.clicked.connect(self._copy_current_report_summary)
        self.btn_report_copy_summary.setEnabled(False)
        actions.addWidget(self.btn_report_run)
        actions.addWidget(self.btn_report_export_csv)
        actions.addWidget(self.btn_report_copy_summary)
        actions.addStretch(1)
        right.addLayout(actions)

        # Result table.
        self.reports_table = QTableWidget(0, 0)
        self.reports_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.reports_table.horizontalHeader().setStretchLastSection(True)
        self.reports_table.verticalHeader().setVisible(False)
        right.addWidget(self.reports_table, 3)

        # Summary box (compact, read-only).
        self.reports_summary = QPlainTextEdit()
        self.reports_summary.setReadOnly(True)
        self.reports_summary.setMaximumHeight(140)
        right.addWidget(self.reports_summary, 1)

        outer.addLayout(right, 1)

        # Last-rendered report cached so the export / copy buttons don't
        # re-query the database (and so the user can re-export the exact
        # rows they just saw).
        self._last_report_id: str | None = None
        self._last_report_result: ReportResult | None = None

        # Default selection: first report. This also triggers
        # ``_on_report_selected`` which restores last-used params.
        self.reports_list.setCurrentRow(0)
        return w

    def _build_report_param_page(
        self, report_id: str
    ) -> tuple[QWidget, dict[str, QWidget]]:
        """Build a single page in the Reports param stack and return the
        page widget plus a dict of named controls so the run handler can
        read the current values back out without touching the layout."""
        page = QWidget()
        form = QFormLayout(page)
        # Labels align right so the short input pills below them line up
        # tidily in column 2, and the row doesn't stretch the field to the
        # full width of the (wide) Reports pane.
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        controls: dict[str, QWidget] = {}
        today = QDate.currentDate()
        first_of_month = QDate(today.year(), today.month(), 1)
        fmt = _current_date_format_qt(self._ui_settings)

        def _compact(w: QWidget) -> QWidget:
            """Wrap ``w`` so its form row sits at its natural size with a
            trailing stretch, instead of stretching across the whole pane.
            Keeps the calendar-popup button right next to the field."""
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(w)
            lay.addStretch(1)
            return row

        if report_id in ("wip_aging", "workload", "weekly_status"):
            de = QDateEdit(today)
            de.setCalendarPopup(True)
            de.setDisplayFormat(fmt)
            de.setMinimumWidth(140)
            controls["as_of"] = de
            form.addRow("As of:", _compact(de))
        elif report_id in ("throughput", "sla", "category_mix"):
            de_from = QDateEdit(first_of_month)
            de_from.setCalendarPopup(True)
            de_from.setDisplayFormat(fmt)
            de_from.setMinimumWidth(140)
            de_to = QDateEdit(today)
            de_to.setCalendarPopup(True)
            de_to.setDisplayFormat(fmt)
            de_to.setMinimumWidth(140)
            controls["from"] = de_from
            controls["to"] = de_to
            form.addRow("From:", _compact(de_from))
            form.addRow("To:", _compact(de_to))
            if report_id == "throughput":
                period = QComboBox()
                period.addItem("Weekly (Mon-Sun)", "week")
                period.addItem("Monthly", "month")
                period.setMinimumWidth(180)
                controls["period"] = period
                form.addRow("Period:", _compact(period))
                grp = QComboBox()
                grp.addItem("No split", "none")
                grp.addItem("By category", "category")
                grp.addItem("By for-person", "for_person")
                grp.setMinimumWidth(180)
                controls["group_by"] = grp
                form.addRow("Group by:", _compact(grp))
        else:  # defensive: unknown report -> empty page
            form.addRow(QLabel("(no parameters)"))
        return page, controls

    def _current_report_id(self) -> str | None:
        item = self.reports_list.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def _on_report_selected(self, _row: int) -> None:
        rid = self._current_report_id()
        if rid is None:
            return
        index = next((i for i, (r, _l) in enumerate(self.REPORT_LIST) if r == rid), 0)
        self.reports_param_stack.setCurrentIndex(index)
        self._restore_report_params(rid)

    def _restore_report_params(self, report_id: str) -> None:
        params = get_report_params(self._ui_settings, report_id)
        if not params:
            return
        controls = self._report_param_widgets.get(report_id, {})

        def _apply_date(key: str) -> None:
            raw = params.get(key)
            if isinstance(raw, str):
                try:
                    d = dt.date.fromisoformat(raw)
                except ValueError:
                    return
                w = controls.get(key)
                if isinstance(w, QDateEdit):
                    w.setDate(_py_to_qdate(d))

        for key in ("as_of", "from", "to"):
            if key in controls:
                _apply_date(key)
        for combo_key in ("period", "group_by"):
            w = controls.get(combo_key)
            raw = params.get(combo_key)
            if isinstance(w, QComboBox) and isinstance(raw, str):
                idx = w.findData(raw)
                if idx >= 0:
                    w.setCurrentIndex(idx)

    def _collect_report_params(self, report_id: str) -> dict[str, object]:
        controls = self._report_param_widgets.get(report_id, {})
        out: dict[str, object] = {}
        for key, w in controls.items():
            if isinstance(w, QDateEdit):
                out[key] = _qdate_to_py(w.date()).isoformat()
            elif isinstance(w, QComboBox):
                out[key] = w.currentData()
        return out

    def _run_selected_report(self) -> None:
        rid = self._current_report_id()
        if rid is None:
            self._notify("Pick a report first.")
            return
        params = self._collect_report_params(rid)
        # Persist last-used params for this report so the next session opens
        # to the same view; failures here are non-fatal.
        try:
            set_report_params(self._ui_settings, rid, params)
            save_ui_settings(self._ui_settings)
        except OSError:
            pass

        rs = ReportingService(self._svc.session)
        try:
            result = self._dispatch_report(rs, rid, params)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Report failed", str(exc))
            return

        self._last_report_id = rid
        self._last_report_result = result
        self._render_report_result(result)
        self.btn_report_export_csv.setEnabled(True)
        self.btn_report_copy_summary.setEnabled(True)
        self._notify(f"{result.name}: {len(result.rows)} row(s).")

    def _dispatch_report(
        self, rs: ReportingService, report_id: str, params: dict[str, object]
    ) -> ReportResult:
        def _date(key: str, default: dt.date) -> dt.date:
            raw = params.get(key)
            if isinstance(raw, str):
                try:
                    return dt.date.fromisoformat(raw)
                except ValueError:
                    return default
            return default

        today = dt.date.today()
        if report_id == "wip_aging":
            return rs.wip_aging(as_of=_date("as_of", today))
        if report_id == "workload":
            return rs.workload(as_of=_date("as_of", today))
        if report_id == "weekly_status":
            return rs.weekly_status(as_of=_date("as_of", today))
        if report_id == "throughput":
            period = params.get("period") or "week"
            group_by = params.get("group_by") or "none"
            return rs.throughput(
                from_date=_date("from", today.replace(day=1)),
                to_date=_date("to", today),
                period=str(period),
                group_by=str(group_by),
            )
        if report_id == "sla":
            return rs.sla(
                from_date=_date("from", today.replace(day=1)),
                to_date=_date("to", today),
            )
        if report_id == "category_mix":
            return rs.category_mix(
                from_date=_date("from", today.replace(day=1)),
                to_date=_date("to", today),
            )
        raise ValueError(f"Unknown report id: {report_id}")

    def _render_report_result(self, result: ReportResult) -> None:
        cols = result.columns
        self.reports_table.clear()
        self.reports_table.setColumnCount(len(cols))
        self.reports_table.setHorizontalHeaderLabels(cols)
        self.reports_table.setRowCount(len(result.rows))
        # Reports ship date cells as ISO strings so the CSV / Excel exports
        # stay unambiguous; for the on-screen table we reformat any
        # ``YYYY-MM-DD`` values to the user's chosen display format.
        fmt = _current_date_format_qt(self._ui_settings)
        for r, row in enumerate(result.rows):
            for c, key in enumerate(cols):
                value = row.get(key, "")
                if value is None:
                    text = ""
                elif isinstance(value, str):
                    text = iso_string_to_display(value, fmt)
                else:
                    text = str(value)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.reports_table.setItem(r, c, item)
        self.reports_table.resizeColumnsToContents()
        self.reports_summary.setPlainText(
            reformat_iso_dates_in_text(result.summary or "", fmt)
        )

    def _export_current_report_csv(self) -> None:
        if self._last_report_result is None:
            self._notify("Run a report first.")
            return
        result = self._last_report_result
        suggested = f"{self._last_report_id or 'report'}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export report to CSV", suggested, "CSV (*.csv)"
        )
        if not path:
            return
        try:
            import csv

            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=result.columns)
                writer.writeheader()
                for row in result.rows:
                    writer.writerow({k: row.get(k, "") for k in result.columns})
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self._notify(f"Exported {len(result.rows)} row(s) to CSV.")

    def _copy_current_report_summary(self) -> None:
        if self._last_report_result is None:
            self._notify("Run a report first.")
            return
        text = self._last_report_result.summary or self._last_report_result.name
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(text)
        self._notify("Summary copied to clipboard.")

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

    @staticmethod
    def _combo_current_int(combo: QComboBox) -> int | None:
        raw = combo.currentData()
        return int(raw) if raw is not None else None

    def _on_category_combo_changed(self, *_args) -> None:
        if self._loading_task_form:
            return
        cat_id = self._combo_current_int(self.f_category)
        self._populate_subcategory_combo(cat_id, selected_sub_id=None)
        self._populate_area_combo(None, selected_area_id=None)

    def _on_subcategory_combo_changed(self, *_args) -> None:
        if self._loading_task_form:
            return
        sub_id = self._combo_current_int(self.f_subcategory)
        self._populate_area_combo(sub_id, selected_area_id=None)

    def _populate_subcategory_combo(
        self, category_id: int | None, *, selected_sub_id: int | None
    ) -> None:
        self.f_subcategory.blockSignals(True)
        self.f_subcategory.clear()
        self.f_subcategory.addItem("— None —", None)
        if category_id is not None:
            for sub in self._svc.list_subcategories(category_id):
                self.f_subcategory.addItem(sub.name, sub.id)
        idx = self.f_subcategory.findData(selected_sub_id)
        self.f_subcategory.setCurrentIndex(idx if idx >= 0 else 0)
        self.f_subcategory.blockSignals(False)

    def _populate_area_combo(self, subcategory_id: int | None, *, selected_area_id: int | None) -> None:
        self.f_area.clear()
        self.f_area.addItem("— None —", None)
        if subcategory_id is not None:
            for area in self._svc.list_areas(subcategory_id):
                self.f_area.addItem(area.name, area.id)
        idx = self.f_area.findData(selected_area_id)
        self.f_area.setCurrentIndex(idx if idx >= 0 else 0)

    def _reload_task_taxonomy_inputs(self, task=None) -> None:
        """Reload category/subcategory/area/person combos from vault master data."""
        selected_person = self._combo_current_int(self.f_person) if hasattr(self, "f_person") else None
        selected_area = self._combo_current_int(self.f_area) if hasattr(self, "f_area") else None
        selected_sub = self._combo_current_int(self.f_subcategory) if hasattr(self, "f_subcategory") else None
        selected_cat = self._combo_current_int(self.f_category) if hasattr(self, "f_category") else None

        if task is not None and getattr(task, "area", None) is not None:
            selected_area = task.area.id
            selected_sub = task.area.subcategory.id
            selected_cat = task.area.subcategory.category.id
        if task is not None:
            selected_person = task.person.id if task.person is not None else None

        self._loading_task_form = True
        self.f_category.clear()
        self.f_category.addItem("— None —", None)
        for cat in self._svc.list_categories():
            self.f_category.addItem(cat.name, cat.id)
        cidx = self.f_category.findData(selected_cat)
        self.f_category.setCurrentIndex(cidx if cidx >= 0 else 0)

        category_id = self._combo_current_int(self.f_category)
        self._populate_subcategory_combo(category_id, selected_sub_id=selected_sub)
        subcategory_id = self._combo_current_int(self.f_subcategory)
        self._populate_area_combo(subcategory_id, selected_area_id=selected_area)

        self.f_person.clear()
        self.f_person.addItem("— None —", None)
        for p in self._svc.list_people():
            self.f_person.addItem(_person_label(p.first_name, p.last_name, p.employee_id), p.id)
        pidx = self.f_person.findData(selected_person)
        self.f_person.setCurrentIndex(pidx if pidx >= 0 else 0)
        self._loading_task_form = False

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

    # ------------------------------------------------------------------
    # Dashboard + saved views (plan 01)
    # ------------------------------------------------------------------
    # Mapping from dashboard card id to the Tasks-tab filter payload
    # that recreates the card's query when the user clicks "Show all".
    # Keys match the checkbox attribute names on MainWindow.
    _DASHBOARD_FILTERS: dict[str, dict[str, object]] = {
        "overdue": {
            "search_text": "",
            "search_fields": ["title"],
            "hide_closed": True,
            "_bucket": "overdue",
        },
        "due_today": {
            "search_text": "",
            "search_fields": ["title"],
            "hide_closed": True,
            "_bucket": "due_today",
        },
        "due_this_week": {
            "search_text": "",
            "search_fields": ["title"],
            "hide_closed": True,
            "_bucket": "due_this_week",
        },
        "blocked": {
            "search_text": "",
            "search_fields": ["title"],
            "hide_closed": True,
            "_bucket": "blocked",
        },
        "top_priority": {
            "search_text": "",
            "search_fields": ["title"],
            "hide_closed": True,
            "_bucket": "top_priority",
        },
    }

    # Mapping from dashboard card id to the Tasks-tab status notice
    # shown when the user applies the card's filter. Lets the user see
    # which card they're drilling into without scrolling back up.
    _DASHBOARD_LABELS: dict[str, str] = {cid: title for cid, title, _ in DASHBOARD_CARD_META}

    def _refresh_dashboard(self) -> None:
        if not hasattr(self, "dashboard"):
            return
        sections = self._svc.dashboard_sections()
        self.dashboard.refresh(sections, date_format=_current_date_format_qt(self._ui_settings))

    def _current_filter_state(self) -> dict[str, object]:
        """Return a saved-view-shaped snapshot of the Tasks tab filter bar."""
        fields = sorted(self._search_field_names())
        return {
            "search_text": self.search_edit.text(),
            "search_fields": fields,
            "hide_closed": bool(self.chk_hide_closed.isChecked()),
        }

    def _apply_filter_state(self, state: dict[str, object]) -> None:
        """Apply a saved-view filter payload to the Tasks tab widgets.

        Unknown keys are ignored so older saved views remain usable
        when the schema grows. The call reloads the task list exactly
        once after every control is updated to avoid flicker.
        """
        # Temporarily suppress the hide_closed reload side effect so we
        # don't trigger two back-to-back list rebuilds.
        self.chk_hide_closed.blockSignals(True)
        try:
            hide_closed = state.get("hide_closed")
            if isinstance(hide_closed, bool):
                self.chk_hide_closed.setChecked(hide_closed)
            text = state.get("search_text")
            if isinstance(text, str):
                self.search_edit.setText(text)
            raw_fields = state.get("search_fields")
            if isinstance(raw_fields, list):
                wanted = {str(f) for f in raw_fields if isinstance(f, str)}
                field_widgets = {
                    "title": self.search_title,
                    "description": self.search_description,
                    "notes": self.search_notes,
                    "todos": self.search_todos,
                    "blockers": self.search_blockers,
                    "audit": self.search_audit,
                    "ticket": self.search_ticket,
                }
                for name, widget in field_widgets.items():
                    widget.setChecked(name in wanted)
        finally:
            self.chk_hide_closed.blockSignals(False)
        self._reload_task_list()

    def _apply_dashboard_filter(self, card_id: str) -> None:
        payload = dict(self._DASHBOARD_FILTERS.get(card_id, {}))
        if not payload:
            return
        bucket = payload.pop("_bucket", None)
        self._apply_filter_state(payload)
        self._filter_tasks_to_dashboard_bucket(bucket if isinstance(bucket, str) else None)
        self._tabs.setCurrentIndex(self._tab_index_tasks)
        label = self._DASHBOARD_LABELS.get(card_id, card_id)
        self._notify(f"Tasks filtered to: {label}.")

    def _filter_tasks_to_dashboard_bucket(self, bucket: str | None) -> None:
        """Shrink the task list to rows matching a dashboard bucket.

        The Tasks tab's existing filter bar cannot express predicates
        like "due_date < today", so instead of inventing new controls
        (which would widen the saved-view schema for one card each) we
        post-filter the list items in place. The visible result
        matches the card's count and is reversible by clearing the
        search box.
        """
        if bucket is None:
            return
        sections = self._svc.dashboard_sections()
        payload = sections.get(bucket) or {}
        ids = {int(t.id) for t in (payload.get("rows") or [])}
        # If the total exceeds the prefetched top N, widen ``ids`` by
        # recomputing from the full bucket so "Show all" really shows
        # all matches, not just the top N the card rendered.
        if int(payload.get("count", 0)) > len(ids):
            ids = self._dashboard_bucket_full_ids(bucket)
        for i in range(self.task_list.count()):
            item = self.task_list.item(i)
            tid = item.data(Qt.ItemDataRole.UserRole)
            visible = isinstance(tid, int) and tid in ids
            item.setHidden(not visible)

    def _dashboard_bucket_full_ids(self, bucket: str) -> set[int]:
        """Return every task id that belongs to ``bucket`` right now."""
        sections = self._svc.dashboard_sections(top_n=10_000)
        payload = sections.get(bucket) or {}
        return {int(t.id) for t in (payload.get("rows") or [])}

    def _refresh_saved_views_sidebar(self) -> None:
        if not hasattr(self, "saved_views"):
            return
        self.saved_views.set_views(get_saved_views(self._ui_settings))

    def _find_saved_view(self, name: str) -> dict[str, object] | None:
        key = name.casefold()
        for view in get_saved_views(self._ui_settings):
            if view["name"].casefold() == key:
                return view
        return None

    def _apply_saved_view(self, name: str) -> None:
        view = self._find_saved_view(name)
        if view is None:
            self._notify(f"Saved view \"{name}\" no longer exists.")
            self._refresh_saved_views_sidebar()
            return
        filters = view.get("filters")
        if isinstance(filters, dict):
            self._apply_filter_state(filters)
        self._notify(f"Saved view applied: {view['name']}.")

    def _save_current_filters_as_view(self) -> None:
        default = ""
        current = self.saved_views.selected_name()
        if current:
            default = current
        name, ok = QInputDialog.getText(
            self,
            "Save view",
            "Name for this view:",
            text=default,
        )
        if not ok:
            return
        trimmed = name.strip()
        if not trimmed:
            self._notify("Saved view name cannot be empty.")
            return
        filters = self._current_filter_state()
        if self._find_saved_view(trimmed) is not None:
            reply = QMessageBox.question(
                self,
                "Replace saved view?",
                f"\"{trimmed}\" already exists. Replace its filters with the current ones?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        stored = add_saved_view(self._ui_settings, trimmed, filters)
        if stored is None:
            self._notify("Could not save that view (name invalid).")
            return
        save_ui_settings(self._ui_settings)
        self._refresh_saved_views_sidebar()
        self._notify(f"Saved view: {stored['name']}.")

    def _rename_saved_view(self, old_name: str) -> None:
        new_name, ok = QInputDialog.getText(
            self,
            "Rename saved view",
            "New name:",
            text=old_name,
        )
        if not ok:
            return
        trimmed = new_name.strip()
        if not trimmed:
            self._notify("Saved view name cannot be empty.")
            return
        if trimmed.casefold() == old_name.casefold():
            # Casing-only rename still proceeds below.
            pass
        if rename_saved_view(self._ui_settings, old_name, trimmed):
            save_ui_settings(self._ui_settings)
            self._refresh_saved_views_sidebar()
            self._notify(f"Renamed \"{old_name}\" to \"{trimmed}\".")
        else:
            self._notify(
                f"Could not rename \"{old_name}\" - the target name may already be taken."
            )

    def _delete_saved_view(self, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete saved view?",
            f"Delete saved view \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if remove_saved_view(self._ui_settings, name):
            save_ui_settings(self._ui_settings)
            self._refresh_saved_views_sidebar()
            self._notify(f"Deleted saved view \"{name}\".")

    def _move_saved_view(self, name: str, delta: int) -> None:
        if move_saved_view(self._ui_settings, name, delta):
            save_ui_settings(self._ui_settings)
            self._refresh_saved_views_sidebar()

    def _on_tab_changed(self, index: int) -> None:
        tab_id = self._tab_index_to_id.get(index)
        if tab_id is None:
            return
        # Refresh the dashboard on entry so it can't show stale
        # counts after a save/close action elsewhere in the app.
        if tab_id == "dashboard":
            self._refresh_dashboard()
        # Persist the last-used tab so the next launch lands here.
        set_last_tab(self._ui_settings, tab_id)
        save_ui_settings(self._ui_settings)

    def _reload_task_list(self) -> None:
        saved_id = self._current_task_id
        self.task_list.blockSignals(True)
        try:
            self.task_list.clear()
            fmt = _current_date_format_qt(self._ui_settings)
            for t in self._tasks_for_sidebar():
                pr = priority_display(t.priority)
                due = fmt_date(t.due_date, fmt) if t.due_date else "no due"
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
        self._reload_task_taxonomy_inputs()

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
            self.f_due.setDate(self.f_due.minimumDate())
        if task.closed_date:
            self.f_closed.setDate(_py_to_qdate(task.closed_date))
        else:
            self.f_closed.setDate(self.f_closed.minimumDate())
        fmt = _current_date_format_qt(self._ui_settings)
        self.lbl_next_ms.setText(
            fmt_date(task.next_milestone_date, fmt) if task.next_milestone_date else "—"
        )

        self.todo_list.clear()
        for td in sorted(task.todos, key=lambda x: x.sort_order):
            ms = fmt_date(td.milestone_date, fmt) if td.milestone_date else ""
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

        self._reload_task_taxonomy_inputs(task)
        self._refresh_timeline()

    def _refresh_priority_label(self) -> None:
        try:
            pr = compute_priority(impact=self.f_impact.value(), urgency=self.f_urgency.value())
            self.f_priority_label.setText(priority_display(pr))
        except ValueError:
            self.f_priority_label.setText("—")

    def _save_task_detail(self) -> None:
        if self._current_task_id is None:
            self._notify("Select a task first.")
            return
        due_py = None if qdate_is_blank(self.f_due) else _qdate_to_py(self.f_due.date())
        closed_py = (
            None if qdate_is_blank(self.f_closed) else _qdate_to_py(self.f_closed.date())
        )
        st = self.f_status.currentData()
        desc_html = self.f_description.toHtml()
        desc_plain = self.f_description.toPlainText().strip()
        if not desc_plain:
            desc_html = None

        existing = self._svc.get_task(self._current_task_id)
        was_closed = existing is not None and existing.status == TaskStatus.CLOSED
        closing_now = (st == TaskStatus.CLOSED) and not was_closed

        self._svc.update_task_fields(
            self._current_task_id,
            title=self.f_title.text(),
            description=desc_html,
            status=None if closing_now else st,
            impact=self.f_impact.value(),
            urgency=self.f_urgency.value(),
            received_date=_qdate_to_py(self.f_received.date()),
            due_date=due_py,
            closed_date=closed_py if (st == TaskStatus.CLOSED and not closing_now) else None,
            area_id=self._combo_current_int(self.f_area),
            person_id=self._combo_current_int(self.f_person),
        )

        new_t = None
        if closing_now:
            _, new_t = self._svc.close_task(self._current_task_id, closed_on=closed_py)

        self._reload_task_list()
        self._load_task_detail()
        if closing_now:
            msg = "Task closed."
            if new_t is not None:
                msg += f" Created successor {format_task_ticket(new_t.ticket_number)} (id {new_t.id})."
            self._notify(msg, timeout_ms=6000)
        else:
            self._notify("Task saved.")

    def _close_current_task(self) -> None:
        if self._current_task_id is None:
            return
        task, new_t = self._svc.close_task(self._current_task_id)
        msg = "Task closed."
        if new_t:
            msg += f" Created successor {format_task_ticket(new_t.ticket_number)} (id {new_t.id})."
        self._notify(msg, timeout_ms=6000)
        self._reload_task_list()
        self._load_task_detail()

    def _new_task(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("New Task")
        form = QFormLayout(d)
        fmt = _current_date_format_qt(self._ui_settings)
        title = QLineEdit()
        recv_row, recv = date_edit_with_today_button(d, display_format=fmt)
        recv.setDate(QDate.currentDate())
        due_row, due = date_edit_with_today_button(d, clearable=True, display_format=fmt)
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
            due_date=None if qdate_is_blank(due) else _qdate_to_py(due.date()),
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

    def _edit_todo(self) -> None:
        it = self.todo_list.currentItem()
        if not it:
            self._notify("Select a todo to edit.")
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if not tid:
            return
        current = self._svc.get_todo(int(tid))
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
        self._svc.update_todo(int(tid), title=new_title, milestone_date=new_ms)
        self._load_task_detail()
        self._reload_task_list()
        self._select_list_item_by_id(self.todo_list, int(tid))
        self._notify("Todo updated.")

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
            self._notify("System notes are not editable here.")
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
            self._notify("Recurring disabled for this task.")
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
        self._notify("Recurrence settings saved.")
        self._load_task_detail()

    def _refresh_timeline(self) -> None:
        if self._current_task_id is None:
            self.timeline.clear()
            return
        lines = []
        tz_key = get_display_timezone(self._ui_settings)
        for e in self._svc.combined_timeline(self._current_task_id):
            ts = format_activity_timestamp(e.at, tz_key)
            lines.append(f"{ts} [{e.kind}] {e.summary}")
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
        # Event-day shading is theme-aware: using a fixed pale-blue
        # background meant that on the Dark theme, Fusion's light-gray
        # day digits faded into the highlight so the user could not
        # tell which day of the month was flagged without visually
        # counting from an unflagged neighbour. Pulling colors from the
        # active theme lets each palette choose a highlight that has
        # enough contrast for its own day-text color.
        bg_hex, fg_hex = calendar_event_colors(get_theme_id(self._ui_settings))
        fmt_dot = QTextCharFormat()
        fmt_dot.setBackground(QColor(bg_hex))
        fmt_dot.setForeground(QColor(fg_hex))
        seen: set[dt.date] = set()
        for ev in evs:
            d = ev["date"]
            if d in seen:
                continue
            seen.add(d)
            self.cal_widget.setDateTextFormat(_py_to_qdate(d), fmt_dot)

    def _apply_calendar_to_due(self) -> None:
        if self._current_task_id is None:
            self._notify("Select a task on the Tasks tab first.")
            return
        day = _qdate_to_py(self.cal_widget.selectedDate())
        self._svc.update_task_fields(self._current_task_id, due_date=day)
        self._reload_task_list()
        self._on_calendar_date_changed()
        self._notify(f"Due date set to {fmt_date(day, _current_date_format_qt(self._ui_settings))}.")

    # -- Calendar -> task editing ---------------------------------------

    def _calendar_selected_task_id(self) -> int | None:
        """Return the task id for the highlighted event in the calendar's
        right-hand list, or ``None`` when no event row is selected."""
        item = self.cal_event_list.currentItem()
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        return int(raw) if raw is not None else None

    def _calendar_event_double_clicked(self, item: QListWidgetItem) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if raw is None:
            return
        self._open_calendar_quick_edit(int(raw))

    def _calendar_quick_edit_selected(self) -> None:
        tid = self._calendar_selected_task_id()
        if tid is None:
            self._notify("Pick an event in the day list first.")
            return
        self._open_calendar_quick_edit(tid)

    def _calendar_open_in_tasks_selected(self) -> None:
        tid = self._calendar_selected_task_id()
        if tid is None:
            self._notify("Pick an event in the day list first.")
            return
        self._jump_to_task_in_tasks_tab(tid)

    def _open_calendar_quick_edit(self, task_id: int) -> None:
        """Open the quick-edit modal for the given task. After save, refresh
        both the calendar list and the Tasks-tab list. If the user clicked
        the dialog's "Open in Tasks tab for full edit" link instead, jump
        to the Tasks tab and select the task there."""
        saved, successor, open_full = run_calendar_quick_edit_dialog(
            self,
            self._svc,
            task_id,
            display_timezone=get_display_timezone(self._ui_settings),
        )
        if open_full:
            self._jump_to_task_in_tasks_tab(task_id)
            return
        if not saved:
            return
        self._reload_task_list()
        self._on_calendar_date_changed()
        if successor is not None:
            ticket = format_task_ticket(successor.ticket_number)
            self._notify(
                f"Task closed. Created successor {ticket} (id {successor.id}).",
                timeout_ms=6000,
            )
        else:
            self._notify("Task saved.")

    def _jump_to_task_in_tasks_tab(self, task_id: int) -> None:
        """Switch the central tab widget to the Tasks tab and highlight
        ``task_id`` in the task list. No-op (with a status notification)
        when the task can't be found - e.g. it was filtered out by the
        current search/closed-only toggle."""
        self._tabs.setCurrentIndex(self._tab_index_tasks)
        if not self._select_list_item_by_id(self.task_list, task_id):
            self._notify(
                "Task not visible in current Tasks list (try clearing search filters)."
            )

    def _reload_holidays_list(self) -> None:
        selected = self.holiday_table.currentItem()
        selected_id = int(selected.data(Qt.ItemDataRole.UserRole)) if selected else None
        self.holiday_table.clear()
        fmt = _current_date_format_qt(self._ui_settings)
        for h in self._svc.list_holidays():
            label = h.label or ""
            self.holiday_table.addItem(f"{fmt_date(h.holiday_date, fmt)}  {label}")
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
        date_row, de = date_edit_with_today_button(d, display_format=_current_date_format_qt(self._ui_settings))
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
        self._notify("CSV export saved.")

    def _export_excel(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "", "Excel (*.xlsx)")
        if not path:
            return
        self._svc.export_tasks_excel(Path(path))
        self._notify("Excel export saved.")

    def _export_rich_workbook(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export rich workbook",
            "task_tracker_workbook.xlsx",
            "Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            written = build_rich_workbook(self._svc.session, Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Workbook export failed", str(exc))
            return
        self._notify(f"Rich workbook saved: {written.name}", timeout_ms=6000)

    def _export_reports_bundle(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose folder for reports bundle"
        )
        if not folder:
            return
        try:
            written = write_reports_bundle_csvs(self._svc.session, Path(folder))
        except OSError as exc:
            QMessageBox.warning(self, "Reports bundle failed", str(exc))
            return
        self._notify(
            f"Reports bundle saved: {len(written)} CSV(s) in {folder}",
            timeout_ms=6000,
        )

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

    # ------------------------------------------------------------------
    # Bulk-shift entry points
    # ------------------------------------------------------------------

    def _selected_task_ids(self) -> list[int]:
        """Return task ids for every currently highlighted row in the
        Tasks-tab list (respecting the multi-select mode)."""
        ids: list[int] = []
        for it in self.task_list.selectedItems():
            raw = it.data(Qt.ItemDataRole.UserRole)
            if raw is not None:
                ids.append(int(raw))
        return ids

    def _on_task_list_context_menu(self, point) -> None:
        """Show a right-click menu with bulk-shift actions anchored at
        the cursor's position inside the task list."""
        menu = QMenu(self.task_list)
        ids = self._selected_task_ids()
        act_shift = menu.addAction(f"Shift dates… ({len(ids)} selected)")
        act_shift.setEnabled(bool(ids))
        act_shift.triggered.connect(self._shift_selected_tasks)
        menu.addSeparator()
        act_undo = menu.addAction("Undo last bulk shift")
        act_undo.setEnabled(self._last_bulk_shift is not None)
        act_undo.triggered.connect(self._undo_last_bulk_shift)
        menu.exec(self.task_list.mapToGlobal(point))

    def _shift_selected_tasks(self) -> None:
        ids = self._selected_task_ids()
        if not ids:
            self._notify("Select one or more tasks first.")
            return
        dlg = ShiftScopeDialog(self, self._svc, mode="tasks", task_ids=ids)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.applied_result is not None:
            self._record_bulk_shift(dlg.applied_result)
            self._reload_task_list()
            self._load_task_detail()
            self._on_calendar_date_changed()

    def _slip_schedule_from_date(self) -> None:
        dlg = ShiftScopeDialog(self, self._svc, mode="slip")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.applied_result is not None:
            self._record_bulk_shift(dlg.applied_result)
            self._reload_task_list()
            self._load_task_detail()
            self._on_calendar_date_changed()

    def _undo_last_bulk_shift(self) -> None:
        if self._last_bulk_shift is None:
            self._notify("Nothing to undo.")
            return
        from tasktracker.services.shift_service import ShiftService

        ss = ShiftService(self._svc.session)
        try:
            ss.undo_shift(self._last_bulk_shift)
        except Exception as exc:
            QMessageBox.warning(self, "Undo failed", str(exc))
            return
        self._notify(
            f"Undid bulk shift {self._last_bulk_shift.shift_id} "
            f"({self._last_bulk_shift.changed_row_count} row(s) reverted)."
        )
        self._last_bulk_shift = None
        self.act_undo_bulk_shift.setEnabled(False)
        self.act_undo_bulk_shift.setToolTip("No bulk shift to undo.")
        self._reload_task_list()
        self._load_task_detail()
        self._on_calendar_date_changed()

    def record_bulk_shift(self, result: ShiftResult) -> None:
        """Public alias for ``_record_bulk_shift`` - used by dialogs
        that want to feed their own shift results into the undo slot
        (e.g. the calendar quick-edit's selection-shift strip)."""
        self._record_bulk_shift(result)

    def _record_bulk_shift(self, result: ShiftResult) -> None:
        self._last_bulk_shift = result
        self.act_undo_bulk_shift.setEnabled(True)
        self.act_undo_bulk_shift.setToolTip(result.describe())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._session.close()
        if self._secure_shutdown is not None:
            self._secure_shutdown()
        super().closeEvent(event)
