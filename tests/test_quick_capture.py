"""Tests for plan 05 quick-capture settings (no global hotkey binding)."""

from __future__ import annotations

from tasktracker.ui import settings_store as ss
from tasktracker.ui.settings_store import DEFAULT_QUICK_CAPTURE, default_ui_settings


def test_default_ui_settings_includes_quick_capture() -> None:
    s = default_ui_settings()
    assert s["quick_capture"] == dict(DEFAULT_QUICK_CAPTURE)


def test_coerce_quick_capture_keeps_valid_hotkey_and_flags() -> None:
    out = ss._coerce_quick_capture(
        {
            "hotkey": " Ctrl+Alt+Q ",
            "keep_running_in_tray": True,
            "tray_click_opens_capture": False,
            "default_impact": 3,
            "default_urgency": 1,
            "default_area_id": 42,
            "default_person_id": None,
        }
    )
    assert out["hotkey"] == "Ctrl+Alt+Q"
    assert out["keep_running_in_tray"] is True
    assert out["tray_click_opens_capture"] is False
    assert out["default_impact"] == 3
    assert out["default_urgency"] == 1
    assert out["default_area_id"] == 42
    assert out["default_person_id"] is None


def test_coerce_quick_capture_ignores_bad_numeric_and_empty_hotkey() -> None:
    base = dict(DEFAULT_QUICK_CAPTURE)
    out = ss._coerce_quick_capture(
        {
            "hotkey": "   ",
            "default_impact": 0,
            "default_urgency": 9,
            "default_area_id": "nope",
        }
    )
    assert out["hotkey"] == base["hotkey"]
    assert out["default_impact"] == base["default_impact"]
    assert out["default_urgency"] == base["default_urgency"]
    assert out["default_area_id"] == base["default_area_id"]
