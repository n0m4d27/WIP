# Plan 01 - Dashboard and saved views

## Goal

Give the app a landing tab that answers "what needs my attention right now"
at a glance, plus a persisted set of named filters ("saved views") that turn
repeated triage lookups into one click.

## Problem it solves

- Current startup lands on the task list with no prioritization hint; overdue
  or due-today items can sit unnoticed behind unrelated rows.
- Filter state on the Tasks tab is transient; "My WFM open", "Headcount P1+P2",
  "Waiting-on-HR" have to be reconstructed every morning.
- Without a saved-view sidebar, muscle memory for daily triage has to live in
  the user's head, which is exactly the failure mode the roadmap is trying to
  kill.

## In scope

- New **Dashboard** tab in the main window, inserted as the leftmost tab so it
  is the default on startup.
- Dashboard cards (at minimum): **Due today**, **Overdue**, **Due this week**,
  **Blocked**, **Top priority (P1/P2) open**.
- Each card shows a row count, a compact list of up to N items, and a
  "Show all" affordance that jumps into Tasks with the matching filter applied.
- **Saved views** sidebar on the Tasks tab: a small list of named filters
  persisted in `ui_settings.json`. Each view captures the current search /
  filter state (status, priority, area, for-person, date range, free text).
- Actions on the saved views list: Save current filters as view, Rename,
  Delete, Apply, Reorder (move up / move down).
- Default order of views is user-editable; startup remembers which view was
  last applied (optional; opt-out if startup noise proves annoying).

## Out of scope

- Widget theming or per-user dashboard layout customization beyond card
  enable/disable. Layout is fixed; extra flexibility lands as a follow-up if
  needed.
- Cross-user sharing of saved views. Views live in per-vault `ui_settings.json`.
- Dashboard drill-down in place (e.g. inline editing from a card). Clicking a
  card item opens the task in the Tasks tab, same as list double-click.
- Charts / sparkline visualizations (would duplicate reporting work).

## Schema / data model changes

None. Everything is computed from existing tables.

## Code touch list (expected files)

- `tasktracker/ui/main_window.py` — tab registration, startup tab selection.
- New module `tasktracker/ui/dashboard.py` — dashboard widget + card
  components.
- New module `tasktracker/ui/saved_views.py` — saved-views sidebar widget and
  model.
- `tasktracker/ui/settings_store.py` — `saved_views` section with
  load / save / default helpers (mirror existing `get_*` / `set_*` patterns).
- `tasktracker/services/task_service.py` — small `dashboard_counts()` /
  `dashboard_sections()` helpers if queries are cleaner in one place.
- `tests/test_dashboard.py` (new) — unit coverage for the query helpers and
  settings round-trip of saved views.
- `tests/test_settings_store.py` — saved-views coercion and defaults.

## Work breakdown

- [ ] Define dashboard card dataclass (title, icon, count, top N rows, empty-state).
- [ ] Implement service-layer queries for each card (reuse existing indexes).
- [ ] Build `dashboard.py` widget with cards laid out in a responsive grid.
- [ ] Wire "Show all" on each card to the Tasks tab with a matching filter
      payload.
- [ ] Add `SavedView` dataclass and settings helpers (`get_saved_views`,
      `set_saved_views`, `add_saved_view`, `remove_saved_view`).
- [ ] Build saved-views sidebar on Tasks tab (list + action buttons).
- [ ] Add "Save current filters as view..." affordance to the existing filter
      bar.
- [ ] Register Dashboard as tab index 0; preserve user's last tab on relaunch
      via existing `ui_settings.json` pattern if one exists, else start on
      Dashboard.
- [ ] Unit tests for dashboard queries and saved-views persistence.
- [ ] Offscreen smoke test: open main window, Dashboard renders, saved view
      round-trip works.

## Validation checklist

- [ ] Overdue card count matches `select count(*) from tasks where due_date < today and status not in ('closed','cancelled')`.
- [ ] Due-today and Due-this-week cards agree with the Reports tab's overlap.
- [ ] Blocked card matches "status = blocked" count.
- [ ] Top priority card lists P1+P2 open items sorted by due date then priority.
- [ ] Saved view round-trips through `ui_settings.json` without losing
      free-text or date filters.
- [ ] Saved view applies identically whether picked from sidebar or from the
      "Apply" button.
- [ ] Existing Tasks tab behavior unchanged when the saved-views sidebar is
      empty (no layout regression).
- [ ] Non-Qt tests pass (`pytest tests/ -q --ignore=tests/test_*_ui.py` or the
      project's usual filter).

## Docs to update on landing

- [ ] `tech_decisions.md` — short note describing the Dashboard tab and where
      saved views live.
- [ ] `tasktracker/resources/user_guide.html` — new "Dashboard" and "Saved
      views" sections.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.

## Risks / open questions

- **Performance on vaults with many tasks.** All card queries must hit indexes;
  watch for a regression if `ui_settings.json`'s recent default filter triggers
  a scan.
- **Saved-view schema evolution.** Once views exist, adding a new filter
  dimension (e.g. tags from plan 06) needs a forward-compatible shape. Use a
  `dict[str, Any]` payload under a `version` key.
- Should the last-applied saved view auto-apply at startup? Probably opt-in,
  default off, to avoid surprises.

## Follow-ups discovered

_(empty at start of plan)_
