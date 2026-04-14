from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


def run_vault_picker_dialog(default_path: Path, parent=None) -> Path | None:
    """Pick a vault folder to open or create."""
    d = QDialog(parent)
    d.setWindowTitle("Select task vault")
    d.setMinimumWidth(560)

    info = QLabel(
        "Choose a folder for this task vault. "
        "Each folder has its own password and encrypted data files."
    )
    info.setWordWrap(True)

    path_edit = QLineEdit(str(default_path))
    browse = QPushButton("Browse…")

    def do_browse() -> None:
        picked = QFileDialog.getExistingDirectory(
            d,
            "Choose vault folder",
            path_edit.text() or str(default_path),
        )
        if picked:
            path_edit.setText(picked)

    browse.clicked.connect(do_browse)

    row = QHBoxLayout()
    row.addWidget(path_edit, 1)
    row.addWidget(browse)

    form = QFormLayout()
    form.addRow("Vault folder", row)

    btn_open = QPushButton("Open existing vault")
    btn_create = QPushButton("Create new vault")
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    buttons.rejected.connect(d.reject)

    def choose_open() -> None:
        p = Path(path_edit.text().strip()).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            QMessageBox.warning(d, "Vault", "Choose an existing folder.")
            return
        d.accept()

    def choose_create() -> None:
        p = Path(path_edit.text().strip()).expanduser().resolve()
        if not str(p):
            QMessageBox.warning(d, "Vault", "Choose a folder path.")
            return
        p.mkdir(parents=True, exist_ok=True)
        d.accept()

    btn_open.clicked.connect(choose_open)
    btn_create.clicked.connect(choose_create)

    action_row = QHBoxLayout()
    action_row.addWidget(btn_open)
    action_row.addWidget(btn_create)

    root = QVBoxLayout(d)
    root.addWidget(info)
    root.addLayout(form)
    root.addLayout(action_row)
    root.addWidget(buttons)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None

    picked = Path(path_edit.text().strip()).expanduser().resolve()
    picked.mkdir(parents=True, exist_ok=True)
    return picked
