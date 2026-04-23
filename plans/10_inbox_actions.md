# Plan 10 - Inbox actions (snooze + bulk edit)

## Goal

Two small but high-leverage actions that turn the Tasks list into an
inbox-style triage surface:

1. **Snooze / defer** — hide a task from "active" views for N business days
   with one click, then resurface automatically.
2. **Bulk edit** — apply a single change (status, for-person, area, tags)
   across many selected tasks at once, mirroring the shape of the existing
   bulk-shift feature.

## Problem it solves

- Today the only way to "put a task down until Monday" is to rewrite the due
  date, which conflates "not yet" with "late". Snooze captures intent
  cleanly.
- Bulk changes across many tasks are common (re-homing a pile to a new
  person, retagging a cohort after a taxonomy cleanup). Without bulk edit,
  those turn into dozens of manual saves.

## In scope

### Snooze / defer

- New `snoozed_until` DATE column on `tasks` (NULL = not snoozed).
- Context-menu actions on the task list: "Snooze 1 day", "Snooze 3 business
  days", "Snooze 1 week", "Snooze until..." (date picker).
- Default task list / dashboard views hide snoozed items whose
  `snoozed_until` is still in the future; a toggle / filter reveals them.
- Auto-wake: when a snoozed task's date arrives, it reappears without user
  action. A small "Woke today" indicator persists for a day so the user
  notices.
- Snooze is orthogonal to status — a snoozed task can still have status
  `open`, `in_progress`, etc.

### Bulk edit

- Multi-select already exists in the Tasks list (same selection model as
  plan used for bulk shift).
- New context-menu action: "Bulk edit..." -> dialog with a tabbed or
  grouped set of fields, each with an "apply this field" checkbox:
  - Status
  - For-person
  - Area (plus derived category / sub-category)
  - Tags (add / remove / replace set — after plan 06 lands)
- Preview dialog modeled after `ShiftPreviewDialog`: shows each task's
  before / after for changed fields, with one-click Undo via an audit
  entry.
- Audit: each task gets a normal field-audit row plus a small "bulk edit
  N/M" summary note (same shape as bulk shift).

## Out of scope

- Bulk edit for dates (already covered by bulk shift / slip service).
- Bulk delete. Too dangerous to ship alongside triage actions; separate
  feature with its own confirmation flow.
- Scheduled snooze recurrence ("snooze this every Friday").

## Schema / data model changes

- `tasks.snoozed_until` DATE NULL, indexed.
- No new tables. Bulk edit reuses `TaskUpdateLog` for per-field audit and a
  `BulkEditAudit` row (optional — could piggyback on an existing
  bulk-shift audit pattern; decide during implementation).
- Schema upgrade adds the column idempotently.

## Code touch list (expected files)

- `tasktracker/db/models.py` — `snoozed_until`.
- `tasktracker/db/schema_upgrade.py` — column add.
- `tasktracker/services/task_service.py` — `snooze_task`,
  `wake_task`, `is_snoozed`.
- New service `tasktracker/services/bulk_edit_service.py` (mirror the
  `shift_service.py` pattern): `preview_bulk_edit(task_ids, plan)`,
  `apply_bulk_edit`, `undo_bulk_edit`.
- New dialog `tasktracker/ui/bulk_edit_dialog.py` + reuse of the
  existing preview-dialog pattern.
- `tasktracker/ui/main_window.py` — snooze and bulk-edit entries on the
  list context menu; respect snoozed-hidden default.
- `tests/test_snooze.py`, `tests/test_bulk_edit.py` (new).

## Work breakdown

- [ ] Schema upgrade for `snoozed_until` + index.
- [ ] Snooze / wake service methods + tests.
- [ ] Context-menu snooze actions.
- [ ] Task list default filter: hide snoozed (with a toggle to show).
- [ ] Auto-wake resurfaces tasks (query-level; nothing to do on timer other
      than refresh list on launch and when the user changes date).
- [ ] Bulk edit service modeled on shift service.
- [ ] Bulk edit dialog (field selector + per-field value inputs).
- [ ] Preview + Undo.
- [ ] Tests.

## Validation checklist

- [ ] Snoozing a task for 3 business days hides it from the default list
      until that date (confirm with a frozen clock in tests).
- [ ] On the wake date, the task reappears in the default list.
- [ ] Snoozed state is visible as a column / badge when the toggle is on.
- [ ] Bulk edit previews show exact before / after deltas and skip
      unchanged fields.
- [ ] Applying bulk edit produces per-task audit rows and a bulk summary.
- [ ] Undo reverses exactly the applied changes and nothing else.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — snooze semantics (hidden, not "deferred due
      date"), bulk edit undo model.
- [ ] `tasktracker/resources/user_guide.html` — new "Snooze" and
      "Bulk edit" subsections.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.
- [ ] `FEATURE_GUIDE.md` — snooze + bulk edit behavior.

## Risks / open questions

- **Snooze vs due date confusion.** Users may expect snooze to also push
  the due date. Keep them independent and call it out in the user guide.
- **Bulk edit scope creep.** Resist adding fields that belong in bulk shift
  (dates). Each field added requires a preview-rendering path.
- **Audit verbosity.** Large bulk edits generate many audit rows. Accept
  as the price of traceability; don't mute.

## Follow-ups discovered

_(empty at start of plan)_
