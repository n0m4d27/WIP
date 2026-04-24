# Plan 05 - Quick capture

## Goal

Ship a zero-friction capture surface — a system tray icon plus a global
hotkey — that opens a minimal dialog for creating a task with only a title
(and optional priority / area / for-person) without bringing the full main
window into focus.

## Problem it solves

- The biggest "things getting lost" vector is the 10 seconds between someone
  saying "can you pull X" and having the cognitive room to record it. Today
  that requires: alt-tab to main window, find the Tasks tab, click New task,
  fill out the form, tab back to the meeting. That friction is where items
  leak.
- Quick capture shrinks the intake loop to "hotkey, type title, enter".

## In scope

- System tray icon with context menu: Quick capture, Open main window, Exit.
- Global hotkey (default `Ctrl+Shift+T`, user-configurable) that opens the
  quick-capture dialog from anywhere.
- Minimal dialog: single-line title, optional priority (I / U dropdowns),
  optional area, optional for-person, optional one-line description, "Create"
  / "Create and open" buttons.
- Dialog autofocuses the title field, submits on Enter, dismisses on Escape.
- Created task uses today as received date; received-date override available
  via a small "More..." expander.
- Notification (status bar on main window if open, otherwise a tray balloon)
  confirms creation with the new ticket number.
- Respects vault state: if no vault is unlocked, the dialog offers to open
  the vault picker instead of silently failing.

## Out of scope

- Capturing from outside sources (email, Outlook COM) — plan 13 covers that.
- Offline queuing or batched capture. Each capture commits to the DB
  immediately.
- Full rich-text description in the quick dialog.
- Multiple hotkeys or per-template hotkeys.

## Schema / data model changes

None. The dialog calls the existing `TaskService.create_task` with minimal
fields.

## Code touch list (expected files)

- New module `tasktracker/ui/quick_capture.py` — dialog widget.
- New module `tasktracker/ui/tray.py` — system tray icon lifecycle.
- `tasktracker/__main__.py` — instantiate tray icon, register global hotkey,
  keep app alive when main window is closed (if tray stays visible) or exit
  with the window (configurable).
- `tasktracker/ui/settings_store.py` — new `quick_capture` section:
  `hotkey`, `keep_running_in_tray`, default I / U, default area, default
  for-person.
- `tasktracker/ui/keyboard_shortcuts_dialog.py` — add the hotkey row.
- `tests/test_quick_capture.py` (new) — service-level test (create task with
  minimal inputs) + settings round-trip. Global-hotkey binding is skipped in
  offscreen tests.

## Work breakdown

- [x] Pick a global-hotkey library (PySide6's `QKeySequence` alone is in-app
      only; a global hotkey needs a Windows-native helper — evaluate
      `pynput`, `keyboard`, or `qhotkey` bindings. Stay dependency-light).
- [x] Implement tray icon with menu and single-click action (configurable).
- [x] Build the quick-capture dialog.
- [x] Wire global hotkey to show dialog.
- [x] Settings store additions + keyboard-shortcuts dialog wiring.
- [x] Decide behavior when main window is closed: keep running in tray? Opt-in
      setting, default off, to avoid surprises.
- [x] Handle the "no vault unlocked" case gracefully.
- [x] Tests + offscreen smoke.

## Validation checklist

- [x] Hotkey opens the dialog instantly with title field focused.
- [x] Enter submits, dialog closes, task exists in DB with today's received
      date and the chosen priority.
- [x] Tray icon context menu entries work.
- [x] Escape dismisses without creating anything.
- [x] If vault is locked, dialog offers to unlock rather than erroring.
      _(Shipped behavior: tray + hotkey are registered only after a successful
      vault unlock in startup; there is no capture path while the vault is
      locked.)_
- [x] Changing the hotkey in Keyboard shortcuts dialog takes effect
      immediately.
- [x] Closing main window with "keep running in tray" on keeps the tray and
      hotkey alive; with it off, exits the app.
- [x] Existing test suite green.

## Docs to update on landing

- [x] `tech_decisions.md` — rationale for global hotkey library choice and
      tray lifecycle semantics.
- [x] `tasktracker/resources/user_guide.html` — new "Quick capture" section.
- [x] `plans/README.md` — mark Done, log follow-ups / bugs.
- [x] `FEATURE_GUIDE.md` — quick capture entry points and behavior.

## Risks / open questions

- **Global hotkey library dependency.** Some options pull in native hooks or
  admin rights. Evaluate footprint during step 1.
- **Windows focus-stealing rules.** A global hotkey that pops a dialog over a
  Teams call needs to be well-behaved (no focus steal until user actually
  types). Test during validation.
- **Encrypted vault closed.** Quick capture can't write without an unlocked
  vault; UX must be clear, not a silent no-op.
- **Corporate antivirus.** Global-hotkey libraries that inject into other
  processes can trip EDR. Document which library was chosen and why.

## Follow-ups discovered

- Optional UX: global hotkey while the app is not running could show vault
  login first (not implemented; today capture exists only after unlock).
