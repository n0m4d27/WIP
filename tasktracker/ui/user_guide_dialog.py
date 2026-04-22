from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
)

from tasktracker.paths import get_app_data_dir
from tasktracker.ui.settings_store import get_theme_id, load_ui_settings
from tasktracker.ui.themes import get_theme

_BUNDLE_GUIDE = Path(__file__).resolve().parent.parent / "resources" / "user_guide.html"

# Shipped `user_guide.html` — patch these inside the first `<style>` block. Qt's rich-text
# engine often honors only the first stylesheet, so a second `<style>` alone may do nothing.
_CODE_RULE_LIGHT = "code { background: #f0f0f0; padding: 0 0.2em; }"
_CODE_RULE_LIGHT_SHORT = "code { background: #f0f0f0; }"
_CODE_RULE_DARK = "code { background-color: #2d2d2d; color: #e8e8e8; padding: 0 0.2em; }"
_H2_BORDER_LIGHT = "border-bottom: 1px solid #ccc;"
_H2_BORDER_DARK = "border-bottom: 1px solid #555;"

# Fallback when the HTML does not match the bundled rules (custom / missing install).
_DARK_GUIDE_STYLE_OVERRIDE = (
    "<style>code { background-color: #2d2d2d; color: #e8e8e8; padding: 0 0.2em; }"
    "h2 { border-bottom-color: #555; }</style>"
)

_DEFAULT_PERSONAL = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<h2>My usage notes</h2>
<p><i>Edit below to record what you put in each field and how you use the app. Click Save to write to <code>app_data/personal_usage.html</code>.</i></p>
<h3>Task title</h3><p></p>
<h3>Description</h3><p></p>
<h3>Impact / Urgency</h3><p></p>
<h3>Todos &amp; milestones</h3><p></p>
<h3>Notes</h3><p></p>
<h3>Blockers</h3><p></p>
<h3>Recurring templates</h3><p></p>
<h3>Anything else</h3><p></p>
</body></html>"""


def _personal_path() -> Path:
    return get_app_data_dir() / "personal_usage.html"


def _load_bundle_html() -> str:
    if _BUNDLE_GUIDE.is_file():
        return _BUNDLE_GUIDE.read_text(encoding="utf-8")
    return "<p>User guide file is missing from the installation.</p>"


def _guide_html_with_theme(html: str, *, is_dark: bool) -> str:
    """Darken ``code`` / ``h2`` rules for light-on-dark chrome.

    Prefer editing the existing ``<style>`` block so Qt's QTextDocument actually applies
    the change; append ``_DARK_GUIDE_STYLE_OVERRIDE`` only if no known light ``code`` rule
    was found but a ``</style>`` tag exists.
    """
    if not is_dark:
        return html
    patched = html
    code_ok = False
    if _CODE_RULE_LIGHT in patched:
        patched = patched.replace(_CODE_RULE_LIGHT, _CODE_RULE_DARK, 1)
        code_ok = True
    elif _CODE_RULE_LIGHT_SHORT in patched:
        patched = patched.replace(_CODE_RULE_LIGHT_SHORT, _CODE_RULE_DARK, 1)
        code_ok = True
    if _H2_BORDER_LIGHT in patched:
        patched = patched.replace(_H2_BORDER_LIGHT, _H2_BORDER_DARK, 1)
    if code_ok:
        return patched
    if "</style>" in patched:
        return patched.replace("</style>", f"</style>{_DARK_GUIDE_STYLE_OVERRIDE}", 1)
    return f"<head>{_DARK_GUIDE_STYLE_OVERRIDE}</head>{patched}"


def _rich_text_default_stylesheet(*, is_dark: bool) -> str:
    """Qt rich-text default stylesheet; set on the document before ``setHtml``."""
    if is_dark:
        return (
            "code { background-color: #2d2d2d; color: #e8e8e8; padding: 0 0.2em; }"
            "h2 { border-bottom: 1px solid #555; }"
        )
    return "code { background-color: #f0f0f0; padding: 0 0.2em; } h2 { border-bottom: 1px solid #ccc; }"


def _palette_suggests_dark_chrome(palette: QPalette) -> bool:
    """True when window text is materially lighter than the window (dark chrome)."""
    w = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
    wt = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText)
    return wt.lightness() > w.lightness() + 15


def _guide_needs_dark_code_contrast() -> bool:
    """Use persisted theme hint and the live application palette (always in sync with apply_theme)."""
    if get_theme(get_theme_id(load_ui_settings())).is_dark:
        return True
    app = QApplication.instance()
    if app is None:
        return False
    return _palette_suggests_dark_chrome(app.palette())


def _load_personal_html() -> str:
    path = _personal_path()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return _DEFAULT_PERSONAL


def _save_personal_html(html: str) -> None:
    path = _personal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


class UserGuideDialog(QDialog):
    """Built-in guide (read-only) + editable personal usage notes in app_data."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("User guide")
        self.resize(720, 560)

        tabs = QTabWidget()

        is_dark = _guide_needs_dark_code_contrast()
        guide = QTextBrowser()
        guide.setOpenExternalLinks(True)
        guide.setHtml(_guide_html_with_theme(_load_bundle_html(), is_dark=is_dark))
        tabs.addTab(guide, "Application guide")

        self._personal = QTextEdit()
        self._personal.setAcceptRichText(True)
        self._personal.document().setDefaultStyleSheet(_rich_text_default_stylesheet(is_dark=is_dark))
        self._personal.setHtml(_load_personal_html())
        tabs.addTab(self._personal, "My notes")

        save_row = QHBoxLayout()
        save_btn = QPushButton("Save my notes")
        save_btn.clicked.connect(self._on_save_personal)
        lbl = QLabel("Stored in your app data folder as personal_usage.html")
        lbl.setStyleSheet("color: #555;")
        save_row.addWidget(save_btn)
        save_row.addWidget(lbl)
        save_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addLayout(save_row)
        root.addWidget(buttons)

    def _on_save_personal(self) -> None:
        _save_personal_html(self._personal.toHtml())
        QMessageBox.information(self, "My notes", "Saved to personal_usage.html in your app data folder.")


def run_user_guide_dialog(parent=None) -> None:
    UserGuideDialog(parent).exec()
