# Plan 06-01: Searchable Blocked-By Task Picker

## Goal
Improve dependency creation UX by replacing the current static picker with a searchable selector that excludes closed tasks by default, making blocker selection workable at larger task volumes.

## Current behavior and gap
- Dependency add currently uses a plain `QInputDialog.getItem(...)` with prebuilt labels in [`tasktracker/ui/main_window.py`](../tasktracker/ui/main_window.py), which does not scale for 50+ tasks.
- Candidate list is currently sourced from `list_tasks(include_closed=True)` and only excludes the current task id, so closed items are mixed into the picker.
- Dependencies panel shell is already present in [`tasktracker/ui/dependencies_panel.py`](../tasktracker/ui/dependencies_panel.py).

## Implementation approach
1. Add a dedicated dependency-picker dialog (new file) instead of `QInputDialog`:
   - Search box (`QLineEdit`) with incremental filtering.
   - Results list (`QListWidget`) showing `ticket + title + status`.
   - Match count / empty-state text.
2. Candidate source rules:
   - Use service list with `include_closed=False`.
   - Exclude current task.
   - Exclude already-linked upstream blockers to reduce duplicates in UI.
3. Matching behavior:
   - Case-insensitive substring on title and ticket text (`T123`, `123`), with optional status matching.
4. Wire MainWindow dependency-add flow:
   - Replace existing `_add_dependency_from_panel` picker path with the new dialog.
   - Keep note prompt behavior after task selection.
5. Keep cycle and duplicate safety in service layer unchanged.

## Verification plan
1. With <=15 open tasks, opening add-dependency shows manageable default list and selection works.
2. With many tasks (50+), typing partial title or ticket quickly narrows to expected rows.
3. Closed tasks are absent from picker by default.
4. Existing cycle guard still blocks invalid links.
5. Existing duplicate dependency handling remains correct.
6. Regression: dependency add/remove/jump in panel still works.
