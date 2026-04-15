"""Persist UI preferences (task panel order, shortcuts) under the vault app_data folder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tasktracker.paths import get_app_data_dir

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

# Default shortcuts (user-customizable via Settings). Suggested mapping:
# - New Task: common “new” accelerator
# - Save Task: common “save” accelerator
# - Close Task: Ctrl+Shift+C avoids stealing Ctrl+W (often “close window” / tab)
DEFAULT_SHORTCUTS: dict[str, str] = {
    "new_task": "Ctrl+N",
    "save_task": "Ctrl+S",
    "close_task": "Ctrl+Shift+C",
}


def default_ui_settings() -> dict[str, Any]:
    return {
        "task_panel_section_order": list(TASK_SECTION_IDS),
        "shortcuts": dict(DEFAULT_SHORTCUTS),
    }


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
    return base


def save_ui_settings(data: dict[str, Any]) -> None:
    path = get_app_data_dir() / SETTINGS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
