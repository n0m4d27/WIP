# Plan 05-02: Task and Todo Resolution Fields

## Goal
Introduce task-level and todo-level resolution fields as quick-reference closure notes, and require a task resolution whenever a task is closed from any wired close path.

## Scope
- Add `resolution` to `tasks` and `todo_items` data models.
- Migrate existing vaults safely with additive startup schema upgrades.
- Enforce required task resolution on close from:
  - Tasks tab save flow (status transition to Closed)
  - Tasks tab Close Task action / shortcut
  - Calendar quick-edit close flow
- Support todo resolution capture/edit and require resolution when marking todos done.

## Implementation summary
1. Extend schema + ORM models with nullable text `resolution` columns.
2. Extend `TaskService` methods (`create_task`, `update_task_fields`, `close_task`, `add_todo`, `update_todo`, `complete_todo`) to read/write resolution and validate close requirements.
3. Add task Resolution editor to core task detail UI and wire load/save behavior.
4. Add close-time resolution prompting/validation in all close entry points.
5. Extend todo dialogs and task/calendar todo views to expose resolution.
6. Update docs (`user_guide.html`, `FEATURE_GUIDE.md`) and tests for required-close and todo-resolution persistence.

## Validation checklist
- Closing a task without resolution is blocked in all close flows.
- Closing with resolution succeeds and persists note.
- Marking todo done requires or reuses a resolution.
- Existing vaults upgrade without destructive migration.
