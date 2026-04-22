"""Dashboard tab widget: "what needs my attention right now" cards.

The dashboard lives as the leftmost tab in the main window so it is the
default landing surface on app start. It is intentionally read-only -
clicking a task row or a card's "Show all" button routes the user to
the Tasks tab with the matching filter applied, rather than opening an
inline editor. Inline drill-down belongs to a later plan; keeping the
dashboard a pure summary view prevents state drift between two editors
of the same task.

This module owns the layout and widget wiring only. Query logic lives
in :meth:`TaskService.dashboard_sections` so the numbers are consistent
between the UI and tests.
"""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tasktracker.domain.priority import priority_display
from tasktracker.domain.ticket import format_task_ticket
from tasktracker.services.task_service import DASHBOARD_CARD_IDS
from tasktracker.ui.date_format import format_date

# Ordered (card_id, title, empty_state_text) triples. Titles are short
# so the card header stays readable at the grid's minimum width, and
# empty-state text is phrased as reassurance rather than an error
# because an empty "Due today" card on a quiet day is good news.
DASHBOARD_CARD_META: tuple[tuple[str, str, str], ...] = (
    ("overdue", "Overdue", "No overdue tasks. Keep it up."),
    ("due_today", "Due today", "Nothing due today."),
    ("due_this_week", "Due this week", "No due dates within the next 7 days."),
    ("blocked", "Blocked", "No tasks currently blocked."),
    ("top_priority", "Top priority (P1/P2)", "No P1 or P2 tasks open."),
)

# Grid position for each card id. Two-column layout reads top-to-bottom
# by columns so the "now" pair (overdue + due today) is visible before
# the user has to scroll on a laptop screen.
_CARD_GRID_POSITIONS: dict[str, tuple[int, int]] = {
    "overdue": (0, 0),
    "due_today": (0, 1),
    "due_this_week": (1, 0),
    "blocked": (1, 1),
    "top_priority": (2, 0),
}


def _format_task_row_label(task: Any, date_format: str) -> str:
    """Return the one-line label rendered inside a card's task list."""
    ticket = format_task_ticket(task.ticket_number)
    priority = priority_display(task.priority)
    due = format_date(task.due_date, date_format) if task.due_date else "no due"
    return f"{ticket} [{priority}] {task.title} — {due}"


class DashboardCard(QFrame):
    """Single card in the dashboard grid.

    Responsibilities:

    * Show a title + live count badge.
    * Render up to N task rows (``QListWidget`` keeps keyboard nav
      consistent with the Tasks tab).
    * Emit signals for "row activated" and "show all clicked" so the
      parent widget can translate those into tab navigation.

    The card does not know about filters or routing; it just reports
    what the user clicked.
    """

    show_all_clicked = Signal(str)
    task_activated = Signal(int)

    def __init__(self, card_id: str, title: str, empty_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._card_id = card_id
        self._empty_text = empty_text
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)

        header = QHBoxLayout()
        self._title = QLabel(title)
        self._title.setStyleSheet("font-weight: bold;")
        header.addWidget(self._title)
        header.addStretch()
        # Count badge is a plain label with bold text so the card stays
        # theme-agnostic; themed backgrounds for the badge can land if
        # visual separation ever becomes a problem.
        self._count = QLabel("0")
        self._count.setStyleSheet("font-weight: bold;")
        header.addWidget(self._count)
        root.addLayout(header)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        # Double-click to jump mirrors the Tasks tab's behavior; single
        # Enter on a selected row achieves the same via itemActivated.
        self._list.itemActivated.connect(self._on_item_activated)
        root.addWidget(self._list, 1)

        self._empty_label = QLabel(empty_text)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: gray;")
        self._empty_label.hide()
        root.addWidget(self._empty_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._show_all = QPushButton("Show all")
        self._show_all.setToolTip("Open the Tasks tab with this filter applied.")
        self._show_all.clicked.connect(lambda: self.show_all_clicked.emit(self._card_id))
        btn_row.addWidget(self._show_all)
        root.addLayout(btn_row)

    @property
    def card_id(self) -> str:
        return self._card_id

    def populate(
        self,
        payload: dict[str, Any],
        *,
        date_format: str,
    ) -> None:
        """Update the card from a ``dashboard_sections`` payload entry."""
        count = int(payload.get("count", 0))
        rows = payload.get("rows") or []
        self._count.setText(str(count))
        self._list.clear()
        if not rows:
            self._list.hide()
            self._empty_label.setText(self._empty_text)
            self._empty_label.show()
            # Disabling the button removes the noise of clicking into a
            # guaranteed-empty list, and the "0" badge already implies
            # the filter is empty.
            self._show_all.setEnabled(False)
            return
        self._empty_label.hide()
        self._list.show()
        for task in rows:
            label = _format_task_row_label(task, date_format)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, int(task.id))
            self._list.addItem(item)
        # When the total exceeds what we listed, hint that "Show all"
        # returns more. Keeps the user oriented without needing a tooltip.
        if count > len(rows):
            hint = QListWidgetItem(f"… and {count - len(rows)} more. Click \"Show all\" to see the full list.")
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(hint)
        self._show_all.setEnabled(True)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(tid, int):
            self.task_activated.emit(tid)


class DashboardWidget(QWidget):
    """Grid of dashboard cards, wrapped in a scroll area.

    The widget is stateless with respect to the database - the host
    window is responsible for calling :meth:`refresh` whenever task
    data changes (on save, close, import, etc.). Doing it this way
    keeps the dashboard decoupled from change signals scattered across
    the Tasks tab.
    """

    show_all_clicked = Signal(str)
    task_activated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        heading = QLabel("What needs my attention")
        heading.setStyleSheet("font-size: 1.15em; font-weight: bold;")
        root.addWidget(heading)

        subtitle = QLabel(
            "Tasks that are overdue, due soon, blocked, or high priority. "
            "Click a task to open it, or use \"Show all\" to jump into the Tasks tab with the matching filter."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: gray;")
        root.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        self._cards: dict[str, DashboardCard] = {}
        for card_id, title, empty in DASHBOARD_CARD_META:
            card = DashboardCard(card_id, title, empty, host)
            card.show_all_clicked.connect(self.show_all_clicked.emit)
            card.task_activated.connect(self.task_activated.emit)
            row, col = _CARD_GRID_POSITIONS[card_id]
            grid.addWidget(card, row, col)
            self._cards[card_id] = card
        # Two even columns; extra rows don't need stretch because card
        # sizePolicy already requests their preferred height.
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def card_ids(self) -> Iterable[str]:
        """Iteration order matches ``DASHBOARD_CARD_IDS``."""
        return DASHBOARD_CARD_IDS

    def refresh(
        self,
        sections: dict[str, dict[str, Any]],
        *,
        date_format: str,
    ) -> None:
        """Apply a ``dashboard_sections`` payload to every card.

        Cards whose id is missing from ``sections`` are cleared rather
        than left stale - this keeps the UI honest if a future service
        refactor drops a card id.
        """
        for card_id, card in self._cards.items():
            payload = sections.get(card_id) or {"count": 0, "rows": []}
            card.populate(payload, date_format=date_format)
