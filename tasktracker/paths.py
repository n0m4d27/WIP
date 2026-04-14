"""Resolve the single self-contained data directory (no user profile paths)."""

from __future__ import annotations

import os
from pathlib import Path


def get_app_data_dir() -> Path:
    """All app files live under this directory (database, auth metadata).

    - If ``TASKTRACKER_DATA`` is set, that path is used (expanded).
    - Else if ``pyproject.toml`` sits next to the ``tasktracker`` package parent
      (normal clone / editable install), use ``<that root>/app_data``.
    - Else use ``<cwd>/app_data``.
    """
    raw = os.environ.get("TASKTRACKER_DATA")
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        pkg_parent = Path(__file__).resolve().parent.parent
        if (pkg_parent / "pyproject.toml").exists():
            p = (pkg_parent / "app_data").resolve()
        else:
            p = (Path.cwd() / "app_data").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p
