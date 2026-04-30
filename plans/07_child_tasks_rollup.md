# Plan 07 - Child tasks and rollup

## Goal

Let a task have an optional parent task, turning flat task lists into a
shallow hierarchy ("Hire 12 analysts" -> one child task per hire) with rollup
indicators so a parent reflects the state of its children at a glance.

## Problem it solves

- Todos are good for linear checklists but bad for independent streams of
  work. A headcount push with 12 hires needs 12 separate lifecycles, each
  with its own dates, owner, blockers, notes — that is 12 tasks, not 12
  todos on one task.
- Without parent / child, the only way to bundle related tasks is by tag or
  area, neither of which rolls up progress.

## In scope

- Optional `parent_task_id` column on `tasks` (self-FK, SET NULL on delete).
- UI in task detail to set / clear the parent; a small "Children" panel on
  parents showing child rows with status, due date, priority, and completion.
- Rollup indicators on parent rows in the Tasks list:
  - `Children closed / total`
  - Badge if any child is overdue or blocked.
- Parent selection picker (search / filter over existing tasks; excludes
  descendants to prevent cycles) using the same scalable pattern established
  by plans 06 and 06-01:
  - dedicated searchable picker dialog rather than a plain dropdown
  - case-insensitive matching on task title and ticket text (`T123`, `123`)
  - candidate pruning for invalid choices before display
  - respects the Tasks-tab closed-task visibility toggle in the same way the
    dependency picker does, so closed tasks can be included when the user has
    chosen to show them
- Close-task interaction: closing a parent does **not** cascade to children.
  It surfaces a gentle warning if any children are still open, so the user
  decides explicitly.
- Rollup propagation to the dashboard (plan 01) and to reports (plan 08
  consumes parent context for time aggregation).

## Out of scope

- Deep hierarchies. Enforce max depth of 2 (a child cannot itself be a
  parent) to keep reports and lists simple. Revisit only if real need
  emerges.
- Auto-close parent when all children close. Explicit action only.
- Gantt visualization. Tabular view first.

## Schema / data model changes

- `tasks.parent_task_id` (INT NULL, FK to `tasks.id` SET NULL, indexed).
- Service-layer guard enforces the max-depth-of-2 rule and prevents cycles.
- Schema upgrade adds the column + index idempotently.

## Code touch list (expected files)

- `tasktracker/db/models.py` — new column + self-relationship.
- `tasktracker/db/schema_upgrade.py` — add column + index.
- `tasktracker/services/task_service.py` — set / clear parent with depth and
  cycle guards; `list_children(task_id)`; rollup helpers
  (`children_summary(task_id) -> dict`); candidate-shaping helper for the
  parent picker if needed.
- `tasktracker/services/reporting_service.py` — when "group by parent" is
  meaningful, expose it.
- New widget `tasktracker/ui/children_panel.py` — parent's children table.
- New dialog `tasktracker/ui/parent_picker_dialog.py` — searchable parent-task
  selector, matching the picker UX introduced for dependencies in plan 06-01.
- `tasktracker/ui/main_window.py` — list column / badge for rollup; parent
  picker.
- `tests/test_parent_child.py` (new).

## Work breakdown

- [x] Schema upgrade + model.
- [x] Service methods: `set_parent`, `clear_parent`, `list_children`,
      `children_summary`.
- [x] Enforce depth <= 2 and no cycles.
- [x] Parent picker widget using the searchable dialog pattern from plan
      06-01.
- [x] Candidate rules for the picker:
      - exclude the current task
      - exclude descendants / any cycle-causing choice
      - enforce depth <= 2 before the user can pick
      - include or exclude closed tasks based on the same hide/show-closed
        behavior the dependency picker follows
- [x] Children panel on task detail (inline or tab per layout placement).
- [x] Rollup badges on Tasks list rows.
- [x] Close-parent-with-open-children warning flow.
- [x] Dashboard / reports review: confirm existing queries don't
      double-count. Update as needed.
- [x] Tests: happy path, cycle prevention, depth guard, delete-parent
      nulls children, rollup accuracy.

## Validation checklist

- [x] Setting a child's parent and then deleting the parent nulls
      `parent_task_id` on the child; child is not deleted.
- [x] Making A parent of B, then attempting to make B parent of A, is
      rejected.
- [x] Attempting to create a grandchild (A parent of B, B parent of C) is
      rejected with a clear error.
- [x] With many tasks (50+), the parent picker narrows correctly by title or
      ticket text and remains usable.
- [x] Closed tasks appear in the parent picker only when the user has chosen
      to show closed tasks in the Tasks-tab context, matching the behavior
      built in plan 06-01.
- [x] Rollup badge on A shows "2 / 5 closed" when 2 of 5 children are
      closed; flips to overdue-flag when any open child is past due.
- [x] Closing a parent with open children surfaces the warning and does not
      silently close children.
- [x] Existing reports (WIP aging, throughput, workload) remain accurate —
      double-counting is avoided where meaningful.
- [x] Existing test suite green.

## Docs to update on landing

- [x] `tech_decisions.md` — max depth of 2, cycle policy, cascade behavior.
- [x] `tasktracker/resources/user_guide.html` — "Parent and child tasks"
      section.
- [x] `plans/README.md` — mark Done, log follow-ups / bugs.
- [x] `FEATURE_GUIDE.md` — parent/child tasks and rollup rules.

## Risks / open questions

- **Report double-counting.** If a parent is a thin "project" shell and its
  children carry the real work, counting both inflates numbers. Decide per
  report whether to include parents, children, or both; document in the
  report definitions.
- **List density.** Rollup badges on every row can add visual noise. Keep the
  badge compact and show it only when a task actually has children.
- **Picker scale.** A plain combo box will break down quickly with dozens of
  tasks. Reuse the searchable picker interaction from plan 06-01 instead of
  inventing a second, inconsistent selection UX.
- **Existing data migration.** Pre-plan vaults have no parents; the column
  defaults to NULL. No data migration beyond the upgrade itself.

## Follow-ups discovered

_(empty at start of plan)_
