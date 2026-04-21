"""Persist UI preferences (task panel order, shortcuts) under the vault app_data folder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tasktracker.paths import get_app_data_dir
from tasktracker.ui.themes import DEFAULT_THEME_ID, THEMES_BY_ID

SETTINGS_FILENAME = "ui_settings.json"

# Ordered section ids for the movable blocks below core task fields on the Tasks tab.
TASK_SECTION_IDS: tuple[str, ...] = ("todos", "notes", "blockers", "recurring", "activity")

TASK_SECTION_LABELS: dict[str, str] = {
    "todos": "Todos (ordered)",
    "notes": "Notes (rich text)",
    "blockers": "Blockers",
    "recurring": "Recurring (template todos for next instance)",
    "activity": "Activity (audit + notes)",
}

# Where each section renders on the Tasks tab. "inline" = stacked VBox below the
# core fields; "tab" = added as a page in a QTabWidget that takes remaining space.
# Tabs are intended for sections whose content can grow arbitrarily tall
# (notes, audit timeline) so a single task with heavy history does not push
# light sections off-screen.
TASK_SECTION_PLACEMENT: dict[str, str] = {
    "todos": "inline",
    "blockers": "inline",
    "recurring": "inline",
    "notes": "tab",
    "activity": "tab",
}

# Short tab captions (the inline groupboxes keep their long label as their box
# title; tabs only have room for a short name).
TASK_SECTION_TAB_LABELS: dict[str, str] = {
    "notes": "Notes",
    "activity": "Activity",
}

# Default shortcuts (user-customizable via Settings). Suggested mapping:
# - New Task: common “new” accelerator
# - Save Task: common “save” accelerator
# - Close Task: Ctrl+Shift+C avoids stealing Ctrl+W (often “close window” / tab)
DEFAULT_SHORTCUTS: dict[str, str] = {
    "new_task": "Ctrl+N",
    "save_task": "Ctrl+S",
    "close_task": "Ctrl+Shift+C",
}

# Default Qt date display format. The string is a Qt ``QDateEdit.setDisplayFormat``
# pattern: ``yyyy`` = 4-digit year, ``MM`` = zero-padded month, ``MMM`` = short
# month name, ``dd`` = zero-padded day, ``d`` = unpadded day. ISO is the default
# because it is unambiguous and sortable; end-users can override via Settings.
DEFAULT_DATE_FORMAT: str = "yyyy-MM-dd"

# Rejected as unsafe (empty / whitespace-only / too long to be a date pattern).
# Full validation lives in ``tasktracker.ui.date_format``; this constant is the
# absolute ceiling for persisted values so a corrupt settings file can't cause
# the app to try to render a 20 KB format string for every date widget.
_MAX_DATE_FORMAT_LEN = 64

# Known report ids surfaced in the Reports tab. Kept here so the UI and the
# settings store agree on which keys are valid; unknown keys read from disk
# are simply ignored on load (no hard failure if older settings exist).
REPORT_IDS: tuple[str, ...] = (
    "wip_aging",
    "throughput",
    "workload",
    "sla",
    "category_mix",
    "weekly_status",
)


def default_ui_settings() -> dict[str, Any]:
    return {
        "task_panel_section_order": list(TASK_SECTION_IDS),
        "shortcuts": dict(DEFAULT_SHORTCUTS),
        "date_format": DEFAULT_DATE_FORMAT,
        # Color theme id (see :mod:`tasktracker.ui.themes`). "system" keeps
        # the current platform defaults and is the safest starting point.
        "theme": DEFAULT_THEME_ID,
        # Per-report last-used parameters (e.g. date ranges, period, group_by).
        # Stored as a JSON-friendly mapping so the Reports tab can repopulate
        # its widgets without re-deriving defaults each session. Schema is
        # intentionally loose: each report owns its own keys.
        "reports": {"last_params": {}},
    }


def _coerce_theme_id(raw: Any) -> str:
    """Return a known theme id or fall back to the default.

    Users who hand-edit ``ui_settings.json`` to an unknown theme id
    get quietly reset to the system theme rather than an error dialog.
    """
    if isinstance(raw, str) and raw in THEMES_BY_ID:
        return raw
    return DEFAULT_THEME_ID


def _coerce_date_format(raw: Any) -> str:
    """Return a safe date-format string, falling back to the default.

    Accepts any short non-empty string - richer syntactic validation
    happens at render time. This pass only protects us from obvious
    disk corruption (wrong type, empty, unboundedly long)."""
    if not isinstance(raw, str):
        return DEFAULT_DATE_FORMAT
    trimmed = raw.strip()
    if not trimmed or len(trimmed) > _MAX_DATE_FORMAT_LEN:
        return DEFAULT_DATE_FORMAT
    return trimmed


def normalize_section_order(order: list[Any]) -> list[str]:
    """Return a permutation of TASK_SECTION_IDS: user order first, then any missing tails."""
    seen: set[str] = set()
    out: list[str] = []
    for x in order:
        s = str(x)
        if s in TASK_SECTION_IDS and s not in seen:
            out.append(s)
            seen.add(s)
    for sid in TASK_SECTION_IDS:
        if sid not in seen:
            out.append(sid)
    return out


def load_ui_settings() -> dict[str, Any]:
    base = default_ui_settings()
    path: Path = get_app_data_dir() / SETTINGS_FILENAME
    if not path.exists():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(raw, dict):
        return base
    if isinstance(raw.get("task_panel_section_order"), list):
        base["task_panel_section_order"] = normalize_section_order(raw["task_panel_section_order"])
    if isinstance(raw.get("shortcuts"), dict):
        merged = dict(DEFAULT_SHORTCUTS)
        for k, v in raw["shortcuts"].items():
            if k in DEFAULT_SHORTCUTS and isinstance(v, str):
                merged[k] = v
        base["shortcuts"] = merged
    if "date_format" in raw:
        base["date_format"] = _coerce_date_format(raw["date_format"])
    if "theme" in raw:
        base["theme"] = _coerce_theme_id(raw["theme"])
    if isinstance(raw.get("reports"), dict):
        last = raw["reports"].get("last_params")
        if isinstance(last, dict):
            cleaned: dict[str, dict[str, Any]] = {}
            for rid, params in last.items():
                if rid in REPORT_IDS and isinstance(params, dict):
                    cleaned[rid] = {
                        str(k): v for k, v in params.items() if isinstance(k, str)
                    }
            base["reports"]["last_params"] = cleaned
    return base


def get_date_format_qt(settings: dict[str, Any]) -> str:
    """Return the Qt date-display format stored in ``settings`` (or the default).

    Callers pass the result straight into ``QDateEdit.setDisplayFormat`` and
    into the helpers in :mod:`tasktracker.ui.date_format` for rendering
    read-only date strings.
    """
    return _coerce_date_format(settings.get("date_format"))


def set_date_format_qt(settings: dict[str, Any], fmt: str) -> None:
    """In-place mutate ``settings`` to persist ``fmt`` on the next save."""
    settings["date_format"] = _coerce_date_format(fmt)


def get_theme_id(settings: dict[str, Any]) -> str:
    """Return the theme id stored in ``settings`` (or the default)."""
    return _coerce_theme_id(settings.get("theme"))


def set_theme_id(settings: dict[str, Any], theme_id: str) -> None:
    """Persist ``theme_id`` in ``settings`` after validating it."""
    settings["theme"] = _coerce_theme_id(theme_id)


def get_report_params(settings: dict[str, Any], report_id: str) -> dict[str, Any]:
    """Return the saved parameter dict for ``report_id``, or an empty dict
    when the report has never been run before."""
    reports = settings.get("reports") or {}
    last = reports.get("last_params") or {}
    params = last.get(report_id)
    return dict(params) if isinstance(params, dict) else {}


def set_report_params(
    settings: dict[str, Any], report_id: str, params: dict[str, Any]
) -> None:
    """Mutate ``settings`` so the next ``save_ui_settings`` persists the new
    params for ``report_id``."""
    reports = settings.setdefault("reports", {"last_params": {}})
    last = reports.setdefault("last_params", {})
    last[report_id] = dict(params)


def save_ui_settings(data: dict[str, Any]) -> None:
    path = get_app_data_dir() / SETTINGS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
