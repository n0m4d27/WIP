"""Dry-run viewer for a :class:`~tasktracker.services.shift_service.ShiftPlan`.

Shown by :class:`~tasktracker.ui.shift_scope_dialog.ShiftScopeDialog`
when the user clicks "Preview…". Users can review every proposed
change - tickets, titles, old vs new dates, and a flag column that
highlights landings on weekends or holidays for calendar-day shifts -
before committing via Apply.

Keeping the preview in its own dialog matters for two reasons: (a) it
preserves the "no surprises" contract - no bulk shift ever commits
without an explicit confirm step - and (b) it makes this the single
place where the row table gets built, so the same widget can be
reused from the Tasks tab, the Edit menu, or the calendar quick-edit
selection strip.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from tasktracker.services.shift_service import ShiftPlan, ShiftResult, ShiftService
from tasktracker.services.task_service import TaskService
from tasktracker.ui.date_format import format_date, format_from_parent, reformat_iso_dates_in_text


# Distinct-enough tints for weekend/holiday flags. Using table item
# backgrounds (rather than whole-row styling) keeps the highlight
# obvious without fighting the system palette in dark mode.
_FLAG_BG = {
    "weekend": QColor(255, 236, 179),  # soft amber
    "holiday": QColor(255, 205, 210),  # soft red
    "no-op": QColor(238, 238, 238),     # gray-ish
}


class ShiftPreviewDialog(QDialog):
    """Show proposed changes; Apply commits and captures the inverse."""

    def __init__(
        self,
        parent,
        svc: TaskService,
        plan: ShiftPlan,
    ) -> None:
        super().__init__(parent)
        self.svc = svc
        self.plan = plan
        self.result_applied: ShiftResult | None = None
        self._date_fmt = format_from_parent(parent)

        self.setWindowTitle("Preview bulk shift")
        self.resize(780, 500)

        lay = QVBoxLayout(self)
        summary = QLabel(reformat_iso_dates_in_text(plan.summary, self._date_fmt))
        summary.setWordWrap(True)
        summary.setStyleSheet("font-weight: bold;")
        lay.addWidget(summary)

        note = QLabel(
            "Apply commits these changes and keeps the inverse for a "
            "one-click undo from the Edit menu."
        )
        note.setWordWrap(True)
        lay.addWidget(note)

        self.table = QTableWidget(len(plan.rows), 7)
        self.table.setHorizontalHeaderLabels(
            ["Kind", "Ticket", "Title", "Field", "Old", "New", "Flag"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        for r, row in enumerate(plan.rows):
            self._populate_row(r, row)
        self.table.resizeColumnsToContents()
        lay.addWidget(self.table, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.btn_apply = QPushButton("Apply")
        bb.addButton(self.btn_apply, QDialogButtonBox.ButtonRole.AcceptRole)
        bb.rejected.connect(self.reject)
        self.btn_apply.clicked.connect(self._on_apply)
        lay.addWidget(bb)

        # Disable Apply when there's nothing to do (all rows are no-ops
        # or old==new). We compute once here; rows don't change while
        # the dialog is up.
        actionable = any(
            r.flag != "no-op" and r.old_value != r.new_value for r in plan.rows
        )
        self.btn_apply.setEnabled(actionable)

    # ------------------------------------------------------------------
    # Row rendering
    # ------------------------------------------------------------------

    def _populate_row(self, r, row) -> None:  # type: ignore[no-untyped-def]
        def _item(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            return it

        cells = [
            _item(row.entity_type),
            _item(row.ticket or ""),
            _item(row.title or ""),
            _item(row.field),
            _item(format_date(row.old_value, self._date_fmt)),
            _item(format_date(row.new_value, self._date_fmt)),
            _item(row.flag or ""),
        ]
        bg = _FLAG_BG.get(row.flag or "", None)
        for col, it in enumerate(cells):
            if bg is not None:
                it.setBackground(QBrush(bg))
            self.table.setItem(r, col, it)

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        ss = ShiftService(self.svc.session)
        try:
            self.result_applied = ss.apply_shift(self.plan)
        except Exception as exc:  # pragma: no cover - surfaced as a dialog
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Shift failed", str(exc))
            return
        self.accept()
