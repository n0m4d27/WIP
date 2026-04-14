"""Resolve self-contained data directories for vault-based storage."""

from __future__ import annotations

import os
from pathlib import Path


def default_data_dir() -> Path:
    """Return default local data directory path (without creating it).

    Precedence:
    - ``TASKTRACKER_DATA`` env var
    - ``<repo_root>/app_data`` when running from source checkout
    - ``<cwd>/app_data`` fallback
    """
    raw = os.environ.get("TASKTRACKER_DATA")
    if raw:
        return Path(raw).expanduser().resolve()

    pkg_parent = Path(__file__).resolve().parent.parent
    if (pkg_parent / "pyproject.toml").exists():
        return (pkg_parent / "app_data").resolve()
    return (Path.cwd() / "app_data").resolve()


def get_app_data_dir() -> Path:
    """Return data dir and create it if missing."""
    p = default_data_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p
