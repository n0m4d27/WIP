"""Task detail section: file attachments (plan 04)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from tasktracker.db.models import Task, TaskAttachment
from tasktracker.services.task_service import TaskService


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


class AttachmentsSection(QGroupBox):
    """List, add, open, rename, and remove attachments; accepts file drops."""

    def __init__(
        self,
        svc: TaskService,
        open_temp_dir: Path,
        on_changed: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._svc = svc
        self._open_temp_dir = open_temp_dir
        self._on_changed = on_changed
        self._task: Task | None = None

        lay = QVBoxLayout(self)
        hint = QLabel("Stored under the vault folder; encrypted when you close the app.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        lay.addWidget(hint)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(lambda _i: self._open_selected())
        lay.addWidget(self._list, 1)

        row = QHBoxLayout()
        self._btn_add = QPushButton("Add files…")
        self._btn_add.clicked.connect(self._add_files)
        self._btn_open = QPushButton("Open")
        self._btn_open.setToolTip("Copy to a temp folder and open with the system default application.")
        self._btn_open.clicked.connect(self._open_selected)
        self._btn_rename = QPushButton("Rename…")
        self._btn_rename.clicked.connect(self._rename_selected)
        self._btn_remove = QPushButton("Remove")
        self._btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(self._btn_add)
        row.addWidget(self._btn_open)
        row.addWidget(self._btn_rename)
        row.addWidget(self._btn_remove)
        row.addStretch()
        lay.addLayout(row)

        self.setAcceptDrops(True)
        self.refresh(None)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        if not self._task or not self.isEnabled():
            event.ignore()
            return
        paths: list[Path] = []
        for u in event.mimeData().urls():
            if u.isLocalFile():
                paths.append(Path(u.toLocalFile()))
        if not paths:
            event.ignore()
            return
        for p in paths:
            if p.is_file():
                self._ingest_path(p)
        event.acceptProposedAction()

    def refresh(self, task: Task | None) -> None:
        self._task = task
        self._list.clear()
        if task is None:
            self.setTitle("Attachments (0)")
            self.setEnabled(False)
            return
        self.setEnabled(True)
        rows = sorted(task.attachments, key=lambda a: (a.created_at, a.id))
        for a in rows:
            self._list.addItem(self._item_for_attachment(a))
        self.setTitle(f"Attachments ({len(rows)})")

    def _item_for_attachment(self, a: TaskAttachment) -> QListWidgetItem:
        it = QListWidgetItem(f"{a.display_name}  —  {_fmt_bytes(a.size_bytes)}")
        it.setData(Qt.ItemDataRole.UserRole, a.id)
        it.setToolTip(a.storage_relpath)
        return it

    def _selected_attachment_id(self) -> int | None:
        it = self._list.currentItem()
        if not it:
            return None
        v = it.data(Qt.ItemDataRole.UserRole)
        return int(v) if v is not None else None

    def _add_files(self) -> None:
        if not self._task:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self.window(), "Add attachments", "", "All files (*)"
        )
        for s in paths:
            self._ingest_path(Path(s))

    def _ingest_path(self, path: Path) -> None:
        if not self._task:
            return
        att, err = self._svc.add_task_attachment(self._task.id, path, confirm_large=False)
        if err == "oversize":
            mb = self._svc.ATTACHMENT_SOFT_CAP_BYTES // (1024 * 1024)
            r = QMessageBox.warning(
                self.window(),
                "Large attachment",
                f'"{path.name}" is over {mb} MB. Add it anyway?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
            att, err = self._svc.add_task_attachment(self._task.id, path, confirm_large=True)
        if err == "no_vault":
            QMessageBox.warning(self.window(), "Attachments", "No vault folder is configured.")
            return
        if err or att is None:
            QMessageBox.warning(
                self.window(),
                "Attachments",
                f"Could not add {path.name!r}" + (f" ({err})." if err else "."),
            )
            return
        self._on_changed()

    def _open_selected(self) -> None:
        aid = self._selected_attachment_id()
        if aid is None or not self._task:
            return
        dest = self._svc.materialize_attachment_open_copy(aid, self._open_temp_dir)
        if dest is None:
            QMessageBox.warning(
                self.window(),
                "Open attachment",
                "Could not read the file from the vault.",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest.resolve())))

    def _remove_selected(self) -> None:
        aid = self._selected_attachment_id()
        if aid is None or not self._task:
            return
        r = QMessageBox.question(
            self.window(),
            "Remove attachment",
            "Remove this attachment from the task and delete the file from the vault?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        if self._svc.remove_task_attachment(aid):
            self._on_changed()

    def _rename_selected(self) -> None:
        aid = self._selected_attachment_id()
        if aid is None or not self._task:
            return
        row = self._svc.session.get(TaskAttachment, aid)
        if not row:
            return
        text, ok = QInputDialog.getText(
            self.window(),
            "Rename attachment",
            "Display name:",
            text=row.display_name,
        )
        if ok and text.strip():
            self._svc.rename_task_attachment(aid, text)
            self._on_changed()
