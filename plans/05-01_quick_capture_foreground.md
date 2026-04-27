# Plan 05-01: Quick Capture Create-and-Open Foreground Reliability

## Goal
Ensure **Create and open** from quick capture consistently brings Task Tracker to the foreground and selects the new task, even when the window is minimized, hidden to tray, or behind other apps.

## Current behavior and gap
- Quick capture already calls `open_task_on_tasks_tab(task_id)` when `open_after=True` in [`tasktracker/ui/quick_capture_integration.py`](../tasktracker/ui/quick_capture_integration.py).
- `open_task_on_tasks_tab()` currently does only `show()`, `raise_()`, `activateWindow()` in [`tasktracker/ui/main_window.py`](../tasktracker/ui/main_window.py), which is not always sufficient on Windows due to foreground restrictions and window-state timing.
- Global hotkey events arrive through Win32 native handling in [`tasktracker/ui/win_hotkey.py`](../tasktracker/ui/win_hotkey.py), so the fix should leverage Windows context without changing capture semantics.

## Implementation approach
1. Add a dedicated **window presentation helper** in `MainWindow` that is stronger than raw `show/raise/activate`:
   - If minimized, explicitly restore (`showNormal()` / clear minimized flag) before activation.
   - Ensure visible if hidden-to-tray (`show()`).
   - Raise and request focus (`raise_()`, `activateWindow()`, `setFocus(...)`).
   - On Windows, include a best-effort native foreground nudge after Qt calls (via Win32 APIs), guarded and no-op on other platforms.
2. Route `open_task_on_tasks_tab()` through this helper so all quick-capture open flows use one hardened path.
3. Reuse the same helper in quick-capture tray **Open Task Tracker** action path to keep behavior consistent.
4. Keep existing selection/filter behavior unchanged (still notify when task is filtered out).

## Windows-specific foreground hardening
- Implement a small utility in [`tasktracker/ui/main_window.py`](../tasktracker/ui/main_window.py) (or a tiny adjacent helper module if preferred) that:
  - Runs only on `sys.platform == "win32"`.
  - Retrieves HWND from Qt window handle (`winId`) and calls a safe best-effort sequence (`ShowWindow`/`SetForegroundWindow` style).
  - Wraps all ctypes calls in exception-safe guards so failures never break UX.
- Avoid changing global hotkey registration logic unless needed; keep the fix localized to presentation/activation.

## Verification plan
1. Manual matrix on Windows:
   - Main window visible but behind another app.
   - Main window minimized.
   - Main window hidden to tray (keep-running enabled).
   - Trigger quick capture via tray and global hotkey; choose **Create and open**.
2. Confirm expected outcomes:
   - Main window becomes visible and foregrounded.
   - Tasks tab opens and new task is selected when visible by filters.
   - If filtered out, existing notification appears.
3. Regression checks:
   - Plain **Create** still does not steal focus.
   - Tray **Open Task Tracker** still works.
   - Close/quit/tray lifecycle behavior remains unchanged.

## Docs to update on landing
- [`tasktracker/resources/user_guide.html`](../tasktracker/resources/user_guide.html) (quick capture wording if guarantee language is tightened).
- [`FEATURE_GUIDE.md`](../FEATURE_GUIDE.md) (foreground behavior note if semantics are refined).
