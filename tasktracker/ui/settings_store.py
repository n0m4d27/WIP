"""Persist UI preferences (task panel order, shortcuts) under the vault app_data folder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tasktracker.paths import get_app_data_dir
from tasktracker.ui.themes import DEFAULT_THEME_ID, THEMES_BY_ID

SETTINGS_FILENAME = "ui_settings.json"

# Tab ids known to the main window. Stored (as a string) under
# ``last_tab`` so startup can restore the last-used tab. Unknown values
# coerce to the default (Dashboard) rather than erroring.
KNOWN_TAB_IDS: tuple[str, ...] = (
    "dashboard",
    "tasks",
    "calendar",
    "reports",
    "holidays",
)
DEFAULT_TAB_ID: str = "dashboard"

# Schema version for persisted saved views. Kept separate from the
# settings file version so a future addition (e.g. tag filters from
# plan 06) can be introduced with a forward-compatible bump without
# disturbing other settings sections.
SAVED_VIEW_SCHEMA_VERSION: int = 1

# Upper bound on a saved-view name so the settings file can't be
# inflated by a corrupt write. Matches the 200-char limit used by
# reference data naming elsewhere.
_MAX_SAVED_VIEW_NAME_LEN: int = 200

# Ordered section ids for the movable blocks below core task fields on the Tasks tab.
TASK_SECTION_IDS: tuple[str, ...] = (
    "todos",
    "notes",
    "blockers",
    "recurring",
    "attachments",
    "activity",
)

TASK_SECTION_LABELS: dict[str, str] = {
    "todos": "Todos (ordered)",
    "notes": "Notes (rich text)",
    "blockers": "Blockers",
    "recurring": "Recurring (template todos for next instance)",
    "attachments": "Attachments",
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
    "attachments": "inline",
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

# IANA zone names can be long; cap hand-edited ``ui_settings.json`` abuse.
_MAX_DISPLAY_TIMEZONE_LEN = 120

# Sentinel: use the machine's current timezone for activity / note timestamps.
DEFAULT_DISPLAY_TIMEZONE: str = "local"

# Application text scale (multiplier on the baseline Qt font). Clamped for sanity.
DEFAULT_UI_TEXT_SCALE: float = 1.0
MIN_UI_TEXT_SCALE: float = 0.85
MAX_UI_TEXT_SCALE: float = 1.75

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
        # IANA timezone name, or "local" for the system zone (see
        # :func:`get_display_timezone`). Used when rendering activity
        # timestamps and similar; exports stay UTC / ISO.
        "display_timezone": DEFAULT_DISPLAY_TIMEZONE,
        # Interface text size multiplier (see :mod:`tasktracker.ui.text_scale`).
        "ui_text_scale": DEFAULT_UI_TEXT_SCALE,
        # Color theme id (see :mod:`tasktracker.ui.themes`). "system" keeps
        # the current platform defaults and is the safest starting point.
        "theme": DEFAULT_THEME_ID,
        # Last-used tab id so startup can restore what the user was on,
        # defaulting to the dashboard the first time.
        "last_tab": DEFAULT_TAB_ID,
        # Named filter snapshots ("saved views") for the Tasks tab. Stored
        # as an ordered list so user-driven reordering survives a save.
        # Shape per entry: {"name": str, "filters": dict, "version": int}.
        "saved_views": [],
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


def coerce_ui_text_scale(raw: Any) -> float:
    """Return a clamped text-scale multiplier (default 1.0)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_UI_TEXT_SCALE
    if v != v:  # NaN
        return DEFAULT_UI_TEXT_SCALE
    return max(MIN_UI_TEXT_SCALE, min(MAX_UI_TEXT_SCALE, v))


def _coerce_display_timezone(raw: Any) -> str:
    """Return ``local`` or a valid IANA name; otherwise default."""
    if not isinstance(raw, str):
        return DEFAULT_DISPLAY_TIMEZONE
    trimmed = raw.strip()
    if not trimmed or len(trimmed) > _MAX_DISPLAY_TIMEZONE_LEN:
        return DEFAULT_DISPLAY_TIMEZONE
    if trimmed == DEFAULT_DISPLAY_TIMEZONE:
        return trimmed
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(trimmed)
    except Exception:
        return DEFAULT_DISPLAY_TIMEZONE
    return trimmed


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


