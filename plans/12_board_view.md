# Plan 12 - Board view

## Goal

A Kanban / swimlane board tab — columns by status (default) or by an
alternate dimension, with optional swimlanes — so the user can see WIP
saturation and flow at a glance, complementing the list and calendar views.

## Problem it solves

- The task list is good for search, the calendar is good for dates, but
  neither shows "how packed is in-progress right now" at a glance.
- A board makes WIP pressure obvious and encourages finishing before
  starting, which is the core productivity win of Kanban.

## In scope

- New **Board** tab in the main window (tab position after Reports).
- Columns: default by status (`Open`, `In progress`, `Blocked`, `On hold`,
  `Closed` within a rolling window).
- Alternate column options (dropdown): `By priority`, `By for-person`,
  `By area`.
- Optional swimlanes orthogonal to columns (e.g. columns = status, lanes =
  for-person).
- Card content: ticket, title, priority chip, due-date indicator, overdue /
  blocked badges, aging chip (after plan 11), child rollup badge (after
  plan 07), tag chips (after plan 06).
- Drag-and-drop between columns to change status (or the active dimension).
  Drops that would be invalid (e.g. dropping a card with open subtasks into
  Closed when plan 07 has landed) prompt confirmation.
- Column collapse to thin strips for seldom-used columns.
- Filter bar reuses the saved views (plan 01) when that has landed.

## Out of scope

- WIP limits with enforcement (warnings only, if at all).
- Per-column sort orders beyond a default (priority then due date).
- Board export to image / PDF.
- Custom column definitions (free-form).

## Schema / data model changes

None. The board is a pure view over existing data.

## Code touch list (expected files)

- New module `tasktracker/ui/board_view.py` — column layout, card widget,
  drag-and-drop plumbing.
- `tasktracker/ui/main_window.py` — tab registration and shared filter
  integration.
- `tasktracker/ui/settings_store.py` — remember last-used dimension / lane
  config per vault.
- `tests/test_board_view.py` (new) — offscreen smoke of column bucketing
  and drag-drop bucket-change dispatch (not the Qt drop itself).

## Work breakdown

- [ ] Data model for the board view (columns + cards dataclasses).
- [ ] Widget skeleton with static columns; cards render correctly.
- [ ] Dimension switcher (status / priority / for-person / area).
- [ ] Swimlane toggle and renderer.
- [ ] Drag-and-drop to move cards between columns; on drop, dispatch the
      right field update (status, priority, assignment, area).
- [ ] Column collapse / expand with persistence.
- [ ] Card chips: priority, due, overdue, blocked; others if prerequisite
      plans have landed.
- [ ] Filter integration: same filters as the Tasks tab; saved views apply
      identically.
- [ ] Tests: bucketing logic and field dispatch on drop.

## Validation checklist

- [ ] Moving a card from In progress to Blocked updates the task status
      correctly and produces an audit row.
- [ ] Switching the column dimension from status to priority re-buckets
      without requiring a refresh.
- [ ] Collapsed column state persists across app restarts.
- [ ] Filter (e.g. a saved view) applies to the board and the Tasks tab
      consistently.
- [ ] Large vaults (500+ open tasks) still render the board within a
      reasonable time (soft goal; measure once during validation).
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — board as a pure view over existing data;
      drag-drop field dispatch rules.
- [ ] `tasktracker/resources/user_guide.html` — new "Board view" section.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.
- [ ] `FEATURE_GUIDE.md` — board view axes, gestures, persistence.

## Risks / open questions

- **Drag-drop semantics with custom dimensions.** Dropping into an "area"
  column implies reassigning area; make sure this is the intent and not a
  surprise. Confirmation dialog on first drop of the session is a cheap
  guardrail.
- **Rendering performance.** Qt's default widget-per-card approach can
  struggle past a few hundred cards. If this bites, consider a virtualized
  list.
- **Dependency on other plans.** Cards are richer when tags, aging, and
  rollups have landed, but the board is still useful without them. Ship
  with the chips that are available.

## Follow-ups discovered

_(empty at start of plan)_
