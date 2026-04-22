"""Tests for the color theme registry and settings integration.

These tests cover the parts that matter for correctness without
needing a live ``QApplication``:

* The registry exposes every expected theme in a stable order.
* ``get_theme`` falls back to the default (Light) on unknown ids.
* Settings coerce unknown / non-string theme ids to the default.
* Theme ids round-trip through ``set_theme_id`` / ``get_theme_id``.
* Each theme provides a full palette spec so widgets never fall back
  to an unstyled color mid-theme.
* The legacy ``"system"`` theme id (from the earlier platform-style
  escape hatch) silently migrates to Light.

``apply_theme`` is a thin wrapper around Qt primitives and is
exercised indirectly in the manual QA flow - adding a full Qt
application spin-up here slows the test suite without adding
meaningful coverage.
"""

from __future__ import annotations

import pytest

from tasktracker.ui.settings_store import (
    default_ui_settings,
    get_theme_id,
    set_theme_id,
)
from tasktracker.ui.themes import (
    DEFAULT_THEME_ID,
    THEMES,
    THEMES_BY_ID,
    Theme,
    calendar_event_colors,
    get_theme,
    list_themes,
)


EXPECTED_THEME_IDS = ("light", "dark", "light_gray", "sepia")

# Every palette role we expect each theme to cover so widgets never
# fall back to an unstyled color mid-theme.
REQUIRED_ROLES = {
    "Window",
    "WindowText",
    "Base",
    "AlternateBase",
    "Text",
    "Button",
    "ButtonText",
    "Highlight",
    "HighlightedText",
    "ToolTipBase",
    "ToolTipText",
}


def test_theme_registry_has_expected_ids_in_order() -> None:
    assert tuple(t.id for t in THEMES) == EXPECTED_THEME_IDS
    assert tuple(t.id for t in list_themes()) == EXPECTED_THEME_IDS


def test_themes_by_id_lookup_is_consistent() -> None:
    for theme in THEMES:
        assert THEMES_BY_ID[theme.id] is theme


def test_default_theme_is_light() -> None:
    assert DEFAULT_THEME_ID == "light"
    # The default must ship a real palette spec - the old "system"
    # escape hatch that left palette_spec None has been removed.
    assert THEMES_BY_ID[DEFAULT_THEME_ID].palette_spec is not None


@pytest.mark.parametrize("theme_id", EXPECTED_THEME_IDS)
def test_themes_cover_required_roles(theme_id: str) -> None:
    spec = THEMES_BY_ID[theme_id].palette_spec
    assert spec is not None, f"{theme_id} should have an explicit palette"
    missing = REQUIRED_ROLES - set(spec.keys())
    assert not missing, f"{theme_id} is missing roles: {sorted(missing)}"
    for role, value in spec.items():
        assert isinstance(value, str) and value.startswith("#"), (
            f"{theme_id}.{role} should be a #hex color, got {value!r}"
        )
        assert len(value) in (4, 7), (
            f"{theme_id}.{role}={value!r} is not a valid #rgb/#rrggbb"
        )


def test_get_theme_falls_back_to_default_for_unknown_id() -> None:
    resolved = get_theme("not-a-real-theme")
    assert isinstance(resolved, Theme)
    assert resolved.id == DEFAULT_THEME_ID


def test_get_theme_returns_default_when_none() -> None:
    assert get_theme(None).id == DEFAULT_THEME_ID


def test_legacy_system_theme_id_migrates_to_light() -> None:
    """Users upgrading from the platform-style era had ``"system"`` on
    disk. The unknown-id coercion path should quietly resolve that to
    Light without requiring an explicit migration step."""
    settings = default_ui_settings()
    settings["theme"] = "system"
    assert get_theme_id(settings) == "light"
    assert get_theme("system").id == "light"


def test_default_ui_settings_includes_theme_key() -> None:
    settings = default_ui_settings()
    assert settings["theme"] == DEFAULT_THEME_ID


def test_set_and_get_theme_id_roundtrip() -> None:
    settings = default_ui_settings()
    set_theme_id(settings, "dark")
    assert get_theme_id(settings) == "dark"
    set_theme_id(settings, "sepia")
    assert get_theme_id(settings) == "sepia"


def test_set_theme_id_rejects_unknown_values() -> None:
    settings = default_ui_settings()
    set_theme_id(settings, "dark")
    set_theme_id(settings, "bogus")
    # Unknown ids silently reset to the default rather than persisting
    # a bad value that would break the radio group on next launch.
    assert get_theme_id(settings) == DEFAULT_THEME_ID


def test_get_theme_id_coerces_non_string_values() -> None:
    settings = default_ui_settings()
    settings["theme"] = 42  # corrupted on disk
    assert get_theme_id(settings) == DEFAULT_THEME_ID


def _is_hex_color(value: str) -> bool:
    return isinstance(value, str) and value.startswith("#") and len(value) in (4, 7)


@pytest.mark.parametrize("theme_id", EXPECTED_THEME_IDS)
def test_themes_declare_calendar_event_colors(theme_id: str) -> None:
    """Every built-in theme must declare calendar-day badge colors.

    The Dashboard and Calendar tabs shade flagged day cells with these
    colors; a theme that forgets them would fall back to hard-coded
    defaults that don't match its palette (dark theme in particular
    became illegible before these extras were introduced).
    """
    bg, fg = calendar_event_colors(theme_id)
    assert _is_hex_color(bg), f"{theme_id}: bg {bg!r} is not a #hex color"
    assert _is_hex_color(fg), f"{theme_id}: fg {fg!r} is not a #hex color"
    # Sanity check: the bg and fg should differ so there's visible
    # contrast (we don't test luminance here - the palette author owns
    # that judgement - just that they aren't literally the same color).
    assert bg.lower() != fg.lower(), (
        f"{theme_id} calendar colors collapse to a single color: {bg}"
    )


def test_calendar_event_colors_fall_back_for_unknown_theme() -> None:
    bg, fg = calendar_event_colors("not-a-theme")
    assert _is_hex_color(bg) and _is_hex_color(fg)
    # Unknown id routes through ``get_theme`` which returns the default,
    # so the returned colors must match the default theme's extras.
    default_bg, default_fg = calendar_event_colors(DEFAULT_THEME_ID)
    assert (bg, fg) == (default_bg, default_fg)