def _coerce_last_tab(raw: Any) -> str:
    """Return a known tab id or fall back to the default (Dashboard)."""
    if isinstance(raw, str) and raw in KNOWN_TAB_IDS:
        return raw
    return DEFAULT_TAB_ID


def _coerce_saved_view(raw: Any) -> dict[str, Any] | None:
    """Return a normalized saved-view dict, or ``None`` if unusable.

    A view is usable when it has a non-empty name and a JSON-object
    filters payload. Missing ``version`` is treated as the current
    schema version (we are still on v1 so the field is informational
    for now; future schema bumps can use it to migrate).
    """
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str):
        return None
    name = name.strip()
    if not name or len(name) > _MAX_SAVED_VIEW_NAME_LEN:
        return None
    filters = raw.get("filters")
    if not isinstance(filters, dict):
        return None
    # Drop keys with non-string names so we know every key is safe to
    # feed back into widget lookups. Values are left untouched: each
    # consumer validates the shape it cares about.
    filters_clean: dict[str, Any] = {
        str(k): v for k, v in filters.items() if isinstance(k, str)
    }
    version = raw.get("version")
    if not isinstance(version, int):
        version = SAVED_VIEW_SCHEMA_VERSION
    return {"name": name, "filters": filters_clean, "version": version}


def _coerce_saved_views(raw: Any) -> list[dict[str, Any]]:
    """Return a cleaned list of saved views, preserving order.

    Bad entries are dropped silently. Duplicate names (case-insensitive)
    keep only the first occurrence so the sidebar never shows two rows
    that look identical but act differently.
    """
    if not isinstance(raw, list):
        return []
    seen_names: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in raw:
        view = _coerce_saved_view(entry)
        if view is None:
            continue
        key = view["name"].casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        out.append(view)
    return out


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
    if "display_timezone" in raw:
        base["display_timezone"] = _coerce_display_timezone(raw["display_timezone"])
    if "ui_text_scale" in raw:
        base["ui_text_scale"] = coerce_ui_text_scale(raw["ui_text_scale"])
    if "theme" in raw:
        base["theme"] = _coerce_theme_id(raw["theme"])
    if "last_tab" in raw:
        base["last_tab"] = _coerce_last_tab(raw["last_tab"])
    if "saved_views" in raw:
        base["saved_views"] = _coerce_saved_views(raw["saved_views"])
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


def get_ui_text_scale(settings: dict[str, Any]) -> float:
    """Return the persisted interface text scale multiplier."""
    return coerce_ui_text_scale(settings.get("ui_text_scale"))


def set_ui_text_scale(settings: dict[str, Any], scale: float) -> None:
    """Persist a clamped text scale for the next ``save_ui_settings``."""
    settings["ui_text_scale"] = coerce_ui_text_scale(scale)


def get_display_timezone(settings: dict[str, Any]) -> str:
    """Timezone key for activity timestamps: ``local`` or an IANA name."""
    return _coerce_display_timezone(settings.get("display_timezone"))


def set_display_timezone(settings: dict[str, Any], tz_key: str) -> None:
    """Persist a validated display timezone for the next ``save_ui_settings``."""
    settings["display_timezone"] = _coerce_display_timezone(tz_key)


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


def get_last_tab(settings: dict[str, Any]) -> str:
    """Return the last-selected tab id, falling back to the default."""
    return _coerce_last_tab(settings.get("last_tab"))


def set_last_tab(settings: dict[str, Any], tab_id: str) -> None:
    """Persist ``tab_id`` as the tab to reopen on next launch."""
    settings["last_tab"] = _coerce_last_tab(tab_id)


