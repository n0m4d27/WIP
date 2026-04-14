from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)


def run_setup_password_dialog(parent=None) -> str | None:
    """Return new password or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Set master password")
    d.setMinimumWidth(360)

    info = QLabel(
        "Choose a master password for this data folder. "
        "It encrypts your database when the app closes. "
        "If you lose it, the data cannot be recovered."
    )
    info.setWordWrap(True)

    pw1 = QLineEdit()
    pw1.setEchoMode(QLineEdit.EchoMode.Password)
    pw2 = QLineEdit()
    pw2.setEchoMode(QLineEdit.EchoMode.Password)

    form = QFormLayout()
    form.addRow("Password", pw1)
    form.addRow("Confirm", pw2)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(d.accept)
    buttons.rejected.connect(d.reject)

    lay = QVBoxLayout(d)
    lay.addWidget(info)
    lay.addLayout(form)
    lay.addWidget(buttons)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    a, b = pw1.text(), pw2.text()
    if len(a) < 8:
        QMessageBox.warning(parent or d, "Password", "Use at least 8 characters.")
        return run_setup_password_dialog(parent)
    if a != b:
        QMessageBox.warning(parent or d, "Password", "Passwords do not match.")
        return run_setup_password_dialog(parent)
    return a


def run_login_dialog(parent=None) -> str | None:
    """Return password or None if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle("Unlock Task Tracker")
    d.setMinimumWidth(320)

    pw = QLineEdit()
    pw.setEchoMode(QLineEdit.EchoMode.Password)
    form = QFormLayout()
    form.addRow("Password", pw)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(d.accept)
    buttons.rejected.connect(d.reject)

    lay = QVBoxLayout(d)
    lay.addLayout(form)
    lay.addWidget(buttons)

    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return pw.text()
