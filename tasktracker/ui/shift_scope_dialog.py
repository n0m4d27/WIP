"""Dialog that collects parameters for a bulk date shift.

Used in two shapes:

* ``mode="tasks"`` - shift a concrete list of task ids (the selection
  on the Tasks tab or the ids coming from a task-centric workflow);
* ``mode="slip"``  - slip every task with a due date on or after an
  anchor date that also matches optional for-person / area / priority
  filters ("slip from date").

Both shapes share the same Delta / business-days / include-todos
controls. The mode-specific bits (anchor date + filter row) are shown
only when relevant, so the user doesn't have to wade past fields that
don't apply to the shift they're performing.

The dialog itself only collects parameters; pressing Preview hands the
plan off to :class:`tasktracker.ui.shift_preview_dialog.ShiftPreviewDialog`
which renders the dry-run and (if the user applies) commits.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from tasktracker.domain.enums import TaskStatus
from tasktracker.services.shift_service import ShiftPlan, ShiftService
from tasktracker.services.task_service import TaskService
from tasktracker.ui.date_format import format_from_parent
from tasktracker.ui.shift_preview_dialog import ShiftPreviewDialog


ShiftScopeMode = Literal["tasks", "slip"]


def _qdate_to_py(q: QDate) -> dt.date:
    return dt.date(q.year(), q.month(), q.day())


class ShiftScopeDialog(QDialog):
    """Modal that gathers the parameters for a bulk shift.

    ``result`` callers should check ``self.applied`` after ``exec()`` -
    the dialog returns ``Accepted`` only when the user clicked
    "Apply" in the subsequent preview dialog.
    """

    def __init__(
        self,
        parent,
        svc: TaskService,
        *,
        mode: ShiftScopeMode = "tasks",
        task_ids: list[int] | None = None,
        default_delta: int = 5,
        default_business_days: bool = True,
        default_include_todos: bool = True,
    ) -> None:
        super().__init__(parent)
        self.svc = svc
        self.mode: ShiftScopeMode = mode
        self.task_ids = list(task_ids or [])
        self.applied_result = None  # ShiftResult | None
        self.applied: bool = False

        self.setWindowTitle(
            "Shift selected tasks…" if mode == "tasks" else "Slip schedule from date…"
        )
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        # Context hint - what the user is about to shift.
        if mode == "tasks":
            self.ctx_label = QLabel(
                f"Shifting {len(self.task_ids)} selected task(s)."
            )
        else:
            self.ctx_label = QLabel(
                "Shift every task with a due date on or after the anchor "
                "date that matches the filter below."
            )
        self.ctx_label.setWordWrap(True)
        layout.addWidget(self.ctx_label)

        form = QFormLayout()

        # Delta controls.
        self.sp_delta = QSpinBox()
        self.sp_delta.setRange(-365, 365)
        self.sp_delta.setValue(default_delta)
        self.sp_delta.setSuffix(" day(s)")
        self.sp_delta.setToolTip(
            "Positive values push dates into the future; negative values "
            "pull them earlier. Zero is a no-op."
        )
        form.addRow("Delta", self.sp_delta)

        self.chk_business = QCheckBox("Business days (skip weekends + holidays)")
        self.chk_business.setChecked(default_business_days)
        form.addRow("", self.chk_business)

        self.chk_include_todos = QCheckBox("Also shift todo milestones")
        self.chk_include_todos.setChecked(default_include_todos)
        self.chk_include_todos.setToolTip(
            "Applies the same delta to every attached todo's milestone date."
        )
        form.addRow("", self.chk_include_todos)

        # Slip-mode extras (anchor + optional filters).
        if mode == "slip":
            self.de_anchor = QDateEdit(QDate.currentDate())
            self.de_anchor.setCalendarPopup(True)
            self.de_anchor.setDisplayFormat(format_from_parent(parent))
            form.addRow("Anchor date", self.de_anchor)

            self.cmb_person = QComboBox()
            self.cmb_person.addItem("— Any —", None)
            for p in svc.list_people():
                self.cmb_person.addItem(
                    f"{p.last_name}, {p.first_name} ({p.employee_id})", p.id
                )
            form.addRow("For person", self.cmb_person)

            self.cmb_area = QComboBox()
            self.cmb_area.addItem("— Any —", None)
            for cat in svc.list_categories():
                for sub in sorted(cat.subcategories, key=lambda s: s.name.lower()):
                    for area in sorted(sub.areas, key=lambda a: a.name.lower()):
                        self.cmb_area.addItem(
                            f"{cat.name} / {sub.name} / {area.name}", area.id
                        )
            form.addRow("Area", self.cmb_area)

            self.cmb_min_priority = QComboBox()
            self.cmb_min_priority.addItem("— Any priority —", None)
            for p in range(1, 6):
                self.cmb_min_priority.addItem(f"P{p} or higher", p)
            form.addRow("Min priority", self.cmb_min_priority)

            self.cmb_status = QComboBox()
            self.cmb_status.addItem("— Exclude closed & cancelled —", "default")
            for s in TaskStatus:
                self.cmb_status.addItem(
                    f"Only {s.value.replace('_', ' ')}", s.value
                )
            form.addRow("Status filter", self.cmb_status)

        layout.addLayout(form)

        # Buttons: Preview runs a dry-run -> opens the preview dialog.
        # Cancel closes without doing anything. OK is intentionally
        # absent because applying has to go through the preview dialog
        # to keep the confirm-before-apply contract.
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.btn_preview = QPushButton("Preview…")
        bb.addButton(self.btn_preview, QDialogButtonBox.ButtonRole.AcceptRole)
        bb.rejected.connect(self.reject)
        self.btn_preview.clicked.connect(self._on_preview)
        layout.addWidget(bb)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _build_plan(self) -> ShiftPlan | None:
        ss = ShiftService(self.svc.session)
        delta = self.sp_delta.value()
        business = self.chk_business.isChecked()
        include_todos = self.chk_include_todos.isChecked()
        if delta == 0:
            return None

        if self.mode == "tasks":
            if not self.task_ids:
                return None
            return ss.preview_task_shift(
                self.task_ids,
                delta,
                business_days=business,
                include_todos=include_todos,
            )

        # slip
        anchor = _qdate_to_py(self.de_anchor.date())
        for_ids = []
        pid = self.cmb_person.currentData()
        if pid is not None:
            for_ids.append(int(pid))
        area_ids = []
        aid = self.cmb_area.currentData()
        if aid is not None:
            area_ids.append(int(aid))
        mpr = self.cmb_min_priority.currentData()
        min_priority = int(mpr) if mpr is not None else None
        status_data = self.cmb_status.currentData()
        statuses = None if status_data == "default" else [str(status_data)]
        return ss.preview_slip_from_date(
            anchor,
            delta,
            business_days=business,
            include_todos=include_todos,
            for_person_ids=for_ids or None,
            area_ids=area_ids or None,
            min_priority=min_priority,
            statuses=statuses,
        )

    def _on_preview(self) -> None:
        plan = self._build_plan()
        if plan is None:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self, "Shift", "Nothing to shift (delta is zero or no rows match)."
            )
            return
        if not plan.rows:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self, "Shift", f"No rows matched: {plan.summary}"
            )
            return

        preview = ShiftPreviewDialog(self, self.svc, plan)
        if preview.exec() == QDialog.DialogCode.Accepted and preview.result_applied is not None:
            self.applied_result = preview.result_applied
            self.applied = True
            self.accept()
