"""Per-user launcher state persisted outside any vault.

Remembers the last-opened vault plus an optional user-pinned "default
vault" so the program can skip the vault picker on most launches. The
config file lives in the OS-specific user config directory (resolved
via ``QStandardPaths`` in :func:`launcher_config_path`) rather than
inside any vault, because we don't know which vault to open until this
data is read.

This module is intentionally Qt-free at import time: everything that
takes / returns data uses plain paths and a dataclass so it can be
unit-tested without spinning up a ``QApplication``. Only
:func:`launcher_config_path` reaches into Qt, and only when called.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
LAUNCHER_FILENAME = "launcher.json"
MAX_RECENTS = 5


@dataclass
class LauncherSettings:
    """Launcher-wide preferences persisted outside the active vault."""

    version: int = SCHEMA_VERSION
    last_opened: str | None = None
    default_vault: str | None = None
    recent_vaults: list[str] = field(default_factory=list)


def launcher_config_path() -> Path:
    """Return the absolute path to the launcher config file.

    Uses :class:`PySide6.QtCore.QStandardPaths` so the location matches
    the platform conventions (``%APPDATA%/TaskTracker`` on Windows,
    ``~/.config/TaskTracker`` under XDG, ``~/Library/Application
    Support/TaskTracker`` on macOS). Falls back to ``~/.config/TaskTracker``
    if Qt can't resolve an AppConfig location for some reason.
    """
    try:
        from PySide6.QtCore import QStandardPaths
    except ImportError:
        return Path.home() / ".config" / "TaskTracker" / LAUNCHER_FILENAME

    root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    )
    if not root:
        root = str(Path.home() / ".config" / "TaskTracker")
    return Path(root) / LAUNCHER_FILENAME


def _normalize(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def load(config_path: Path) -> LauncherSettings:
    """Load settings from ``config_path``; return defaults on missing / malformed files.

    The JSON schema is forward-compatible: unknown keys and a higher
    ``version`` number are ignored rather than raising, so launching an
    older binary against a newer config won't clobber the user's state.
    """
    if not config_path.exists():
        return LauncherSettings()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LauncherSettings()
    if not isinstance(raw, dict):
        return LauncherSettings()

    last = raw.get("last_opened")
    default = raw.get("default_vault")
    recents_raw = raw.get("recent_vaults") or []
    recents = [str(x) for x in recents_raw if isinstance(x, str)][:MAX_RECENTS]
    version_raw = raw.get("version", SCHEMA_VERSION)
    version = version_raw if isinstance(version_raw, int) else SCHEMA_VERSION

    return LauncherSettings(
        version=version,
        last_opened=str(last) if isinstance(last, str) and last else None,
        default_vault=str(default) if isinstance(default, str) and default else None,
        recent_vaults=recents,
    )


def save(config_path: Path, settings: LauncherSettings) -> None:
    """Persist ``settings`` at ``config_path`` (creating parent dirs)."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "last_opened": settings.last_opened,
        "default_vault": settings.default_vault,
        "recent_vaults": list(settings.recent_vaults),
    }
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def record_opened(settings: LauncherSettings, path: Path | str) -> None:
    """Mark ``path`` as the most-recently-opened vault.

    Updates ``last_opened`` and moves the path to the front of
    ``recent_vaults`` (deduplicating and trimming to :data:`MAX_RECENTS`).
    The caller is responsible for persisting via :func:`save`.
    """
    p = _normalize(path)
    settings.last_opened = p
    recents: list[str] = [p]
    for existing in settings.recent_vaults:
        if existing and existing != p and existing not in recents:
            recents.append(existing)
        if len(recents) >= MAX_RECENTS:
            break
    settings.recent_vaults = recents[:MAX_RECENTS]


def set_default(settings: LauncherSettings, path: Path | str | None) -> None:
    """Pin (or unpin) ``path`` as the vault to auto-open on launch.

    Passing ``None`` clears the pinned default. Does not affect
    ``recent_vaults`` or ``last_opened``; the caller decides whether to
    persist via :func:`save`.
    """
    settings.default_vault = None if path is None else _normalize(path)


def clear_default(settings: LauncherSettings) -> None:
    """Remove any pinned default vault. Equivalent to ``set_default(..., None)``."""
    settings.default_vault = None
