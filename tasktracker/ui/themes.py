"""Application-wide color themes.

Four curated palettes ship out of the box:

* **Light** - soft off-white chrome with near-white input fields.
  First-launch default; a neutral light palette that avoids the glare
  of pure ``#ffffff`` while staying clearly lighter than the gray
  reading theme.
* **Dark** - high-contrast dark palette for low-light use.
* **Light gray (reading)** - muted gray page background with darker ink
  text; reduces glare for long-form reading sessions on a bright
  monitor without the eye strain of a pure-dark theme.
* **Sepia (reading)** - warm sienna / parchment palette that mimics
  the paper-and-ink look many readers prefer late in the day.

Every theme is applied via Qt's ``Fusion`` style. Fusion is fully
``QPalette``-driven and cross-platform, so every widget (buttons,
combos, line edits, date pickers, plain-text / text edits, check
boxes, scrollbars) actually picks up the theme colors. The native
platform styles (``windowsvista`` on Windows, ``macOS`` on macOS)
draw most controls through OS APIs and ignore ``QPalette`` for many
roles, which is why we don't use them for theming.

This module is intentionally Qt-thin: only ``QPalette`` / ``QColor``
from ``PySide6`` are imported at module top-level, and applying a
theme takes the ``QApplication`` as an explicit argument so the
call sites stay obvious. Unit tests can import this module and
inspect registry metadata without touching ``QApplication``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QColor, QPalette

# Qt style name applied for every theme. Fusion's palette-driven paint
# routines are the whole reason our colors actually cover the UI.
_FUSION_STYLE: str = "Fusion"


@dataclass(frozen=True)
class Theme:
    """One entry in the theme registry.

    ``id`` is persisted in ``ui_settings.json`` and must stay stable
    across releases. ``label`` is the human-facing menu text.
    ``description`` is a one-line tooltip. ``is_dark`` tags palettes
    that look better with a lighter link color - Qt doesn't infer that
    for us, so we thread the hint through explicitly. ``palette_spec``
    is a mapping from ``QPalette.ColorRole`` string name to a hex
    color; every built-in theme ships a full spec. ``disabled_spec``
    is an optional override for the ``QPalette.ColorGroup.Disabled``
    group - Fusion's auto-derivation works for light palettes but is
    too low-contrast on the dark theme, so we tighten it there.
    ``stylesheet`` is a small QSS fragment appended to the application
    stylesheet to patch widgets Qt doesn't route through the palette
    (tooltip frames, QMenu separators).
    """

    id: str
    label: str
    description: str
    is_dark: bool = False
    # Optional in type only so a future theme can fall back to Fusion's
    # defaults if it needs to; every built-in theme supplies a full spec.
    palette_spec: dict[str, str] | None = None
    disabled_spec: dict[str, str] = field(default_factory=dict)
    stylesheet: str = ""
    extras: dict[str, str] = field(default_factory=dict)


# Palette role keys we assign across every theme. Keeping the roles in
# one place makes it easy to add new themes without forgetting a slot.
# ``Mid`` / ``Dark`` / ``Light`` / ``Shadow`` / ``Midlight`` are used by
# Fusion to render frame bevels, scroll-track edges, and focus-ring
# shading; omitting them leaves Fusion to derive values from ``Window``
# which works for light palettes but produces washed-out borders on the
# dark theme. Setting them explicitly gives every theme a consistent
# frame look.
_ROLES: tuple[str, ...] = (
    "Window",
    "WindowText",
    "Base",
    "AlternateBase",
    "Text",
    "Button",
    "ButtonText",
    "BrightText",
    "Highlight",
    "HighlightedText",
    "ToolTipBase",
    "ToolTipText",
    "PlaceholderText",
    "Link",
    "LinkVisited",
    "Mid",
    "Midlight",
    "Dark",
    "Light",
    "Shadow",
)

# Roles whose disabled-state variant we set explicitly. Fusion auto-
# derives disabled colors by blending toward ``Window`` which looks
# fine on light palettes but is hard to read on the dark theme; an
# explicit disabled color per theme fixes that without fighting the
# style.
_DISABLED_ROLES: tuple[str, ...] = (
    "Text",
    "WindowText",
    "ButtonText",
    "HighlightedText",
)


# ---------------------------------------------------------------------------
# Stylesheet fragments
# ---------------------------------------------------------------------------

# Small, targeted QSS fragments. Fusion + palette handles the bulk of
# widget chrome (buttons, combos, line edits, date pickers, text areas,
# checkboxes, tabs, scrollbars), so these only patch things Qt does NOT
# route through ``QPalette``: tooltip frames and QMenu separators.
# Keeping the stylesheets tiny avoids fighting Fusion's paint routines
# (heavy QSS tends to look worse than palette tweaks) and makes future
# theme additions cheap.
_LIGHT_STYLESHEET = """
QToolTip {
    color: #1b1b1b;
    background-color: #fafafa;
    border: 1px solid #c4c4c4;
}
"""

_DARK_STYLESHEET = """
QToolTip {
    color: #e0e0e0;
    background-color: #2b2b2b;
    border: 1px solid #555555;
}
QMenu::separator {
    background: #3a3a3a;
    height: 1px;
    margin: 4px 8px;
}
"""

_LIGHT_GRAY_STYLESHEET = """
QToolTip {
    color: #1b1b1b;
    background-color: #e8e8e8;
    border: 1px solid #bdbdbd;
}
"""

_SEPIA_STYLESHEET = """
QToolTip {
    color: #3b2c1a;
    background-color: #efe4cf;
    border: 1px solid #b99a70;
}
"""


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------


# "Soft light" - deliberately sized between pure white and the gray
# reading theme. Window is softly off-white so big chrome panels don't
# glare; Base stays near-white so input fields pop against the window
# chrome without being dazzling. Highlight is a cool muted blue so
# selections read as neutral (the sepia theme owns warm highlights).
_LIGHT = Theme(
    id="light",
    label="Light",
    description="Soft off-white chrome with near-white input fields - reduced glare.",
    is_dark=False,
    palette_spec={
        "Window": "#ececec",
        "WindowText": "#1b1b1b",
        "Base": "#fbfbfb",
        "AlternateBase": "#f2f2f2",
        "Text": "#1b1b1b",
        "Button": "#e4e4e4",
        "ButtonText": "#1b1b1b",
        "BrightText": "#000000",
        "Highlight": "#2a6db3",
        "HighlightedText": "#ffffff",
        "ToolTipBase": "#fafafa",
        "ToolTipText": "#1b1b1b",
        "PlaceholderText": "#7a7a7a",
        "Link": "#1a5fb4",
        "LinkVisited": "#6a3db0",
        # Frame / bevel shading: slightly darker than the window so
        # groupbox edges and scrollbar tracks stay distinguishable
        # without being busy.
        "Mid": "#c4c4c4",
        "Midlight": "#e0e0e0",
        "Dark": "#9e9e9e",
        "Light": "#f8f8f8",
        "Shadow": "#757575",
    },
    disabled_spec={
        "Text": "#8e8e8e",
        "WindowText": "#8e8e8e",
        "ButtonText": "#8e8e8e",
        "HighlightedText": "#5a5a5a",
    },
    stylesheet=_LIGHT_STYLESHEET,
)

_DARK = Theme(
    id="dark",
    label="Dark",
    description="Dark background with light text, tuned for low-light use.",
    is_dark=True,
    palette_spec={
        "Window": "#1f1f1f",
        "WindowText": "#e0e0e0",
        "Base": "#1b1b1b",
        "AlternateBase": "#262626",
        "Text": "#e0e0e0",
        "Button": "#2b2b2b",
        "ButtonText": "#e0e0e0",
        "BrightText": "#ffffff",
        "Highlight": "#264f78",
        "HighlightedText": "#ffffff",
        "ToolTipBase": "#2b2b2b",
        "ToolTipText": "#e0e0e0",
        "PlaceholderText": "#888888",
        "Link": "#4ea1f3",
        "LinkVisited": "#b48cff",
        # Frame / bevel shading tuned so scroll tracks and focus rings
        # stay visible against the dark backgrounds.
        "Mid": "#3a3a3a",
        "Midlight": "#4a4a4a",
        "Dark": "#141414",
        "Light": "#555555",
        "Shadow": "#000000",
    },
    disabled_spec={
        "Text": "#6e6e6e",
        "WindowText": "#6e6e6e",
        "ButtonText": "#6e6e6e",
        "HighlightedText": "#9a9a9a",
    },
    stylesheet=_DARK_STYLESHEET,
)

_LIGHT_GRAY = Theme(
    id="light_gray",
    label="Light gray (reading)",
    description="Soft gray page background - reduces glare on bright screens.",
    is_dark=False,
    palette_spec={
        "Window": "#e6e6e6",
        "WindowText": "#1b1b1b",
        "Base": "#f0f0f0",
        "AlternateBase": "#e0e0e0",
        "Text": "#1b1b1b",
        "Button": "#d9d9d9",
        "ButtonText": "#1b1b1b",
        "BrightText": "#000000",
        "Highlight": "#b8c8dc",
        "HighlightedText": "#101010",
        "ToolTipBase": "#e8e8e8",
        "ToolTipText": "#1b1b1b",
        "PlaceholderText": "#6f6f6f",
        "Link": "#1a5fb4",
        "LinkVisited": "#6a3db0",
        "Mid": "#bcbcbc",
        "Midlight": "#d0d0d0",
        "Dark": "#9a9a9a",
        "Light": "#f7f7f7",
        "Shadow": "#777777",
    },
    disabled_spec={
        "Text": "#8e8e8e",
        "WindowText": "#8e8e8e",
        "ButtonText": "#8e8e8e",
        "HighlightedText": "#5a5a5a",
    },
    stylesheet=_LIGHT_GRAY_STYLESHEET,
)

_SEPIA = Theme(
    id="sepia",
    label="Sepia (reading)",
    description="Warm parchment palette - gentle for long reading sessions.",
    is_dark=False,
    palette_spec={
        "Window": "#f0e3c6",
        "WindowText": "#3b2c1a",
        "Base": "#f6ecd5",
        "AlternateBase": "#ece0c3",
        "Text": "#3b2c1a",
        "Button": "#e5d4b6",
        "ButtonText": "#3b2c1a",
        "BrightText": "#1a0f06",
        "Highlight": "#d8bf8e",
        "HighlightedText": "#2a1f12",
        "ToolTipBase": "#efe4cf",
        "ToolTipText": "#3b2c1a",
        "PlaceholderText": "#7a6244",
        "Link": "#8a4b12",
        "LinkVisited": "#6e3c9a",
        "Mid": "#b99a70",
        "Midlight": "#d5bf96",
        "Dark": "#8a6d43",
        "Light": "#faf1de",
        "Shadow": "#6b5028",
    },
    disabled_spec={
        "Text": "#9a8560",
        "WindowText": "#9a8560",
        "ButtonText": "#9a8560",
        "HighlightedText": "#5a4a30",
    },
    stylesheet=_SEPIA_STYLESHEET,
)


# Public registry. Order is the order the View menu shows the themes.
THEMES: tuple[Theme, ...] = (_LIGHT, _DARK, _LIGHT_GRAY, _SEPIA)

THEMES_BY_ID: dict[str, Theme] = {t.id: t for t in THEMES}

DEFAULT_THEME_ID: str = "light"


# ---------------------------------------------------------------------------
# Application helpers
# ---------------------------------------------------------------------------


def get_theme(theme_id: str | None) -> Theme:
    """Return the theme with ``theme_id`` or the default (Light) theme.

    Unknown / missing ids resolve to the default so callers never have
    to deal with lookup failures. Legacy persisted values such as the
    old ``"system"`` id are silently remapped here (and by
    ``_coerce_theme_id`` on load) without needing an explicit
    migration step.
    """
    if theme_id and theme_id in THEMES_BY_ID:
        return THEMES_BY_ID[theme_id]
    return THEMES_BY_ID[DEFAULT_THEME_ID]


def _palette_from_spec(
    spec: dict[str, str], disabled_spec: dict[str, str] | None = None
) -> QPalette:
    """Build a ``QPalette`` from role -> hex color mappings.

    ``spec`` drives the Active / Inactive color groups (they share the
    same color for our themes - Qt's "focused vs unfocused window"
    distinction isn't something we need to style separately). Any entry
    in ``disabled_spec`` overrides the default Fusion-derived color for
    ``QPalette.ColorGroup.Disabled``; that's where we tighten contrast
    on themes where Fusion's auto-derivation is hard to read.
    """
    p = QPalette()
    for role in _ROLES:
        hex_value = spec.get(role)
        if not hex_value:
            continue
        color_role = getattr(QPalette.ColorRole, role, None)
        if color_role is None:
            continue
        color = QColor(hex_value)
        p.setColor(QPalette.ColorGroup.Active, color_role, color)
        p.setColor(QPalette.ColorGroup.Inactive, color_role, color)
        p.setColor(QPalette.ColorGroup.Disabled, color_role, color)
    if disabled_spec:
        for role in _DISABLED_ROLES:
            hex_value = disabled_spec.get(role)
            if not hex_value:
                continue
            color_role = getattr(QPalette.ColorRole, role, None)
            if color_role is None:
                continue
            p.setColor(QPalette.ColorGroup.Disabled, color_role, QColor(hex_value))
    return p


def apply_theme(app, theme_id: str | None) -> Theme:
    """Apply ``theme_id`` to the running ``QApplication``.

    Returns the resolved :class:`Theme` (which may fall back to the
    default when ``theme_id`` is unknown). Safe to call repeatedly:
    previous overrides are replaced wholesale each time so a user can
    cycle between themes without state leaking.

    Every theme uses Qt's ``Fusion`` style. Fusion is fully
    ``QPalette``-driven, so our palettes actually cover every widget -
    buttons, combos, date pickers, line edits, plain-text edits,
    checkboxes, tabs, scrollbars. The native platform styles (``windowsvista``
    on Windows, ``macOS`` on macOS) draw many controls through OS APIs
    and ignore parts of the palette, which is why we don't use them.
    """
    theme = get_theme(theme_id)
    app.setStyle(_FUSION_STYLE)
    # ``palette_spec`` is optional in the type for future flexibility,
    # but every built-in theme supplies one; guard defensively anyway
    # so a hand-constructed Theme without a spec doesn't crash here.
    if theme.palette_spec is not None:
        app.setPalette(_palette_from_spec(theme.palette_spec, theme.disabled_spec))
    app.setStyleSheet(theme.stylesheet)
    return theme


def list_themes() -> tuple[Theme, ...]:
    """Return the themes in menu / display order."""
    return THEMES
