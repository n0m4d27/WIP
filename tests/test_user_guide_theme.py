"""Tests for theme-aware user guide HTML styling."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from tasktracker.ui.user_guide_dialog import (
    _CODE_RULE_DARK,
    _CODE_RULE_LIGHT,
    _DARK_GUIDE_STYLE_OVERRIDE,
    _guide_html_with_theme,
    _palette_suggests_dark_chrome,
    _rich_text_default_stylesheet,
)


def test_guide_html_light_unchanged() -> None:
    html = "<html><head><style>code { x: 1; }</style></head><body><p>Hi</p></body></html>"
    assert _guide_html_with_theme(html, is_dark=False) == html


def test_guide_html_dark_patches_bundled_code_in_first_style() -> None:
    html = (
        "<html><head><style>\n"
        "body { font-family: sans-serif; }\n"
        "h2 { font-size: 1.05em; margin-top: 1.2em; border-bottom: 1px solid #ccc; }\n"
        f"{_CODE_RULE_LIGHT}\n"
        "</style></head><body></body></html>"
    )
    out = _guide_html_with_theme(html, is_dark=True)
    assert _CODE_RULE_DARK in out
    assert _CODE_RULE_LIGHT not in out
    assert "border-bottom: 1px solid #555;" in out
    assert "border-bottom: 1px solid #ccc;" not in out
    assert _DARK_GUIDE_STYLE_OVERRIDE not in out


def test_guide_html_dark_short_code_rule_in_place() -> None:
    html = "<html><head><style>code { background: #f0f0f0; }</style></head><body></body></html>"
    out = _guide_html_with_theme(html, is_dark=True)
    assert _CODE_RULE_DARK in out
    assert "background: #f0f0f0" not in out
    assert _DARK_GUIDE_STYLE_OVERRIDE not in out


def test_guide_html_dark_unknown_code_appends_override() -> None:
    html = "<html><head><style>code { x: 1; }</style></head><body></body></html>"
    out = _guide_html_with_theme(html, is_dark=True)
    assert _DARK_GUIDE_STYLE_OVERRIDE in out
    assert "#2d2d2d" in out


def test_guide_html_dark_without_style_prefixes_head() -> None:
    html = "<p>missing</p>"
    out = _guide_html_with_theme(html, is_dark=True)
    assert out.startswith("<head>")
    assert "#2d2d2d" in out


def test_rich_text_stylesheet_dark_and_light() -> None:
    d = _rich_text_default_stylesheet(is_dark=True)
    assert "#2d2d2d" in d
    assert "#e8e8e8" in d
    l = _rich_text_default_stylesheet(is_dark=False)
    assert "#f0f0f0" in l
    assert "#2d2d2d" not in l


def test_palette_dark_chrome_heuristic() -> None:
    dark = QPalette()
    dark.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor("#1f1f1f"))
    dark.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
    assert _palette_suggests_dark_chrome(dark)

    light = QPalette()
    light.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor("#ececec"))
    light.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#1b1b1b"))
    assert not _palette_suggests_dark_chrome(light)
