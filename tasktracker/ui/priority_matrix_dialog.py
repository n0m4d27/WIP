from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from tasktracker.domain.priority import PRIORITY_LABELS, compute_priority


class PriorityMatrixDialog(QDialog):
    """OOTB ServiceNow-style Impact × Urgency → Priority reference."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Impact × Urgency → Priority (ServiceNow OOTB)")
        self.resize(520, 320)

        table = QTableWidget(4, 4)
        table.setHorizontalHeaderLabels(["", "Urgency 1 High", "Urgency 2 Med", "Urgency 3 Low"])
        table.setVerticalHeaderLabels(["", "Impact 1 High", "Impact 2 Med", "Impact 3 Low"])
        for r in range(1, 4):
            for c in range(1, 4):
                pr = compute_priority(impact=r, urgency=c)
                label = PRIORITY_LABELS[pr]
                item = QTableWidgetItem(f"P{pr}\n{label}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()

        help_lbl = QLabel(
            "Set <b>Impact</b> and <b>Urgency</b> on the task; <b>Priority</b> updates automatically. "
            "Use this matrix to pick the pair that yields the priority you want."
        )
        help_lbl.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.addWidget(help_lbl)
        lay.addWidget(table)
        lay.addWidget(buttons)
