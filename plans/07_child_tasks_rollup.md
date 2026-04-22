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
  descendants to prevent cycles).
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
  (`children_summary(task_id) -> dict`).
- `tasktracker/services/reporting_service.py` — when "group by parent" is
  meaningful, expose it.
- New widget `tasktracker/ui/children_panel.py` — parent's children table.
- `tasktracker/ui/main_window.py` — list column / badge for rollup; parent
  picker.
- `tests/test_parent_child.py` (new).

## Work breakdown

- [ ] Schema upgrade + model.
- [ ] Service methods: `set_parent`, `clear_parent`, `list_children`,
      `children_summary`.
- [ ] Enforce depth <= 2 and no cycles.
- [ ] Parent picker widget.
- [ ] Children panel on task detail (inline or tab per layout placement).
- [ ] Rollup badges on Tasks list rows.
- [ ] Close-parent-with-open-children warning flow.
- [ ] Dashboard / reports review: confirm existing queries don't
      double-count. Update as needed.
- [ ] Tests: happy path, cycle prevention, depth guard, delete-parent
      nulls children, rollup accuracy.

## Validation checklist

- [ ] Setting a child's parent and then deleting the parent nulls
      `parent_task_id` on the child; child is not deleted.
- [ ] Making A parent of B, then attempting to make B parent of A, is
      rejected.
- [ ] Attempting to create a grandchild (A parent of B, B parent of C) is
      rejected with a clear error.
- [ ] Rollup badge on A shows "2 / 5 closed" when 2 of 5 children are
      closed; flips to overdue-flag when any open child is past due.
- [ ] Closing a parent with open children surfaces the warning and does not
      silently close children.
- [ ] Existing reports (WIP aging, throughput, workload) remain accurate —
      double-counting is avoided where meaningful.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — max depth of 2, cycle policy, cascade behavior.
- [ ] `tasktracker/resources/user_guide.html` — "Parent and child tasks"
      section.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.

## Risks / open questions

- **Report double-counting.** If a parent is a thin "project" shell and its
  children carry the real work, counting both inflates numbers. Decide per
  report whether to include parents, children, or both; document in the
  report definitions.
- **List density.** Rollup badges on every row can add visual noise. Keep the
  badge compact and show it only when a task actually has children.
- **Existing data migration.** Pre-plan vaults have no parents; the column
  defaults to NULL. No data migration beyond the upgrade itself.

## Follow-ups discovered

_(empty at start of plan)_
