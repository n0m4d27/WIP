from __future__ import annotations

from typing import Final

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


# Sentinel object returned by :func:`run_login_dialog` when the user
# clicks "Switch vault…". Caller compares by identity (``is``) and
# relaunches the app with ``--pick-vault`` instead of attempting to
# decrypt the current vault.
SWITCH_VAULT_REQUESTED: Final[object] = object()


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


def run_login_dialog(parent=None, *, vault_path: str | None = None):
    """Prompt for the vault password.

    Returns:
        * ``str`` — the entered password,
        * ``None`` — the user cancelled,
        * :data:`SWITCH_VAULT_REQUESTED` — the user clicked "Switch
          vault…" and wants the startup flow to relaunch the app with
          the vault picker.

    ``vault_path`` is shown as an informational hint so the user knows
    which vault they're about to unlock.
    """
    d = QDialog(parent)
    d.setWindowTitle("Unlock Task Tracker")
    d.setMinimumWidth(360)

    pw = QLineEdit()
    pw.setEchoMode(QLineEdit.EchoMode.Password)
    form = QFormLayout()
    form.addRow("Password", pw)

    lay = QVBoxLayout(d)
    if vault_path:
        hint = QLabel(f"Vault: {vault_path}")
        hint.setWordWrap(True)
        lay.addWidget(hint)
    lay.addLayout(form)

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    # "Switch vault…" lives on the button bar on the ActionRole side so
    # it sits between OK/Cancel and the left edge; clicking it does not
    # accept or reject - it raises a sentinel via ``d.done(2)``.
    btn_switch = QPushButton("Switch vault…")
    buttons.addButton(btn_switch, QDialogButtonBox.ButtonRole.ActionRole)
    btn_switch.clicked.connect(lambda: d.done(2))
    buttons.accepted.connect(d.accept)
    buttons.rejected.connect(d.reject)

    # Put the password Ok/Cancel buttons on the right; the switch button
    # was already placed by ``addButton`` above.
    bar = QHBoxLayout()
    bar.addWidget(buttons)
    lay.addLayout(bar)

    code = d.exec()
    if code == QDialog.DialogCode.Accepted:
        return pw.text()
    if code == 2:
        return SWITCH_VAULT_REQUESTED
    return None
