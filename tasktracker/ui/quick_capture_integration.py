"""System tray + global hotkey for quick capture (plan 05)."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from tasktracker.domain.ticket import format_task_ticket
from tasktracker.services.task_service import TaskService
from tasktracker.ui.quick_capture_dialog import run_quick_capture_dialog
from tasktracker.ui.settings_store import get_date_format_qt
from tasktracker.ui.win_hotkey import WindowsGlobalHotkey


class QuickCaptureIntegration(QObject):
    """Tray menu, optional global hotkey, and quit policy for background capture."""

    def __init__(
        self,
        app: QApplication,
        main_window: Any,
        session_factory: Callable[[], Any],
        vault_root: Any,
    ) -> None:
        super().__init__(parent=main_window)
        self._app = app
        self._main = main_window
        self._session_factory = session_factory
        self._vault_root = vault_root
        self._hotkey: WindowsGlobalHotkey | None = None
        self._tray: QSystemTrayIcon | None = None
        self._build_tray()
        self.reregister_hotkey()

    def _tray_icon(self) -> QIcon:
        return QIcon(self._app.style().standardPixmap(QStyle.StandardPixmap.SP_DesktopIcon))

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self._tray_icon(), self._main)
        self._tray.setToolTip("Task Tracker")
        menu = QMenu()
        act_cap = QAction("Quick capture", menu)
        act_cap.triggered.connect(self.show_quick_capture)
        act_open = QAction("Open Task Tracker", menu)
        act_open.triggered.connect(self._show_main_window)
        act_exit = QAction("Exit", menu)
        act_exit.triggered.connect(self.quit_from_tray)
        menu.addAction(act_cap)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_exit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        qc = self._main._ui_settings.get("quick_capture", {})
        if bool(qc.get("tray_click_opens_capture", False)):
            self.show_quick_capture()
        else:
            self._show_main_window()

    def reregister_hotkey(self) -> None:
        if self._hotkey is not None:
            self._hotkey.unregister(self._app)
            self._hotkey = None
        qc = self._main._ui_settings.get("quick_capture", {})
        seq = str(qc.get("hotkey", "Ctrl+Shift+T"))
        self._hotkey = WindowsGlobalHotkey(seq, self.show_quick_capture)
        self._hotkey.register(self._app)

    def apply_quit_policy(self) -> None:
        qc = self._main._ui_settings.get("quick_capture", {})
        keep = bool(qc.get("keep_running_in_tray", False))
        self._app.setQuitOnLastWindowClosed(not keep)

    def keep_tray_alive(self) -> bool:
        qc = self._main._ui_settings.get("quick_capture", {})
        return bool(qc.get("keep_running_in_tray", False))

    def _destroy_tray(self) -> None:
        tray = self._tray
        if tray is None:
            return
        try:
            tray.activated.disconnect()
        except TypeError:
            pass
        tray.setContextMenu(None)
        tray.hide()
        tray.deleteLater()
        self._tray = None
        self._app.processEvents()

    def cleanup_before_quit(self) -> None:
        if self._hotkey is not None:
            self._hotkey.unregister(self._app)
            self._hotkey = None
        self._destroy_tray()

    def _show_main_window(self) -> None:
        self._main.show()
        self._main.raise_()
        self._main.activateWindow()

    def show_quick_capture(self) -> None:
        parent = self._main if self._main.isVisible() else None
        fmt = get_date_format_qt(self._main._ui_settings)
        payload = run_quick_capture_dialog(
            parent,
            session_factory=self._session_factory,
            vault_root=self._vault_root,
            ui_settings=self._main._ui_settings,
            date_format_qt=fmt,
        )
        if payload is None:
            return
        task_id, open_after = payload
        self._notify_created(task_id)
        self._main._reload_task_list()
        self._main._refresh_dashboard()
        if open_after:
            self._main.open_task_on_tasks_tab(task_id)

    def _notify_created(self, task_id: int) -> None:
        session = self._session_factory()
        try:
            svc = TaskService(session, self._vault_root)
            task = svc.get_task(task_id)
            label = format_task_ticket(task.ticket_number) if task else str(task_id)
        finally:
            session.close()
        msg = f"Captured task {label}."
        if self._main.isVisible():
            self._main._notify(msg)
        elif self._tray is not None:
            self._tray.showMessage(
                "Task Tracker",
                msg,
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def quit_from_tray(self) -> None:
        self._main.finalize_application_shutdown()
        self._app.quit()
