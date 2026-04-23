# Plan 03 - Task templates

## Goal

Let the user define reusable one-off task templates ("new headcount request",
"new monthly WFM refresh") that prefill title pattern, taxonomy, default
priority, description scaffolding, and a seed set of todos. Creating a new
task from a template becomes a single click instead of a dozen.

## Problem it solves

- Several task shapes repeat weekly or monthly (intake, approvals, QA pass,
  hand-off). Typing them from scratch is time you do not have on a Monday
  morning.
- The recurring-rule system (`RecurringRule` + `RecurringTodoTemplate`) already
  proves the template idea, but it only fires on close of a specific task.
  There is no path for "give me a fresh instance of shape X" without tying it
  to a recurring cadence.

## In scope

- New `TaskTemplate` entity with: name, optional description pattern, default
  title pattern (with simple placeholders like `{today}`, `{week}`), default
  area, default for-person, default impact / urgency (priority derives), and
  default status (likely `open`).
- New `TaskTemplateTodo` child rows: title, sort order, optional milestone
  offset in business days from task creation (mirror the recurring shape).
- Templates managed via Settings (a new "Task templates..." dialog, sibling of
  the existing reference-data dialog).
- "New task from template..." toolbar / menu action that offers a searchable
  list of templates, applies the chosen template, and opens the new task in
  edit state (not yet saved to DB, unless the user hits Save).
- Import / export of templates as JSON (match the pattern used for taxonomy
  and people).

## Out of scope

- Cross-vault template syncing beyond the manual JSON export / import.
- Templating for notes / blockers / attachments (only task fields + todos).
- Conditional templates ("if area = X, prefill Y"). Kept simple.
- Shared templates between users (single-user product).

## Schema / data model changes

- `task_templates` table:
  - `id`, `name` (unique), `title_pattern`, `description_pattern` (TEXT),
    `default_area_id` (FK SET NULL), `default_person_id` (FK SET NULL),
    `default_impact`, `default_urgency`, `default_status`, `sort_order`,
    `created_at`, `updated_at`.
- `task_template_todos` table:
  - `id`, `template_id` (FK CASCADE), `sort_order`, `title`,
    `milestone_offset_days` (INT NULL, business days).
- `schema_upgrade.py` creates both tables idempotently.

## Code touch list (expected files)

- `tasktracker/db/models.py` — new models.
- `tasktracker/db/schema_upgrade.py` — create tables.
- `tasktracker/services/task_service.py` — `list_templates`, `create_template`,
  `update_template`, `delete_template`, `apply_template(template_id) -> Task`
  (creates the task + todos atomically; computes milestone dates via
  `shift_business_days`).
- New dialog `tasktracker/ui/task_template_dialog.py` — list + CRUD UI.
- `tasktracker/ui/main_window.py` — "New task from template..." action and the
  settings menu entry.
- `tests/test_task_templates.py` (new) — CRUD, apply, JSON round-trip.

## Work breakdown

- [x] Define models + upgrade step.
- [x] Implement service methods (CRUD + apply).
- [x] Build Task templates dialog (list, add, edit, delete, reorder, import,
      export).
- [x] Add "New task from template..." action with a simple picker.
- [x] Placeholder expansion for title pattern (`{today}`, `{yyyy}`, `{mm}`,
      `{dd}`, `{week}`) — keep the list tiny; expand later if needed.
- [x] Business-day offset support for todos (reuse `shift_business_days`).
- [x] JSON export / import using the existing reference-data pattern.
- [x] Tests: CRUD, apply produces expected task shape, placeholders expand,
      JSON round-trip, corrupt import handled gracefully.

## Validation checklist

- [x] Creating a template with two todos and applying it yields one task + two
      todos with correct sort order and milestone dates.
- [x] Deleting the default area or person on a template safely nulls the
      reference (no crash when applying).
- [x] Placeholders expand against the task's received date, not literal
      strings.
- [x] JSON import is idempotent (re-import of the same file does not duplicate
      templates; matches by `name`).
- [x] Existing test suite green.

## Docs to update on landing

- [x] `tech_decisions.md` — note the template model, placeholder grammar, and
      how it differs from `RecurringRule`.
- [x] `tasktracker/resources/user_guide.html` — new "Task templates" section
      under Settings + mention in New task flow.
- [x] `plans/README.md` — mark Done, log follow-ups / bugs.

## Risks / open questions

- **Placeholder sprawl.** Ship with the smallest useful set and treat new
  placeholders as follow-ups.
- **Interaction with `RecurringRule`.** These are separate features; a task
  spawned from a template can still have a recurring rule attached afterwards.
  Document explicitly to avoid user confusion.
- **What happens if the template's default area is deleted later?** Apply
  gracefully falls back to no area; no hard FK failure.

## Follow-ups discovered

_(empty at start of plan)_
