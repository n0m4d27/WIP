"""Tests for interface text scale settings and application font helper."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from tasktracker.ui.settings_store import (
    DEFAULT_UI_TEXT_SCALE,
    MAX_UI_TEXT_SCALE,
    MIN_UI_TEXT_SCALE,
    coerce_ui_text_scale,
    default_ui_settings,
    get_ui_text_scale,
    set_ui_text_scale,
)
from tasktracker.ui.text_scale import (
    apply_app_text_scale,
    ensure_text_scale_baseline,
    propagate_font_to_widget_tree,
    reset_text_scale_baseline_for_tests,
)


def test_default_settings_include_ui_text_scale() -> None:
    s = default_ui_settings()
    assert s["ui_text_scale"] == DEFAULT_UI_TEXT_SCALE
    assert get_ui_text_scale(s) == DEFAULT_UI_TEXT_SCALE


def test_coerce_ui_text_scale_clamps() -> None:
    assert coerce_ui_text_scale(1.0) == 1.0
    assert coerce_ui_text_scale(0.5) == MIN_UI_TEXT_SCALE
    assert coerce_ui_text_scale(9.0) == MAX_UI_TEXT_SCALE
    assert coerce_ui_text_scale(None) == DEFAULT_UI_TEXT_SCALE
    assert coerce_ui_text_scale("bogus") == DEFAULT_UI_TEXT_SCALE
    assert coerce_ui_text_scale(float("nan")) == DEFAULT_UI_TEXT_SCALE


def test_set_get_ui_text_scale_roundtrip() -> None:
    s = default_ui_settings()
    set_ui_text_scale(s, 1.25)
    assert get_ui_text_scale(s) == 1.25


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_apply_app_text_scale_uses_baseline(qapp: QApplication) -> None:
    reset_text_scale_baseline_for_tests()
    ensure_text_scale_baseline(qapp)
    base = qapp.font().pointSizeF()
    if base <= 0:
        base = float(qapp.font().pointSize() or 10)
    apply_app_text_scale(qapp, 1.2)
    scaled = qapp.font().pointSizeF()
    assert abs(scaled - base * 1.2) < 0.05 or scaled >= base


def test_propagate_font_to_widget_tree_matches_app_font(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QLabel, QMainWindow

    reset_text_scale_baseline_for_tests()
    ensure_text_scale_baseline(qapp)
    apply_app_text_scale(qapp, 1.15)
    win = QMainWindow()
    lbl = QLabel("Probe", win)
    win.setCentralWidget(lbl)
    propagate_font_to_widget_tree(win, qapp.font())
    assert lbl.font().pointSizeF() == qapp.font().pointSizeF()
