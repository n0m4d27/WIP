"""Tests for the plan 01 additions to :mod:`tasktracker.ui.settings_store`.

These cover the saved-views CRUD helpers and the ``last_tab`` coercion.
The helpers operate on an in-memory dict rather than hitting disk, so
no fixtures are required beyond a fresh :func:`default_ui_settings`.
"""

from __future__ import annotations

import pytest

from tasktracker.ui.settings_store import (
    DEFAULT_TAB_ID,
    KNOWN_TAB_IDS,
    SAVED_VIEW_SCHEMA_VERSION,
    add_saved_view,
    default_ui_settings,
    get_last_tab,
    get_saved_views,
    move_saved_view,
    remove_saved_view,
    rename_saved_view,
    set_last_tab,
    set_saved_views,
)


def test_default_settings_include_plan_01_keys() -> None:
    settings = default_ui_settings()
    assert settings["last_tab"] == DEFAULT_TAB_ID
    assert settings["saved_views"] == []


@pytest.mark.parametrize("tab_id", KNOWN_TAB_IDS)
def test_last_tab_round_trip(tab_id: str) -> None:
    settings = default_ui_settings()
    set_last_tab(settings, tab_id)
    assert get_last_tab(settings) == tab_id


def test_last_tab_unknown_coerces_to_default() -> None:
    settings = default_ui_settings()
    set_last_tab(settings, "made-up-tab")
    assert get_last_tab(settings) == DEFAULT_TAB_ID


def test_last_tab_wrong_type_coerces_to_default() -> None:
    settings = default_ui_settings()
    settings["last_tab"] = 42
    assert get_last_tab(settings) == DEFAULT_TAB_ID


def test_add_saved_view_appends_and_tags_version() -> None:
    settings = default_ui_settings()
    stored = add_saved_view(
        settings,
        "My WFM open",
        {"search_text": "wfm", "search_fields": ["title"], "hide_closed": True},
    )
    assert stored is not None
    assert stored["name"] == "My WFM open"
    assert stored["version"] == SAVED_VIEW_SCHEMA_VERSION
    views = get_saved_views(settings)
    assert [v["name"] for v in views] == ["My WFM open"]
    assert views[0]["filters"]["search_text"] == "wfm"


def test_add_saved_view_trims_and_rejects_empty() -> None:
    settings = default_ui_settings()
    assert add_saved_view(settings, "   ", {}) is None
    # Whitespace-only name should not corrupt the list.
    assert get_saved_views(settings) == []

    stored = add_saved_view(settings, "  Leading spaces  ", {})
    assert stored is not None
    assert stored["name"] == "Leading spaces"


def test_add_saved_view_replaces_on_case_insensitive_collision() -> None:
    settings = default_ui_settings()
    add_saved_view(settings, "Inbox", {"search_text": "v1"})
    add_saved_view(settings, "inbox", {"search_text": "v2"})
    views = get_saved_views(settings)
    assert len(views) == 1
    # Replacement keeps the original casing and position.
    assert views[0]["name"] == "Inbox"
    assert views[0]["filters"]["search_text"] == "v2"


def test_remove_saved_view_is_case_insensitive() -> None:
    settings = default_ui_settings()
    add_saved_view(settings, "Headcount P1/P2", {})
    add_saved_view(settings, "Waiting on HR", {})
    assert remove_saved_view(settings, "HEADCOUNT P1/P2") is True
    remaining = [v["name"] for v in get_saved_views(settings)]
    assert remaining == ["Waiting on HR"]


def test_remove_saved_view_missing_returns_false() -> None:
    settings = default_ui_settings()
    assert remove_saved_view(settings, "does-not-exist") is False


def test_rename_saved_view_succeeds_and_preserves_filters() -> None:
    settings = default_ui_settings()
    add_saved_view(settings, "Old", {"search_text": "abc"})
    assert rename_saved_view(settings, "Old", "New") is True
    views = get_saved_views(settings)
    assert views[0]["name"] == "New"
    assert views[0]["filters"]["search_text"] == "abc"


def test_rename_saved_view_rejects_duplicate_name() -> None:
    settings = default_ui_settings()
    add_saved_view(settings, "A", {})
    add_saved_view(settings, "B", {})
    assert rename_saved_view(settings, "A", "B") is False
    names = [v["name"] for v in get_saved_views(settings)]
    assert names == ["A", "B"]


def test_rename_saved_view_case_only_rename_updates_casing() -> None:
    settings = default_ui_settings()
    add_saved_view(settings, "inbox", {})
    assert rename_saved_view(settings, "inbox", "Inbox") is True
    assert get_saved_views(settings)[0]["name"] == "Inbox"


def test_move_saved_view_shifts_position() -> None:
    settings = default_ui_settings()
    for name in ("A", "B", "C", "D"):
        add_saved_view(settings, name, {})
    assert move_saved_view(settings, "C", -1) is True
    assert [v["name"] for v in get_saved_views(settings)] == ["A", "C", "B", "D"]
    assert move_saved_view(settings, "A", -1) is False  # already at top
    assert move_saved_view(settings, "D", 1) is False  # already at bottom
    assert move_saved_view(settings, "C", 10) is True  # clamped to end
    assert [v["name"] for v in get_saved_views(settings)] == ["A", "B", "D", "C"]


def test_set_saved_views_drops_bad_entries() -> None:
    settings = default_ui_settings()
    cleaned = set_saved_views(
        settings,
        [
            {"name": "Good", "filters": {"search_text": "x"}},
            {"name": "", "filters": {}},  # empty name - dropped
            {"filters": {}},  # missing name - dropped
            {"name": "Good", "filters": {"search_text": "dup"}},  # dup - dropped
            "not-a-dict",  # wrong type - dropped
            {"name": "Also Good", "filters": {}},
        ],
    )
    assert [v["name"] for v in cleaned] == ["Good", "Also Good"]
    assert get_saved_views(settings)[0]["filters"]["search_text"] == "x"


def test_get_saved_views_returns_deep_copies() -> None:
    settings = default_ui_settings()
    add_saved_view(settings, "Deep", {"search_text": "start"})
    views = get_saved_views(settings)
    views[0]["filters"]["search_text"] = "mutated"
    reread = get_saved_views(settings)
    assert reread[0]["filters"]["search_text"] == "start"
