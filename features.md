# Features

## Must-Have Features (MVP)

### 1) Task Lifecycle Management
- Create, view, edit, close tasks.
- Required task dates:
  - received date
  - expected delivery (due) date
  - closed date
- Task status flow: `open -> in_progress -> blocked -> closed`.

### 2) Overarching Task-Centric Data Model
- Every artifact is attached to a parent task:
  - notes
  - todo items
  - blockers
  - update logs

### 3) Recurring Task Automation
- Define recurrence rule on eligible tasks.
- Auto-generate next task iteration based on interval.
- Preserve closed previous iteration with immutable closure timestamp.

### 4) Notes Timeline
- Add timestamped notes per task.
- Render notes in strict chronological order.
- Provide "combined narrative" view to read full task history end-to-end.

### 5) Task Todo and Milestone Logic
- Add todo items under a task.
- Each todo can include a milestone date.
- Task computes nearest upcoming milestone from open todos for prioritization/sorting.

### 6) Calendar View
- Month/week/day calendar views.
- Visualize task due dates and todo milestone dates.
- Filter by status (open/blocked/closed), recurring/non-recurring, and owner/category.

## Nice-to-Have Features (Post-MVP)
- Templates for common task types.
- Bulk update actions.
- Dependency mapping between tasks.
- Reminder notifications for nearing due/milestone dates.
- Simple performance tracking linked to APR reference data.

## Derived from Access Relationships
Feature scoping aligns to these relationship anchors:
- `Task` to many `Notes`
- `Task` to many `Todo`
- `Task` to many `Blockers`
- `Task` to many `Updates`
- `Task` linked with recurring definition (`RecurringTasks`)

`Performance` and `APR` are treated as optional modules to activate once core task flow is stable.
