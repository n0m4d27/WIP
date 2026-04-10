from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from tasktracker.db.session import get_engine, init_schema, make_session_factory
from tasktracker.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    engine = get_engine()
    init_schema(engine)
    session_factory = make_session_factory(engine)
    win = MainWindow(session_factory)
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
