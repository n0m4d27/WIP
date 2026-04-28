from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tasktracker.services.task_service import TaskService


class TagsDialog(QDialog):
    def __init__(self, parent: QWidget | None, svc: TaskService) -> None:
        super().__init__(parent)
        self._svc = svc
        self.setWindowTitle("Manage tags")
        self.resize(520, 420)

        root = QVBoxLayout(self)
        self._list = QListWidget()
        root.addWidget(self._list, 1)

        row = QHBoxLayout()
        self._btn_add = QPushButton("Add…")
        self._btn_add.clicked.connect(self._add_tag)
        row.addWidget(self._btn_add)
        self._btn_rename = QPushButton("Rename…")
        self._btn_rename.clicked.connect(self._rename_tag)
        row.addWidget(self._btn_rename)
        self._btn_color = QPushButton("Set color hint…")
        self._btn_color.clicked.connect(self._set_color_hint)
        row.addWidget(self._btn_color)
        self._btn_merge = QPushButton("Merge into…")
        self._btn_merge.clicked.connect(self._merge_tag)
        row.addWidget(self._btn_merge)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._delete_tag)
        row.addWidget(self._btn_delete)
        row.addStretch(1)
        root.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        root.addWidget(bb)

        self._reload()

    def _selected_tag_id(self) -> int | None:
        it = self._list.currentItem()
        if it is None:
            return None
        raw = it.data(Qt.ItemDataRole.UserRole)
        return int(raw) if raw is not None else None

    def _reload(self) -> None:
        keep = self._selected_tag_id()
        self._list.clear()
        for tag in self._svc.list_tags():
            label = tag.name if not tag.color_hint else f"{tag.name} ({tag.color_hint})"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, tag.id)
            self._list.addItem(it)
        if keep is not None:
            for i in range(self._list.count()):
                it = self._list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == keep:
                    self._list.setCurrentItem(it)
                    break

    def _add_tag(self) -> None:
        name, ok = QInputDialog.getText(self, "Add tag", "Tag name:")
        if not ok:
            return
        tag = self._svc.create_tag(name)
        if tag is None:
            QMessageBox.warning(self, "Tags", "Tag name is invalid or already exists.")
            return
        self._reload()

    def _rename_tag(self) -> None:
        tag_id = self._selected_tag_id()
        if tag_id is None:
            return
        current = next((t for t in self._svc.list_tags() if t.id == tag_id), None)
        if current is None:
            return
        name, ok = QInputDialog.getText(self, "Rename tag", "Tag name:", text=current.name)
        if not ok:
            return
        if self._svc.rename_tag(tag_id, name) is None:
            QMessageBox.warning(self, "Tags", "Rename failed (name may already exist).")
            return
        self._reload()

    def _set_color_hint(self) -> None:
        tag_id = self._selected_tag_id()
        if tag_id is None:
            return
        current = next((t for t in self._svc.list_tags() if t.id == tag_id), None)
        if current is None:
            return
        val, ok = QInputDialog.getText(
            self,
            "Tag color hint",
            "Color hint (optional):",
            text=current.color_hint or "",
        )
        if not ok:
            return
        self._svc.update_tag(tag_id, color_hint=val or None)
        self._reload()

    def _merge_tag(self) -> None:
        src_id = self._selected_tag_id()
        if src_id is None:
            return
        rows = self._svc.list_tags()
        opts = [t for t in rows if t.id != src_id]
        if not opts:
            QMessageBox.information(self, "Tags", "Need at least two tags to merge.")
            return
        names = [t.name for t in opts]
        chosen, ok = QInputDialog.getItem(self, "Merge tag", "Merge into:", names, 0, False)
        if not ok:
            return
        target = next((t for t in opts if t.name == chosen), None)
        if target is None:
            return
        self._svc.merge_tags(src_id, target.id)
        self._reload()

    def _delete_tag(self) -> None:
        tag_id = self._selected_tag_id()
        if tag_id is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete tag",
                "Delete selected tag from all tasks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._svc.delete_tag(tag_id)
        self._reload()


def run_manage_tags_dialog(parent: QWidget | None, svc: TaskService) -> None:
    dlg = TagsDialog(parent, svc)
    dlg.exec()
