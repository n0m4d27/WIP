"""Settings dialog to manage vault-specific categories/areas and people."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from tasktracker.services.task_service import TaskService


class _ReferenceDataDialog(QDialog):
    def __init__(self, svc: TaskService, parent=None) -> None:
        super().__init__(parent)
        self._svc = svc
        self.setWindowTitle("Manage categories and people")
        self.resize(900, 520)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_categories_tab(), "Categories")
        tabs.addTab(self._build_people_tab(), "People")
        root.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        bb.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        root.addWidget(bb)

        self._reload_categories()
        self._reload_people()

    def _build_categories_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)

        cat_box = QGroupBox("Categories")
        cat_l = QVBoxLayout(cat_box)
        self.cat_list = QListWidget()
        self.cat_list.currentItemChanged.connect(self._on_category_changed)
        cat_l.addWidget(self.cat_list)
        cat_btns = QHBoxLayout()
        b = QPushButton("Add…")
        b.clicked.connect(self._add_category)
        cat_btns.addWidget(b)
        b = QPushButton("Remove")
        b.clicked.connect(self._delete_category)
        cat_btns.addWidget(b)
        cat_l.addLayout(cat_btns)
        lay.addWidget(cat_box, 1)

        sub_box = QGroupBox("Sub-categories")
        sub_l = QVBoxLayout(sub_box)
        self.sub_list = QListWidget()
        self.sub_list.currentItemChanged.connect(self._on_subcategory_changed)
        sub_l.addWidget(self.sub_list)
        sub_btns = QHBoxLayout()
        b = QPushButton("Add…")
        b.clicked.connect(self._add_subcategory)
        sub_btns.addWidget(b)
        b = QPushButton("Remove")
        b.clicked.connect(self._delete_subcategory)
        sub_btns.addWidget(b)
        sub_l.addLayout(sub_btns)
        lay.addWidget(sub_box, 1)

        area_box = QGroupBox("Areas")
        area_l = QVBoxLayout(area_box)
        self.area_list = QListWidget()
        area_l.addWidget(self.area_list)
        area_btns = QHBoxLayout()
        b = QPushButton("Add…")
        b.clicked.connect(self._add_area)
        area_btns.addWidget(b)
        b = QPushButton("Remove")
        b.clicked.connect(self._delete_area)
        area_btns.addWidget(b)
        area_l.addLayout(area_btns)
        lay.addWidget(area_box, 1)
        return w

    def _build_people_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tip = QLabel(
            "People are the task attribution targets (the person the task is for). "
            "Employee ID is the unique key."
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.people_list = QListWidget()
        lay.addWidget(self.people_list)
        row = QHBoxLayout()
        b = QPushButton("Add…")
        b.clicked.connect(self._add_person)
        row.addWidget(b)
        b = QPushButton("Remove")
        b.clicked.connect(self._delete_person)
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        return w

    def _selected_id(self, lw: QListWidget) -> int | None:
        item = lw.currentItem()
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        return int(raw) if raw is not None else None

    def _reload_categories(self) -> None:
        keep_cat = self._selected_id(self.cat_list)
        self.cat_list.blockSignals(True)
        self.cat_list.clear()
        for cat in self._svc.list_categories():
            self.cat_list.addItem(cat.name)
            it = self.cat_list.item(self.cat_list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, cat.id)
        self.cat_list.blockSignals(False)
        if not self._select_by_id(self.cat_list, keep_cat) and self.cat_list.count() > 0:
            self.cat_list.setCurrentRow(0)
        self._on_category_changed(None, None)

    def _reload_subcategories(self) -> None:
        keep_sub = self._selected_id(self.sub_list)
        self.sub_list.blockSignals(True)
        self.sub_list.clear()
        cat_id = self._selected_id(self.cat_list)
        if cat_id is not None:
            for sub in self._svc.list_subcategories(cat_id):
                self.sub_list.addItem(sub.name)
                it = self.sub_list.item(self.sub_list.count() - 1)
                it.setData(Qt.ItemDataRole.UserRole, sub.id)
        self.sub_list.blockSignals(False)
        if not self._select_by_id(self.sub_list, keep_sub) and self.sub_list.count() > 0:
            self.sub_list.setCurrentRow(0)
        self._on_subcategory_changed(None, None)

    def _reload_areas(self) -> None:
        keep_area = self._selected_id(self.area_list)
        self.area_list.clear()
        sub_id = self._selected_id(self.sub_list)
        if sub_id is not None:
            for area in self._svc.list_areas(sub_id):
                self.area_list.addItem(area.name)
                it = self.area_list.item(self.area_list.count() - 1)
                it.setData(Qt.ItemDataRole.UserRole, area.id)
        self._select_by_id(self.area_list, keep_area)

    def _reload_people(self) -> None:
        keep_id = self._selected_id(self.people_list)
        self.people_list.clear()
        for p in self._svc.list_people():
            self.people_list.addItem(f"{p.last_name}, {p.first_name} ({p.employee_id})")
            it = self.people_list.item(self.people_list.count() - 1)
            it.setData(Qt.ItemDataRole.UserRole, p.id)
        self._select_by_id(self.people_list, keep_id)

    @staticmethod
    def _select_by_id(lw: QListWidget, item_id: int | None) -> bool:
        if item_id is None:
            return False
        for i in range(lw.count()):
            it = lw.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == item_id:
                lw.setCurrentItem(it)
                return True
        return False

    def _on_category_changed(self, _cur, _prev) -> None:
        self._reload_subcategories()

    def _on_subcategory_changed(self, _cur, _prev) -> None:
        self._reload_areas()

    def _add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Add category", "Category name:")
        if not ok:
            return
        created = self._svc.add_category(name)
        self._reload_categories()
        if created is not None:
            self._select_by_id(self.cat_list, created.id)

    def _delete_category(self) -> None:
        cat_id = self._selected_id(self.cat_list)
        if cat_id is None:
            return
        self._svc.delete_category(cat_id)
        self._reload_categories()

    def _add_subcategory(self) -> None:
        cat_id = self._selected_id(self.cat_list)
        if cat_id is None:
            return
        name, ok = QInputDialog.getText(self, "Add sub-category", "Sub-category name:")
        if not ok:
            return
        created = self._svc.add_subcategory(cat_id, name)
        self._reload_subcategories()
        if created is not None:
            self._select_by_id(self.sub_list, created.id)

    def _delete_subcategory(self) -> None:
        sub_id = self._selected_id(self.sub_list)
        if sub_id is None:
            return
        self._svc.delete_subcategory(sub_id)
        self._reload_subcategories()

    def _add_area(self) -> None:
        sub_id = self._selected_id(self.sub_list)
        if sub_id is None:
            return
        name, ok = QInputDialog.getText(self, "Add area", "Area name:")
        if not ok:
            return
        created = self._svc.add_area(sub_id, name)
        self._reload_areas()
        if created is not None:
            self._select_by_id(self.area_list, created.id)

    def _delete_area(self) -> None:
        area_id = self._selected_id(self.area_list)
        if area_id is None:
            return
        self._svc.delete_area(area_id)
        self._reload_areas()

    def _add_person(self) -> None:
        d = QDialog(self)
        d.setWindowTitle("Add person")
        form = QFormLayout(d)
        first = QLineEdit()
        last = QLineEdit()
        emp = QLineEdit()
        form.addRow("First name", first)
        form.addRow("Last name", last)
        form.addRow("Employee ID", emp)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        created = self._svc.add_person(first.text(), last.text(), emp.text())
        self._reload_people()
        if created is not None:
            self._select_by_id(self.people_list, created.id)

    def _delete_person(self) -> None:
        person_id = self._selected_id(self.people_list)
        if person_id is None:
            return
        self._svc.delete_person(person_id)
        self._reload_people()


def run_manage_reference_data_dialog(parent, svc: TaskService) -> None:
    _ReferenceDataDialog(svc, parent).exec()
