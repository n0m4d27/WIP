# Plan 08 - Effort, time log, and daily review

## Goal

Track estimated vs actual effort per task and per todo, make logging time a
one-click action, and add a daily-review surface so "where did my time go
this week" can be answered from inside the app.

## Problem it solves

- Capacity conversations with management have no data behind them today.
  Estimates live in people's heads; actuals are never recorded.
- Analysts frequently lose track of which thread consumed an afternoon — a
  lightweight "log 30 min" button stacked across the day becomes a useful
  self-reflection tool and a defensible backup for standup updates.
- Folding the daily-review surface into this plan (rather than a standalone
  Tier 3 doc) keeps the effort feature end-to-end in one rollout.

## Problem it solves (specific, roadmap-level)

- Addresses Tier 2 item "effort + time-log" and Tier 3 item "daily time-log
  review" as a single feature family so context is not paged in twice.

## In scope

### Effort fields

- `estimated_minutes` and `actual_minutes` columns on `Task` and `TodoItem`.
  Actuals are usually the sum of time-log entries; manual override remains
  possible.
- Edit surfaces: small "Estimate" / "Actual" inputs on the task panel and on
  the todo dialog.

### Time log

- New `TimeLogEntry` entity: `task_id`, optional `todo_id`, `minutes`,
  `logged_on` (date), `note` (TEXT), `created_at`.
- Task panel "Log time..." button with quick presets (15 / 30 / 45 / 60 / 90
  minutes) and a custom-amount dialog.
- Table of recent entries on the task, with edit / delete.
- Rollup: `Task.actual_minutes` is derived from entries by default (sum);
  user can switch to manual override explicitly.

### Daily review

- A Daily review panel on the Dashboard tab (plan 01) listing the chosen
  day's entries, total minutes, and a quick per-task breakdown.
- Date-picker defaulting to today with prev / next day / week buttons.
- Export to CSV for a given date range.

## Out of scope

- Timer / stopwatch mode. All logging is post-hoc entry.
- Cross-task timekeeping reports in the management-facing Reports tab
  (could be a follow-up; keeps this plan from ballooning).
- Calendar-style time-blocking view.
- Billing-grade accuracy / immutability. Entries are editable by design.

## Schema / data model changes

- `tasks.estimated_minutes` INT NULL.
- `tasks.actual_minutes` INT NULL (manual override column; derived value
  computed on read if NULL).
- `todo_items.estimated_minutes` INT NULL.
- `todo_items.actual_minutes` INT NULL.
- `time_log_entries`:
  - `id`, `task_id` (FK CASCADE), `todo_id` (FK SET NULL),
    `minutes` INT NOT NULL CHECK (minutes > 0), `logged_on` DATE NOT NULL,
    `note` TEXT NULL, `created_at` DATETIME NOT NULL.
- Schema upgrade adds columns + table idempotently.

## Code touch list (expected files)

- `tasktracker/db/models.py` — columns + `TimeLogEntry`.
- `tasktracker/db/schema_upgrade.py` — column adds + table create.
- `tasktracker/services/task_service.py` — estimate / actual getters /
  setters, `add_time_entry`, `update_time_entry`, `delete_time_entry`,
  `time_entries_between(from_date, to_date)`.
- New widget `tasktracker/ui/time_log_panel.py` — per-task table + Log time
  action.
- New widget `tasktracker/ui/daily_review_panel.py` — dashboard card.
- `tasktracker/ui/main_window.py` — wire panels.
- `tasktracker/services/excel_export.py` — add time-log sheet to the rich
  workbook.
- `tests/test_time_log.py` (new).

## Work breakdown

- [ ] Schema upgrade (columns + table).
- [ ] Service CRUD for entries; rollup helper for `actual_minutes`.
- [ ] Task panel estimate / actual inputs.
- [ ] Log time action + preset dialog.
- [ ] Entries table on task detail.
- [ ] Daily review panel on dashboard (depends on plan 01 being in place).
- [ ] CSV export for a date range.
- [ ] Extend rich workbook export with time-log sheet.
- [ ] Tests: CRUD, rollup, export shape.

## Validation checklist

- [ ] Adding two 30-minute entries on a task with no override shows
      `actual_minutes = 60` in the UI rollup.
- [ ] Setting the manual override to 90 makes the rollup show 90 regardless
      of entry sum.
- [ ] Clearing the override reverts to the entry-sum rollup.
- [ ] Deleting a todo with `todo_id` time entries nulls the `todo_id` on the
      entries (they remain on the parent task).
- [ ] Daily review panel totals match the sum of entries for that date.
- [ ] CSV export contains one row per entry with stable columns.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — estimate / actual model, rollup strategy,
      entry immutability position (editable).
- [ ] `tasktracker/resources/user_guide.html` — "Effort and time log" section.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.
- [ ] `FEATURE_GUIDE.md` — effort / time log surfaces and data model.

## Risks / open questions

- **Rollup performance.** Summing entries on every task render could be slow
  on large vaults; cache on write or compute in a single join query.
- **Dependency on plan 01.** Daily review panel is best placed on the
  dashboard. If plan 01 has not landed yet, deliver the daily review as a
  standalone small tab and move it to the dashboard in a follow-up.
- **Interaction with plan 06 tags.** "Hours per tag" is an obvious follow-up
  but not in scope here.

## Follow-ups discovered

_(empty at start of plan)_
