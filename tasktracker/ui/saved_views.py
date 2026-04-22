"""Saved views sidebar for the Tasks tab.

A "saved view" is a named snapshot of the Tasks tab's filter state
(search string, enabled search-field checkboxes, hide-closed toggle).
Persistence lives in :mod:`tasktracker.ui.settings_store`; this module
is only the widget that renders the list and emits user intents.

The sidebar is a vertical stack on the far left of the Tasks tab. The
host window is responsible for:

* Reading the current filter state (via :meth:`SavedViewsWidget.emit_save_requested`).
* Applying a view (in response to :pyattr:`SavedViewsWidget.view_applied`).
* Persisting updates through ``settings_store`` helpers and calling
  :meth:`SavedViewsWidget.set_views` to reflect the new list.

Keeping persistence in the host window lets that window batch a single
``save_ui_settings`` call per user action rather than forcing every
widget interaction to hit disk.
"""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SavedViewsWidget(QGroupBox):
    """Sidebar group box with the saved-view list and action buttons."""

    view_applied = Signal(str)
    save_requested = Signal()
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    move_requested = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Saved views", parent)
        self.setToolTip(
            "Named snapshots of the Tasks tab filters. Use \"Save current…\" to "
            "capture the current search and checkbox state as a view."
        )
        root = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.itemActivated.connect(self._on_item_activated)
        self._list.currentRowChanged.connect(lambda _row: self._update_button_state())
        root.addWidget(self._list, 1)

        # Placeholder text shown when no views are configured. Rebuilt
        # fresh on every populate because ``QListWidget.clear`` deletes
        # any stored QListWidgetItem.
        self._empty_hint_text = (
            "No saved views yet. Set up filters and click \"Save current…\"."
        )

        actions = QHBoxLayout()
        self._btn_apply = QPushButton("Apply")
        self._btn_apply.setToolTip("Apply the selected view's filters to the Tasks tab.")
        self._btn_apply.clicked.connect(self._emit_apply)
        actions.addWidget(self._btn_apply)

        self._btn_save = QPushButton("Save current…")
        self._btn_save.setToolTip(
            "Save the Tasks tab's current filter state as a new saved view."
        )
        self._btn_save.clicked.connect(self.save_requested.emit)
        actions.addWidget(self._btn_save)
        root.addLayout(actions)

        manage = QHBoxLayout()
        self._btn_rename = QPushButton("Rename…")
        self._btn_rename.clicked.connect(self._emit_rename)
        manage.addWidget(self._btn_rename)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._emit_delete)
        manage.addWidget(self._btn_delete)
        root.addLayout(manage)

        move = QHBoxLayout()
        self._btn_up = QPushButton("Move up")
        self._btn_up.clicked.connect(lambda: self._emit_move(-1))
        move.addWidget(self._btn_up)
        self._btn_down = QPushButton("Move down")
        self._btn_down.clicked.connect(lambda: self._emit_move(1))
        move.addWidget(self._btn_down)
        root.addLayout(move)

        self.set_views([])

    # ------------------------------------------------------------------
    # Population + selection state
    # ------------------------------------------------------------------
    def set_views(self, views: Iterable[dict[str, Any]]) -> None:
        """Replace the list contents with ``views``.

        Selection is preserved by name when possible so a refresh after
        a rename/move keeps the user's focus on the view they just
        worked with.
        """
        previous = self.selected_name()
        self._list.clear()
        names: list[str] = []
        for view in views:
            name = view.get("name")
            if not isinstance(name, str):
                continue
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._list.addItem(item)
            names.append(name)
        if not names:
            placeholder = QListWidgetItem(self._empty_hint_text)
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)
        else:
            target = previous if previous in names else names[0]
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == target:
                    self._list.setCurrentRow(i)
                    break
        self._update_button_state()

    def selected_name(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        name = item.data(Qt.ItemDataRole.UserRole)
        return name if isinstance(name, str) else None

    # ------------------------------------------------------------------
    # Internal signal helpers
    # ------------------------------------------------------------------
    def _has_real_selection(self) -> bool:
        return self.selected_name() is not None

    def _selected_index(self) -> int:
        name = self.selected_name()
        if name is None:
            return -1
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == name:
                return i
        return -1

    def _update_button_state(self) -> None:
        has = self._has_real_selection()
        self._btn_apply.setEnabled(has)
        self._btn_rename.setEnabled(has)
        self._btn_delete.setEnabled(has)
        # Up/down only make sense when there is another entry to swap
        # with. Disabling them on the edges avoids the user clicking and
        # getting no-op feedback.
        idx = self._selected_index()
        last = self._list.count() - 1
        self._btn_up.setEnabled(has and idx > 0)
        # When the only item in the list is the empty-hint placeholder,
        # ``last`` is 0 and ``has`` is False, so this still disables.
        self._btn_down.setEnabled(has and 0 <= idx < last)

    def _emit_apply(self) -> None:
        name = self.selected_name()
        if name is not None:
            self.view_applied.emit(name)

    def _emit_rename(self) -> None:
        name = self.selected_name()
        if name is not None:
            self.rename_requested.emit(name)

    def _emit_delete(self) -> None:
        name = self.selected_name()
        if name is not None:
            self.delete_requested.emit(name)

    def _emit_move(self, delta: int) -> None:
        name = self.selected_name()
        if name is not None:
            self.move_requested.emit(name, delta)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(name, str):
            self.view_applied.emit(name)
