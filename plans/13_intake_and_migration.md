# Plan 13 - Intake and migration

## Goal

Two related intake paths that reduce manual task entry:

1. **Outlook email drop** — a watched folder where `.msg` files dropped by
   the user auto-create tasks, with the email subject as the title, body as
   description, and attachments lifted into the task's attachments (plan 04).
2. **CSV import** — a mapper UI that ingests a CSV and creates tasks, used
   both for a one-shot migration from the legacy Access DB and for bulk
   ingests from HR / WFM spreadsheets.

## Problem it solves

- "A lot of manual movement" is the stated pain. Both of these paths attack
  the intake side: email-based requests become tasks with a drag, and rows
  in a spreadsheet become tasks with a mapper.
- Without a CSV path, migrating from the current Access DB is effectively a
  manual retype.

## In scope

### Outlook email drop

- User configures one watched folder in Settings (default
  `<vault>/inbox_drop/`). Any `.msg` file dropped there is processed:
  - Subject -> task title.
  - Body (plain text + rich text) -> task description.
  - Received time -> task `received_date`.
  - Sender / recipients captured in a note on the new task.
  - Attachments from the email become `TaskAttachment` rows (depends on
    plan 04). If plan 04 has not landed, attachments are dropped with a
    warning logged into the task's description.
  - The original `.msg` is moved to a `processed/` subfolder with a date
    prefix for audit.
- On ingest error, the file moves to `failed/` with an accompanying `.log`
  explaining why.
- Polling cadence configurable (default every 30 seconds while the main
  window is visible; paused when minimized).
- A "Run intake now" action triggers immediate processing.

### CSV import

- A new "File -> Import tasks from CSV..." dialog:
  - File picker, then preview of the first N rows.
  - Column-mapping UI: each task field on the left, CSV column on the
    right, with coercion hints (date parse, number parse).
  - Dry-run view showing "would create N tasks, M skipped because of
    missing title / bad date".
  - One-click commit.
- Defaults: if a column named `title` / `subject` exists, map it
  automatically. Same for `due_date`, `received_date`, `category`, `area`,
  `for_person`.
- Deduplication: optional "skip rows whose title already exists as an open
  task" checkbox.
- Produces a summary dialog (created / skipped / errored) and an exportable
  log.

## Out of scope

- Live IMAP / Exchange integration. Watched folder only.
- Write-back to Outlook (mark the original email as handled in Outlook).
- Continuous sync with an external system. All intake is pull-style.
- Two-way CSV round-trip with updates. Import creates; updates are manual.

## Schema / data model changes

- None strictly required for CSV import.
- For Outlook drop, an `IntakeLogEntry` table is optional for audit:
  `id`, `source` (`email` / `csv`), `raw_filename`, `status`
  (`created` / `skipped` / `errored`), `task_id` FK NULL, `message`,
  `created_at`.
- Schema upgrade creates the table idempotently if we keep it.

## Code touch list (expected files)

- New module `tasktracker/services/intake_service.py` — shared parsing and
  creation paths for both sources.
- New module `tasktracker/services/email_drop_watcher.py` — directory-watch
  loop with pause / resume.
- `.msg` parsing: evaluate `extract-msg` (the pragmatic choice on Windows);
  keep parsing behind a helper so swaps are cheap.
- New dialog `tasktracker/ui/csv_import_dialog.py`.
- `tasktracker/ui/main_window.py` — File menu entry and the intake
  settings.
- `tasktracker/ui/settings_store.py` — intake section (drop folder, poll
  cadence, enabled flag).
- `tests/test_intake_csv.py` and `tests/test_intake_email.py` (new).

## Work breakdown

- [ ] Shared intake service that given a normalized payload creates a task
      + notes + attachments.
- [ ] CSV mapper dialog with dry-run.
- [ ] CSV import commits + summary.
- [ ] Email drop watcher with pause / resume and run-now action.
- [ ] `.msg` parsing: subject, body, received, sender, recipients,
      attachments.
- [ ] File-moves to `processed/` and `failed/` with logs.
- [ ] Optional intake audit table.
- [ ] Tests with fixtures (a small real-ish `.msg` sample and a CSV sample).

## Validation checklist

- [ ] Dropping a test `.msg` into the watched folder produces a task whose
      title, description, received date, sender note, and attachments all
      match the email.
- [ ] A corrupt `.msg` moves to `failed/` with a log explaining why.
- [ ] CSV dry-run shows correct created / skipped counts before commit.
- [ ] CSV with bad date strings produces a coercion error row rather than
      a crash.
- [ ] Deduplicate option skips rows whose title matches an existing open
      task.
- [ ] Pausing the watcher stops intake; resuming picks up where it left
      off.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — intake architecture, parser choice, audit
      position.
- [ ] `tasktracker/resources/user_guide.html` — "Intake" section covering
      both CSV and email drop.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.
- [ ] `FEATURE_GUIDE.md` — intake / migration workflows.

## Risks / open questions

- **`.msg` parser dependency.** `extract-msg` is the pragmatic option but
  is a real dependency with native baggage in some environments. Isolate
  behind a helper to allow swap-out.
- **Attachment inflation.** Emails with large attachments quickly grow the
  vault. Honor plan 04's size warnings here.
- **Access migration shape.** The CSV mapper covers the 80% case for Access
  migration; the remaining 20% (notes, history) likely needs a bespoke
  exporter from Access. Treat as a follow-up if needed, fed by
  `access_workflow_capture.md`.
- **Polling on NAS.** A NAS-backed drop folder adds latency to the poll
  loop; a 30-second default cadence is deliberately conservative.

## Follow-ups discovered

_(empty at start of plan)_
