"""User-configurable date display format.

Three responsibilities live here:

* **Presets** - a curated list of common formats shown in the settings
  dialog so the user doesn't have to know Qt's pattern syntax.
* **Qt <-> Python conversion** - a small token translator so the same
  format the user picks for ``QDateEdit.setDisplayFormat`` can also be
  fed into :func:`datetime.date.strftime` for code paths that aren't
  holding a ``QDate`` object. Only the tokens used by the presets (and
  the ones power-users are plausibly going to type freehand) are
  translated; any unrecognised tokens fall through verbatim so a
  trailing ``-`` or a literal ``at`` still renders correctly.
* **Rendering helpers** - one-call converters for ``datetime.date``
  objects and for ISO-string-laden text blocks (summaries, labels) so
  we can re-format values that already came out of the service layer
  as ``YYYY-MM-DD`` without re-plumbing every service to take a format
  parameter.

The ISO format is the default and also the wire format used for
exports (CSV / Excel / JSON) regardless of the user's pick - those
files get consumed by Excel, pandas, and spreadsheets where a literal
ISO date is the least surprising shape. See ``tech_decisions.md`` for
the full rationale.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from tasktracker.ui.settings_store import DEFAULT_DATE_FORMAT


@dataclass(frozen=True)
class DateFormatPreset:
    """One entry in the Settings dialog's preset drop-down.

    ``qt_format`` is what ``QDateEdit.setDisplayFormat`` expects.
    ``label`` is the human label (with a live example baked in).
    """

    qt_format: str
    label: str


# Curated presets. Order is the display order in the settings dialog.
DATE_FORMAT_PRESETS: tuple[DateFormatPreset, ...] = (
    DateFormatPreset("yyyy-MM-dd", "ISO  2026-04-17  (yyyy-MM-dd)  [default]"),
    DateFormatPreset("MM/dd/yyyy", "US  04/17/2026  (MM/dd/yyyy)"),
    DateFormatPreset("dd/MM/yyyy", "EU  17/04/2026  (dd/MM/yyyy)"),
    DateFormatPreset("d MMM yyyy", "Short  17 Apr 2026  (d MMM yyyy)"),
    DateFormatPreset("MMM d, yyyy", "US long  Apr 17, 2026  (MMM d, yyyy)"),
    DateFormatPreset("dd MMMM yyyy", "Long  17 April 2026  (dd MMMM yyyy)"),
)


# Token translation table from Qt's QDateTime format syntax to strftime.
# Order matters: multi-character tokens must come before shorter ones so a
# ``yyyy`` pattern doesn't get munched four times as ``y`` / ``yy``.
_QT_TO_PY_TOKENS: tuple[tuple[str, str], ...] = (
    ("yyyy", "%Y"),
    ("yy", "%y"),
    ("MMMM", "%B"),
    ("MMM", "%b"),
    ("MM", "%m"),
    ("dddd", "%A"),
    ("ddd", "%a"),
    ("dd", "%d"),
    # Single-letter M/d map to platform-specific "no padding" specifiers.
    # ``%-m`` / ``%-d`` are Linux/macOS; Windows uses ``%#m`` / ``%#d``.
    # We prefer the zero-padded forms for portability and pick explicit
    # no-pad only when a preset truly needs it (none do today).
    ("M", "%m"),
    ("d", "%d"),
)


def qt_to_py_format(qt_fmt: str) -> str:
    """Translate a Qt display format into a ``strftime`` pattern.

    Tokens that aren't in the translation table (spaces, commas, dashes,
    literal text) pass through verbatim. Unrecognised letter runs also
    pass through unchanged so typos degrade gracefully instead of
    raising.
    """
    # Walk the string token-by-token so we don't rewrite ``MMM`` inside the
    # expansion of ``yyyy`` or similar. Building a regex with alternation
    # would work too but this form keeps the semantic order explicit.
    out: list[str] = []
    i = 0
    n = len(qt_fmt)
    while i < n:
        matched = False
        for qt_tok, py_tok in _QT_TO_PY_TOKENS:
            if qt_fmt.startswith(qt_tok, i):
                out.append(py_tok)
                i += len(qt_tok)
                matched = True
                break
        if not matched:
            out.append(qt_fmt[i])
            i += 1
    return "".join(out)


def format_date(d: dt.date | None, qt_fmt: str | None = None) -> str:
    """Render a ``dt.date`` using the given Qt format (or the default).

    Returns the empty string for ``None`` so this helper is drop-in for
    ``.isoformat() if d else ""`` patterns scattered through the UI.
    """
    if d is None:
        return ""
    fmt = qt_fmt or DEFAULT_DATE_FORMAT
    py_fmt = qt_to_py_format(fmt)
    try:
        return d.strftime(py_fmt)
    except ValueError:
        # Invalid strftime directive (e.g. Windows-only specifier on Linux).
        # Fall back to ISO rather than crashing - the user still gets a
        # legible date, they just don't see their custom format applied.
        return d.isoformat()


_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def reformat_iso_dates_in_text(text: str, qt_fmt: str | None = None) -> str:
    """Find ``YYYY-MM-DD`` runs in ``text`` and rewrite them in ``qt_fmt``.

    Report summaries and audit lines already come out of the service
    layer pre-formatted as ISO strings, which keeps exports crisp. The
    UI surfaces (Reports summary panel, status-bar messages) run the
    result of those services through this helper so the display still
    honours the user's format choice without us having to thread a
    format parameter through every service call.

    Whitespace and surrounding punctuation are preserved. When the
    chosen format is ISO itself the function is a no-op (fast path).
    """
    fmt = qt_fmt or DEFAULT_DATE_FORMAT
    if fmt == "yyyy-MM-dd":
        return text

    def _swap(match: re.Match[str]) -> str:
        try:
            d = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return match.group(0)
        return format_date(d, fmt)

    return _ISO_DATE_RE.sub(_swap, text)


def format_from_parent(parent) -> str:
    """Look up the Qt date format from a Qt parent chain.

    Walks the parent chain looking for an object with a ``_ui_settings``
    attribute (the ``MainWindow``) and returns the stored format, or the
    default when no such ancestor is found. Handy for short-lived dialogs
    that are constructed with ``parent=main_window`` and want their date
    pickers to match the rest of the app without the call sites having
    to thread a settings dict everywhere.
    """
    from tasktracker.ui.settings_store import get_date_format_qt

    cur = parent
    # Bound the walk to a sensible depth in case someone creates a cycle.
    for _ in range(16):
        if cur is None:
            return DEFAULT_DATE_FORMAT
        settings = getattr(cur, "_ui_settings", None)
        if isinstance(settings, dict):
            return get_date_format_qt(settings)
        parent_fn = getattr(cur, "parent", None)
        cur = parent_fn() if callable(parent_fn) else None
    return DEFAULT_DATE_FORMAT


DISPLAY_TIMEZONE_LOCAL = "local"


def is_valid_iana_timezone(name: str) -> bool:
    """Return True if ``name`` is a loadable IANA timezone identifier."""
    if not name or not isinstance(name, str):
        return False
    try:
        ZoneInfo(name.strip())
    except Exception:
        return False
    return True


def resolve_display_tz(tz_key: str) -> dt.tzinfo:
    """Resolve settings key ``local`` or an IANA name to a ``tzinfo``."""
    k = (tz_key or "").strip()
    if not k or k == DISPLAY_TIMEZONE_LOCAL:
        local = dt.datetime.now().astimezone().tzinfo
        return local if local is not None else dt.timezone.utc
    try:
        return ZoneInfo(k)
    except Exception:
        local = dt.datetime.now().astimezone().tzinfo
        return local if local is not None else dt.timezone.utc


def format_activity_timestamp(when: dt.datetime, tz_key: str) -> str:
    """Format an aware (or UTC-assumed naive) instant for the activity panel."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    tz = resolve_display_tz(tz_key)
    local = when.astimezone(tz)
    abbr = local.tzname() or ""
    base = local.strftime("%Y-%m-%d %H:%M")
    if abbr:
        return f"{base} {abbr}"
    return base


def iso_string_to_display(value: str | None, qt_fmt: str | None = None) -> str:
    """Treat ``value`` as a single ISO date string and render it.

    Returns ``value`` unchanged when parsing fails - useful for report
    row dicts where a column is *usually* a date but occasionally
    contains a sentinel like ``"no due"`` or ``"(unassigned)"``.
    """
    if not value:
        return value or ""
    try:
        d = dt.date.fromisoformat(value)
    except ValueError:
        return value
    return format_date(d, qt_fmt)
