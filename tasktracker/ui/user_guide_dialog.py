from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
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

_BUNDLE_GUIDE = Path(__file__).resolve().parent.parent / "resources" / "user_guide.html"

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

        guide = QTextBrowser()
        guide.setOpenExternalLinks(True)
        guide.setHtml(_load_bundle_html())
        tabs.addTab(guide, "Application guide")

        self._personal = QTextEdit()
        self._personal.setAcceptRichText(True)
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
