"""Unit tests for the user-configurable date format helpers.

Kept deliberately Qt-free so the format math (token conversion,
ISO-string rewriting, preset round-tripping) stays runnable in any
environment the service-layer tests run in.
"""

from __future__ import annotations

import datetime as dt

from tasktracker.ui.date_format import (
    DATE_FORMAT_PRESETS,
    DISPLAY_TIMEZONE_LOCAL,
    format_activity_timestamp,
    format_date,
    iso_string_to_display,
    qt_to_py_format,
    reformat_iso_dates_in_text,
    resolve_display_tz,
)
from tasktracker.ui.settings_store import (
    DEFAULT_DATE_FORMAT,
    DEFAULT_DISPLAY_TIMEZONE,
    _coerce_date_format,
    _coerce_display_timezone,
    default_ui_settings,
    get_date_format_qt,
    get_display_timezone,
    set_date_format_qt,
    set_display_timezone,
)


SAMPLE = dt.date(2026, 4, 17)


def test_default_format_matches_settings_default() -> None:
    assert DEFAULT_DATE_FORMAT == "yyyy-MM-dd"
    assert format_date(SAMPLE) == "2026-04-17"


def test_qt_to_py_translates_common_tokens() -> None:
    assert qt_to_py_format("yyyy-MM-dd") == "%Y-%m-%d"
    assert qt_to_py_format("MM/dd/yyyy") == "%m/%d/%Y"
    assert qt_to_py_format("dd MMM yyyy") == "%d %b %Y"
    assert qt_to_py_format("MMMM d, yyyy") == "%B %d, %Y"


def test_qt_to_py_preserves_literals_and_unknown_tokens() -> None:
    assert qt_to_py_format("yyyy 'at' MM-dd") == "%Y 'at' %m-%d"


def test_format_date_renders_each_preset_without_raising() -> None:
    expected = {
        "yyyy-MM-dd": "2026-04-17",
        "MM/dd/yyyy": "04/17/2026",
        "dd/MM/yyyy": "17/04/2026",
        "d MMM yyyy": "17 Apr 2026",
        "MMM d, yyyy": "Apr 17, 2026",
        "dd MMMM yyyy": "17 April 2026",
    }
    for preset in DATE_FORMAT_PRESETS:
        assert format_date(SAMPLE, preset.qt_format) == expected[preset.qt_format]


def test_format_date_handles_none() -> None:
    assert format_date(None) == ""
    assert format_date(None, "MM/dd/yyyy") == ""


def test_reformat_iso_dates_in_text_rewrites_all_occurrences() -> None:
    text = "Window 2026-04-01 -> 2026-04-30: 12 open"
    assert (
        reformat_iso_dates_in_text(text, "MM/dd/yyyy")
        == "Window 04/01/2026 -> 04/30/2026: 12 open"
    )


def test_reformat_iso_dates_in_text_default_is_noop() -> None:
    text = "As of 2026-04-17: 5 closed"
    assert reformat_iso_dates_in_text(text) == text
    assert reformat_iso_dates_in_text(text, "yyyy-MM-dd") == text


def test_reformat_iso_dates_ignores_non_dates() -> None:
    text = "Ticket 2026-99-99 is not a date"
    assert reformat_iso_dates_in_text(text, "MM/dd/yyyy") == text


def test_iso_string_to_display_passes_through_non_dates() -> None:
    assert iso_string_to_display("no due", "MM/dd/yyyy") == "no due"
    assert iso_string_to_display("", "MM/dd/yyyy") == ""
    assert iso_string_to_display(None, "MM/dd/yyyy") == ""


def test_iso_string_to_display_rewrites_iso_values() -> None:
    assert iso_string_to_display("2026-04-17", "dd/MM/yyyy") == "17/04/2026"


# ----- settings_store round-tripping ---------------------------------------


def test_default_settings_include_date_format() -> None:
    s = default_ui_settings()
    assert s["date_format"] == DEFAULT_DATE_FORMAT


def test_set_and_get_date_format_round_trip() -> None:
    s = default_ui_settings()
    set_date_format_qt(s, "MM/dd/yyyy")
    assert get_date_format_qt(s) == "MM/dd/yyyy"


def test_coerce_date_format_guards_against_garbage() -> None:
    # Non-string types fall back to ISO.
    assert _coerce_date_format(None) == "yyyy-MM-dd"
    assert _coerce_date_format(42) == "yyyy-MM-dd"
    # Empty / whitespace-only strings fall back.
    assert _coerce_date_format("") == "yyyy-MM-dd"
    assert _coerce_date_format("   ") == "yyyy-MM-dd"
    # Overly long strings (likely corruption) fall back.
    assert _coerce_date_format("y" * 500) == "yyyy-MM-dd"
    # Valid short custom strings pass through (trimmed).
    assert _coerce_date_format(" d MMM yyyy ") == "d MMM yyyy"


def test_get_date_format_qt_handles_missing_key() -> None:
    # Simulates a settings dict persisted before the feature landed.
    legacy = {"task_panel_section_order": [], "shortcuts": {}}
    assert get_date_format_qt(legacy) == DEFAULT_DATE_FORMAT


def test_default_settings_include_display_timezone() -> None:
    s = default_ui_settings()
    assert s["display_timezone"] == DEFAULT_DISPLAY_TIMEZONE
    assert get_display_timezone(s) == DEFAULT_DISPLAY_TIMEZONE


def test_coerce_display_timezone_accepts_local_and_utc() -> None:
    assert _coerce_display_timezone("local") == "local"
    assert _coerce_display_timezone("UTC") == "UTC"
    assert _coerce_display_timezone("  America/New_York  ") == "America/New_York"


def test_coerce_display_timezone_rejects_garbage() -> None:
    assert _coerce_display_timezone(None) == DEFAULT_DISPLAY_TIMEZONE
    assert _coerce_display_timezone("Not/A/Zone") == DEFAULT_DISPLAY_TIMEZONE
    assert _coerce_display_timezone("x" * 500) == DEFAULT_DISPLAY_TIMEZONE


def test_set_display_timezone_round_trip() -> None:
    s = default_ui_settings()
    set_display_timezone(s, "Europe/Paris")
    assert get_display_timezone(s) == "Europe/Paris"


def test_format_activity_timestamp_utc_fixed_instant() -> None:
    when = dt.datetime(2026, 4, 22, 15, 30, tzinfo=dt.UTC)
    out = format_activity_timestamp(when, "America/New_York")
    assert "2026-04-22" in out
    assert "11:30" in out


def test_format_activity_timestamp_naive_assumed_utc() -> None:
    when = dt.datetime(2026, 1, 1, 0, 0)
    out = format_activity_timestamp(when, "UTC")
    assert out.startswith("2026-01-01 00:00")


def test_resolve_display_tz_local_is_tzinfo() -> None:
    tz = resolve_display_tz(DISPLAY_TIMEZONE_LOCAL)
    assert isinstance(tz, dt.tzinfo)
