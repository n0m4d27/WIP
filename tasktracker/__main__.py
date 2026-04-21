from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from tasktracker import launcher_settings as ls
from tasktracker.db.schema_upgrade import upgrade_schema
from tasktracker.db.session import get_engine, init_schema, make_session_factory
from tasktracker.paths import default_data_dir
from tasktracker.security.crypto import decrypt_file, encrypt_file
from tasktracker.security.password import (
    create_auth_record,
    derive_fernet,
    load_auth_record,
    verify_password,
)
from tasktracker.ui.auth_dialogs import (
    SWITCH_VAULT_REQUESTED,
    run_login_dialog,
    run_setup_password_dialog,
)
from tasktracker.ui.main_window import MainWindow
from tasktracker.ui.settings_store import get_theme_id, load_ui_settings
from tasktracker.ui.themes import apply_theme
from tasktracker.ui.vault_dialogs import run_vault_picker_dialog


def _resolve_startup_vault(
    args: argparse.Namespace, launcher: ls.LauncherSettings
) -> tuple[Path | None, str | None]:
    """Resolve which vault to open at startup.

    Precedence (first match wins):

    1. ``--pick-vault`` CLI flag -> always show picker
    2. ``TASKTRACKER_DATA`` env var (unchanged legacy behaviour)
    3. Pinned default vault from ``launcher.json``
    4. Last-opened vault from ``launcher.json``
    5. Show the vault picker

    Returns ``(chosen_vault, stale_notification)``. When the cached
    default/last-opened path no longer exists we still fall through to
    the picker, but surface a status-bar notification once the main
    window shows so the user understands why their default didn't
    auto-open.
    """
    stale_message: str | None = None

    if args.pick_vault:
        return None, None

    env_raw = os.environ.get("TASKTRACKER_DATA")
    if env_raw:
        p = Path(env_raw).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p, None

    for candidate, tag in (
        (launcher.default_vault, "Pinned default vault"),
        (launcher.last_opened, "Last-opened vault"),
    ):
        if not candidate:
            continue
        p = Path(candidate).expanduser()
        if p.exists() and p.is_dir():
            return p.resolve(), None
        stale_message = (
            f"{tag} no longer exists ({candidate}); please pick one."
        )
        # Don't try to "fix" the launcher file here - the picker path
        # below will overwrite last_opened with whatever the user chooses
        # next, and we intentionally leave the pin alone so the user can
        # see and clear it explicitly.

    return None, stale_message


def main() -> None:
    parser = argparse.ArgumentParser(prog="tasktracker")
    parser.add_argument(
        "--pick-vault",
        action="store_true",
        help="Skip the saved default vault and show the picker.",
    )
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)

    cfg_path = ls.launcher_config_path()
    launcher = ls.load(cfg_path)

    data_dir, startup_notice = _resolve_startup_vault(args, launcher)
    if data_dir is None:
        chosen = run_vault_picker_dialog(default_data_dir(), launcher=launcher)
        if chosen is None:
            raise SystemExit(0)
        data_dir = chosen.resolve()
        # run_vault_picker_dialog already recorded this in ``launcher``;
        # persist before we do anything destructive so if the app
        # crashes mid-setup the next run remembers the right folder.
        try:
            ls.save(cfg_path, launcher)
        except OSError:
            pass
    else:
        ls.record_opened(launcher, data_dir)
        try:
            ls.save(cfg_path, launcher)
        except OSError:
            pass
    os.environ["TASKTRACKER_DATA"] = str(data_dir)

    # Apply the saved color theme *before* the login dialog so the
    # theme covers the entire session, not just the main window.
    # We intentionally load ui_settings after the vault is resolved
    # because the settings file lives under ``<vault>/app_data/``;
    # each vault can carry its own theme preference.
    try:
        apply_theme(app, get_theme_id(load_ui_settings()))
    except Exception:
        # Never block startup on a theming failure - a missing or
        # malformed settings file will fall back to the system theme.
        pass

    auth_path = data_dir / "auth.json"
    db_plain = data_dir / "tasks.db"
    db_enc = data_dir / "tasks.db.enc"

    fernet = None
    need_fresh_schema = False

    if not auth_path.exists():
        pwd = run_setup_password_dialog()
        if pwd is None:
            raise SystemExit(0)
        record = create_auth_record(pwd)
        auth_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        fernet = derive_fernet(pwd, record)
        need_fresh_schema = True
    else:
        record = load_auth_record(auth_path)
        while True:
            pwd_result = run_login_dialog(vault_path=str(data_dir))
            if pwd_result is None:
                raise SystemExit(0)
            if pwd_result is SWITCH_VAULT_REQUESTED:
                # Relaunch with --pick-vault so the user can choose or
                # create a different vault. Keep the current QApp alive
                # long enough to spawn the child, then quit cleanly.
                _relaunch_with_pick_vault()
                raise SystemExit(0)
            assert isinstance(pwd_result, str)
            if verify_password(pwd_result, record):
                fernet = derive_fernet(pwd_result, record)
                break
            QMessageBox.warning(None, "Login", "Incorrect password. Please try again.")

    if need_fresh_schema:
        for p in (db_plain, db_enc):
            if p.exists():
                p.unlink()
        engine = get_engine(db_plain)
        init_schema(engine)
        upgrade_schema(engine)
    else:
        if db_plain.exists() and db_enc.exists():
            db_enc.unlink()
        elif db_enc.exists() and not db_plain.exists():
            decrypt_file(db_enc, db_plain, fernet)
        if not db_plain.exists():
            engine = get_engine(db_plain)
            init_schema(engine)
            upgrade_schema(engine)
        else:
            engine = get_engine(db_plain)
            upgrade_schema(engine)

    assert fernet is not None

    def secure_shutdown() -> None:
        engine.dispose()
        if db_plain.exists():
            encrypt_file(db_plain, db_enc, fernet)
            db_plain.unlink()

    session_factory = make_session_factory(engine)
    win = MainWindow(
        session_factory,
        engine=engine,
        secure_shutdown=secure_shutdown,
        startup_notice=startup_notice,
    )
    win.show()
    raise SystemExit(app.exec())


def _relaunch_with_pick_vault() -> None:
    """Spawn a new process of the same program with ``--pick-vault``."""
    import subprocess

    # Works for both ``python -m tasktracker`` and a PyInstaller bundle.
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--pick-vault"]
    else:
        cmd = [sys.executable, "-m", "tasktracker", "--pick-vault"]
    try:
        subprocess.Popen(cmd, close_fds=True)
    except OSError:
        # Best effort - if the relaunch fails the user can start the
        # app manually. Not worth raising a modal dialog here.
        pass


if __name__ == "__main__":
    main()
