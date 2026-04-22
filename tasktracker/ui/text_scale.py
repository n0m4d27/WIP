"""Application-wide text scaling via ``QApplication.setFont``.

Scaling always applies relative to a one-time baseline font captured after the
color theme is applied, so changing the scale does not compound on the previous
scaled font.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from tasktracker.ui.settings_store import coerce_ui_text_scale

_baseline_font: QFont | None = None


def ensure_text_scale_baseline(app: QApplication) -> None:
    """Snapshot ``app.font()`` once; later scaling multiplies this baseline."""
    global _baseline_font
    if _baseline_font is None:
        _baseline_font = QFont(app.font())


def apply_app_text_scale(app: QApplication, scale: float) -> None:
    """Set the application font to ``baseline * coerce(scale)``."""
    ensure_text_scale_baseline(app)
    if _baseline_font is None:
        return
    s = coerce_ui_text_scale(scale)
    f = QFont(_baseline_font)
    base_pt = _baseline_font.pointSizeF()
    if base_pt <= 0 and _baseline_font.pointSize() > 0:
        base_pt = float(_baseline_font.pointSize())
    if base_pt <= 0:
        px = _baseline_font.pixelSize()
        if px > 0:
            f.setPixelSize(max(1, int(round(px * s))))
            app.setFont(f)
            return
        base_pt = 10.0
    f.setPointSizeF(max(1.0, base_pt * s))
    app.setFont(f)


def propagate_font_to_widget_tree(root: QWidget, font: QFont) -> None:
    """Assign ``font`` to ``root`` and every descendant ``QWidget``.

    ``QApplication.setFont`` alone does not always refresh fonts for existing
    Fusion widgets (lists, tables, tab bodies); pushing an explicit font
    keeps Tasks / Calendar / Reports in sync with the menu bar.
    """
    root.setFont(font)
    for w in root.findChildren(QWidget):
        w.setFont(font)


def reset_text_scale_baseline_for_tests() -> None:
    """Clear cached baseline (unit tests only)."""
    global _baseline_font
    _baseline_font = None
