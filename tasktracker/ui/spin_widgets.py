"""Small spin-box variants for platform-specific UI quirks."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractSpinBox, QSpinBox


class StepInvertedSpinBox(QSpinBox):
    """Spin box where step-up decreases the stored value in some environments.

    Impact/Urgency use a 1–3 scale; on some platforms the arrow controls feel
    reversed relative to "up means higher number". Inverting ``stepBy`` aligns
    button, wheel, and keyboard stepping with that expectation.

    Qt enables/disables each arrow from the *un-inverted* step direction, so at
    min/max the wrong arrow would grey out unless we swap ``stepEnabled`` too.
    """

    def stepBy(self, steps: int) -> None:
        super().stepBy(-steps)

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabled:
        base = super().stepEnabled()
        F = QAbstractSpinBox.StepEnabledFlag
        out = F.StepNone
        if base & F.StepUpEnabled:
            out |= F.StepDownEnabled
        if base & F.StepDownEnabled:
            out |= F.StepUpEnabled
        return QAbstractSpinBox.StepEnabled(out)
