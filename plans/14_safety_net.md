# Plan 14 - Safety net (auto-save + crash recovery)

## Goal

Protect in-flight edits and accidental exits with two lightweight safety
nets:

1. **Auto-save drafts** for the task editor so unsaved content is never
   lost to a misclick, a Windows update, or a process crash.
2. **Crash recovery prompt** on startup when a draft from a prior session
   is detected, offering to restore, discard, or compare.

## Problem it solves

- The task editor today keeps changes only in memory. A tab switch without
  saving, an accidental Alt-F4, a power blip, a stuck save — any of those
  drop edits on the floor.
- The risk is low per-event but cumulative over months of daily use; the
  cost to fix is small.

## In scope

- Per-task draft file stored under `<vault>/app_data/drafts/<task_id>.json`
  (or `_new.json` for unsaved new tasks).
- Draft contents capture the editable surface: title, description, status,
  impact, urgency, dates, taxonomy, for-person, and inline edits to todos
  that the user has not yet saved.
- Auto-save writes the draft on a debounce (default 2 seconds of idle
  input) and on focus loss of the task editor.
- On successful save to DB, the draft file for that task is deleted.
- On startup, if any draft file exists, prompt the user with a list: per
  entry, choose **Restore draft**, **Discard draft**, or **Keep both** (saves
  the restored content as a note on the task for comparison).
- For "new task" drafts (never saved), restore opens a new task form with
  the draft loaded; discard deletes the draft.

## Out of scope

- Auto-save for other surfaces (notes dialog, todo dialog). Those are
  short-lived modals; if there is real pain, add in a follow-up.
- Cross-machine draft sync.
- Version history beyond "one current draft per task".
- Encrypted drafts. Drafts live under `app_data/drafts/` inside the vault,
  so they inherit vault-level at-rest protection (see risks).

## Schema / data model changes

None. Drafts are JSON files alongside `ui_settings.json`.

## Code touch list (expected files)

- New module `tasktracker/ui/task_draft_store.py` — `save_draft`,
  `load_draft`, `clear_draft`, `list_drafts`.
- `tasktracker/ui/main_window.py` — startup recovery prompt, hook into
  task-editor's change signals for debounced auto-save, clear draft on
  save success.
- `tasktracker/ui/settings_store.py` — small `drafts` section (enabled,
  debounce_ms).
- `tests/test_drafts.py` (new) — round-trip, stale-draft detection,
  recovery flow.

## Work breakdown

- [ ] Decide on the draft schema (JSON shape, forward-compatible via a
      `version` key).
- [ ] Implement the draft store.
- [ ] Wire change signals from the task editor to a debounced writer.
- [ ] Clear draft on successful DB save.
- [ ] Startup recovery: detect drafts, prompt, act on user choice.
- [ ] "Keep both" path: apply draft contents in-editor; offer an inline
      "Compare to saved version" reveal.
- [ ] Settings toggle and debounce slider.
- [ ] Tests: write draft, simulate crash, restart, prompt appears,
      restore yields identical in-memory state.

## Validation checklist

- [ ] Typing into the title field, waiting 2 seconds, and killing the
      process produces a `<task_id>.json` draft under
      `<vault>/app_data/drafts/`.
- [ ] Next startup shows the recovery prompt; Restore yields the typed
      title in the editor without touching the DB until the user hits
      Save.
- [ ] Discard deletes the draft file and it does not reappear on next
      launch.
- [ ] "Keep both" saves the draft content as a note on the task so the
      user can reconcile later.
- [ ] Normal save path clears the corresponding draft.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — draft storage decision, forward-compatibility
      strategy, at-rest protection.
- [ ] `tasktracker/resources/user_guide.html` — brief "Auto-save and
      recovery" section.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.
- [ ] `FEATURE_GUIDE.md` — auto-save / recovery behavior.

## Risks / open questions

- **Drafts while vault is closed.** Drafts written during a session live
  inside the vault folder. When the vault re-encrypts on shutdown, they
  must be swept into the encrypted payload or explicitly excluded. Decide
  during implementation; sweeping in is simpler and keeps at-rest
  protection intact.
- **Stale drafts forever.** If the user deletes the underlying task
  externally, a draft may linger. Startup should skip / delete drafts
  whose task id no longer exists (with a one-line notice).
- **Debounce tuning.** 2 seconds is a starting point; user-configurable so
  fast typists can shorten it without surprise.

## Follow-ups discovered

_(empty at start of plan)_