def get_saved_views(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a shallow copy of the saved-view list.

    Callers mutate the returned list freely; persistence happens via
    :func:`set_saved_views`, :func:`add_saved_view`, etc. Each returned
    entry is itself a shallow copy so edits to ``filters`` on a copy
    cannot silently alter the settings dict in memory.
    """
    raw = settings.get("saved_views")
    coerced = _coerce_saved_views(raw) if raw is not None else []
    return [
        {"name": v["name"], "filters": dict(v["filters"]), "version": v["version"]}
        for v in coerced
    ]


def set_saved_views(
    settings: dict[str, Any], views: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Replace the saved-view list wholesale after coercion.

    Returns the cleaned list that was actually stored so the UI can
    stay in sync (e.g. if two views collided on name).
    """
    cleaned = _coerce_saved_views(views)
    settings["saved_views"] = cleaned
    return cleaned


def _find_saved_view_index(
    views: list[dict[str, Any]], name: str
) -> int:
    key = name.strip().casefold()
    for i, v in enumerate(views):
        if v["name"].casefold() == key:
            return i
    return -1


def add_saved_view(
    settings: dict[str, Any],
    name: str,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Append a new saved view with the given name and filters.

    If ``name`` collides with an existing view (case-insensitive) the
    existing entry's filters are replaced so "Save as view…" acts as
    an in-place update when the user picks a used name - matching the
    affordance users expect from similar tools. Returns the stored
    view, or ``None`` if the name was empty / otherwise invalid.
    """
    coerced = _coerce_saved_view(
        {
            "name": name,
            "filters": filters,
            "version": SAVED_VIEW_SCHEMA_VERSION,
        }
    )
    if coerced is None:
        return None
    views = _coerce_saved_views(settings.get("saved_views"))
    idx = _find_saved_view_index(views, coerced["name"])
    if idx >= 0:
        # Preserve position and the existing display casing on
        # overwrite so an accidental "inbox" entry doesn't visually
        # rename a carefully-cased "Inbox" saved view. Callers who
        # want to change the casing use ``rename_saved_view``.
        views[idx] = {
            "name": views[idx]["name"],
            "filters": coerced["filters"],
            "version": coerced["version"],
        }
        stored = views[idx]
    else:
        views.append(coerced)
        stored = coerced
    settings["saved_views"] = views
    return stored


def remove_saved_view(settings: dict[str, Any], name: str) -> bool:
    """Remove a saved view by name. Returns ``True`` if a view was removed."""
    views = _coerce_saved_views(settings.get("saved_views"))
    idx = _find_saved_view_index(views, name)
    if idx < 0:
        return False
    del views[idx]
    settings["saved_views"] = views
    return True


def rename_saved_view(
    settings: dict[str, Any], old_name: str, new_name: str
) -> bool:
    """Rename a saved view. Returns ``True`` on success.

    Fails (returns ``False``) when the target name is empty, invalid,
    or already taken by a different view. A rename to the same name is
    treated as a success no-op.
    """
    new_coerced = _coerce_saved_view(
        {
            "name": new_name,
            "filters": {},
            "version": SAVED_VIEW_SCHEMA_VERSION,
        }
    )
    if new_coerced is None:
        return False
    views = _coerce_saved_views(settings.get("saved_views"))
    idx = _find_saved_view_index(views, old_name)
    if idx < 0:
        return False
    # Same-name rename (differs only in casing) still updates the
    # stored casing so the user-visible label reflects the new choice.
    target_key = new_coerced["name"].casefold()
    for i, v in enumerate(views):
        if i != idx and v["name"].casefold() == target_key:
            return False
    views[idx] = {
        "name": new_coerced["name"],
        "filters": views[idx]["filters"],
        "version": views[idx]["version"],
    }
    settings["saved_views"] = views
    return True


def move_saved_view(settings: dict[str, Any], name: str, delta: int) -> bool:
    """Shift a saved view up (``delta < 0``) or down (``delta > 0``).

    Returns ``True`` when the position actually changed. Edges are
    clamped - moving the first item up or the last item down is a no-op
    that reports ``False`` so the UI can disable its buttons.
    """
    if delta == 0:
        return False
    views = _coerce_saved_views(settings.get("saved_views"))
    idx = _find_saved_view_index(views, name)
    if idx < 0:
        return False
    target = max(0, min(len(views) - 1, idx + delta))
    if target == idx:
        return False
    item = views.pop(idx)
    views.insert(target, item)
    settings["saved_views"] = views
    return True


def save_ui_settings(data: dict[str, Any]) -> None:
    path = get_app_data_dir() / SETTINGS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
