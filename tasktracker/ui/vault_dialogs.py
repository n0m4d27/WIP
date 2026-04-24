"""Vault selection dialog.

The picker is shown either at launch (when no default/last-opened vault
could be used) or on demand when the user invokes "Switch vault…" from
Settings / the login dialog. It also surfaces the user's recent vault
list and an opt-in "always open this vault on launch" pin so returning
users skip the picker on subsequent runs.

All launcher-state mutation is wired through :mod:`tasktracker.launcher_settings`
so the picker is the single UI for touching ``launcher.json``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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

from tasktracker.launcher_settings import (
    LauncherSettings,
    clear_default,
    record_opened,
    set_default,
)


def run_vault_picker_dialog(
    default_path: Path,
    parent=None,
    *,
    launcher: LauncherSettings | None = None,
) -> Path | None:
    """Pick a vault folder to open or create.

    When ``launcher`` is supplied, the dialog shows a recent-vaults combo
    and an "always open this vault on launch" checkbox; on accept it
    mutates ``launcher`` (recording the opened path and updating the
    pinned default) but does **not** persist to disk — the caller is
    responsible for :func:`tasktracker.launcher_settings.save` so the
    startup flow can keep all disk I/O in one place.
    """
    inst = QApplication.instance()
    if inst is not None:
        inst.setQuitOnLastWindowClosed(False)
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

    # Recent-vaults convenience combo. Only shown when we were given a
    # launcher object with at least one recent entry; otherwise the
    # original layout is preserved.
    recents_combo: QComboBox | None = None
    if launcher is not None and launcher.recent_vaults:
        recents_combo = QComboBox()
        recents_combo.addItem("— Recent vaults —", None)
        for p in launcher.recent_vaults:
            recents_combo.addItem(p, p)

        def on_recent(idx: int) -> None:
            data = recents_combo.itemData(idx) if recents_combo is not None else None
            if isinstance(data, str) and data:
                path_edit.setText(data)

        recents_combo.currentIndexChanged.connect(on_recent)
        form.addRow("Recent", recents_combo)

    form.addRow("Vault folder", row)

    # "Always open this vault on launch" pin. Pre-populated when the
    # current path matches the saved default so users can see at a glance
    # which vault is pinned, and an explicit Clear button lets them
    # unpin without having to open another dialog.
    chk_default: QCheckBox | None = None
    btn_clear_default: QPushButton | None = None
    if launcher is not None:
        chk_default = QCheckBox("Always open this vault on launch")
        if launcher.default_vault:
            try:
                current = str(Path(path_edit.text()).expanduser().resolve())
                chk_default.setChecked(current == launcher.default_vault)
            except OSError:
                chk_default.setChecked(False)
        form.addRow("", chk_default)

        default_label = QLabel(
            launcher.default_vault or "(none pinned yet)"
        )
        default_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        btn_clear_default = QPushButton("Clear pinned default")
        btn_clear_default.setEnabled(bool(launcher.default_vault))

        def do_clear() -> None:
            if launcher is None:
                return
            clear_default(launcher)
            default_label.setText("(none pinned yet)")
            if chk_default is not None:
                chk_default.setChecked(False)
            if btn_clear_default is not None:
                btn_clear_default.setEnabled(False)

        btn_clear_default.clicked.connect(do_clear)
        pinned_row = QHBoxLayout()
        pinned_row.addWidget(default_label, 1)
        pinned_row.addWidget(btn_clear_default)
        form.addRow("Pinned default", pinned_row)

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

    if launcher is not None:
        record_opened(launcher, picked)
        if chk_default is not None:
            if chk_default.isChecked():
                set_default(launcher, picked)
            else:
                # Unchecking in the dialog must clear an existing pin
                # even if the user didn't click the dedicated Clear
                # button; otherwise the toggle is surprising.
                if launcher.default_vault == str(picked):
                    clear_default(launcher)

    return picked
