# Plan 11 - Reminders and aging

## Goal

Surface attention-worthy tasks before they fall off the user's radar:

1. **OS-level reminders** (Windows toast notifications) when a task's due
   date or next-milestone date arrives and the app is closed or minimized.
2. **Aging indicators** in the Tasks list that auto-highlight items stuck in
   `open` beyond a threshold of business days.

## Problem it solves

- Reminders currently require opening the app. Tasks with a due date at the
  end of the day can slip because nothing nudges the user.
- Aging signals are absent. An item that quietly sat in `open` for three
  weeks looks identical to one received today.

## In scope

### Reminders

- A new background timer inside the app (singleton `QTimer`) that on a
  configurable cadence (default every 15 minutes) checks for tasks whose
  `due_date` or `next_milestone_date` is today or overdue and whose last
  reminder fire was not today.
- Windows toast via `win11toast` or `winotify` (pick one; stay
  dependency-light). Linux / Mac fallbacks: tray balloon from plan 05 if
  available, otherwise skip (app targets Windows per tech decisions).
- Clicking a toast opens the main window with the task preselected.
- Per-task "Remind me at..." control for ad-hoc, time-of-day reminders on
  today's date.
- Settings: enable / disable reminders, cadence, quiet hours (e.g. 18:00 to
  08:00 don't fire), include snoozed (plan 10) default off.

### Aging indicators

- New service helper `aging_bucket(task) -> AgingLevel` returning one of
  `fresh`, `warm`, `stale`, `stuck` based on business days since received,
  configurable thresholds (defaults: warm >=5, stale >=10, stuck >=20).
- Visible as a small color chip / icon in the task list.
- Dashboard (plan 01) gets an "Aging" card summarizing stuck counts.
- Parent rollup (plan 07) uses the oldest child's aging bucket.

## Out of scope

- Email or Teams-channel reminders.
- Snooze-a-reminder UI (different from snoozing the task, which plan 10
  covers).
- Per-person aging policies. One set of thresholds per vault.
- Auto status change based on aging (e.g. auto-move to "at risk" — intrusive,
  skipped intentionally).

## Schema / data model changes

- `tasks.last_reminded_on` DATE NULL (idempotency key so we fire at most
  once per day per task).
- Schema upgrade adds the column idempotently.
- `ui_settings.json` gains a `reminders` section (enabled, cadence_minutes,
  quiet_start, quiet_end, include_snoozed).
- Aging thresholds live in `ui_settings.json` too (`aging.warm`,
  `aging.stale`, `aging.stuck`).

## Code touch list (expected files)

- `tasktracker/db/models.py` — `last_reminded_on` column.
- `tasktracker/db/schema_upgrade.py` — column add.
- New module `tasktracker/services/reminder_service.py` — polling loop and
  "what should fire now" query.
- New module `tasktracker/notifications/windows_toast.py` — thin wrapper
  around the chosen toast library (keeps the dependency surface small and
  testable).
- `tasktracker/services/task_service.py` — `aging_bucket(task)` and list
  helpers.
- `tasktracker/ui/main_window.py` — aging chip in the list, Dashboard
  aging card, per-task "Remind me at..." control, settings wiring.
- `tasktracker/ui/settings_store.py` — reminders and aging sections.
- `tests/test_reminders.py` and `tests/test_aging.py` (new) — clock-frozen
  tests.

## Work breakdown

- [ ] Schema upgrade for `last_reminded_on`.
- [ ] Settings shape + persistence.
- [ ] `ReminderService` with a pure "what would fire at time T" function for
      unit testability.
- [ ] Toast wrapper (OS-specific; fall back to no-op if library missing).
- [ ] QTimer wiring in main window lifecycle.
- [ ] Per-task "Remind me at..." control.
- [ ] Aging bucket function + list chip.
- [ ] Dashboard aging card (depends on plan 01).
- [ ] Parent rollup of aging (depends on plan 07).
- [ ] Tests with frozen clocks.

## Validation checklist

- [ ] A task due today triggers exactly one toast on the next poll after
      08:00 local time, not again until tomorrow.
- [ ] Quiet hours suppress toasts; the last_reminded_on date is not updated
      during quiet hours.
- [ ] Clicking a toast brings the main window forward with the correct task
      selected.
- [ ] Aging chips match expected bucket transitions with a frozen clock.
- [ ] Dashboard aging card matches the service's count exactly.
- [ ] With a parent-of-children (plan 07), the parent inherits the worst
      child's aging bucket.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — toast library choice, quiet-hours rule,
      aging thresholds and their configurability.
- [ ] `tasktracker/resources/user_guide.html` — "Reminders" and
      "Aging indicators" sections.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.

## Risks / open questions

- **Notification library churn.** The Windows toast ecosystem has seen
  several Python libraries come and go. Prefer the smallest stable option;
  isolate behind the wrapper so swaps are cheap.
- **Corporate antivirus.** Same concern as the global hotkey in plan 05;
  toast libraries that use COM / WinRT are generally fine, but verify.
- **Dependency order.** Dashboard aging card lands best after plan 01;
  parent rollup lands best after plan 07. If those are pending, ship the
  in-list chip first and add the card / rollup in follow-ups.

## Follow-ups discovered

_(empty at start of plan)_
