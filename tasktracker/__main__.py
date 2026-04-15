from __future__ import annotations

import json
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

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
from tasktracker.ui.auth_dialogs import run_login_dialog, run_setup_password_dialog
from tasktracker.ui.main_window import MainWindow
from tasktracker.ui.vault_dialogs import run_vault_picker_dialog


def main() -> None:
    app = QApplication(sys.argv)

    if os.environ.get("TASKTRACKER_DATA"):
        data_dir = default_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
    else:
        chosen = run_vault_picker_dialog(default_data_dir())
        if chosen is None:
            raise SystemExit(0)
        data_dir = chosen.resolve()
        os.environ["TASKTRACKER_DATA"] = str(data_dir)

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
            pwd = run_login_dialog()
            if pwd is None:
                raise SystemExit(0)
            if verify_password(pwd, record):
                fernet = derive_fernet(pwd, record)
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
        # Crash recovery: if both files exist, keep plaintext (newer work) and drop stale ciphertext.
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
    win = MainWindow(session_factory, engine=engine, secure_shutdown=secure_shutdown)
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
