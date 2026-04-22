# Plan 06 - Tags and task dependencies

## Goal

Add two cross-cutting relational features that taxonomy and blockers cannot
cleanly express today:

1. **Free-form tags** — lightweight labels (e.g. `#q1-planning`,
   `#waiting-on-hr`) that can attach to any task, orthogonal to
   Category / Sub-category / Area.
2. **Task-to-task dependencies** — explicit "blocks" / "is blocked by"
   relationships, turning today's free-text blocker reasons into a proper
   graph.

## Problem it solves

- The structured taxonomy is great for routing work but bad at cross-cutting
  context. You need a way to say "this task, plus these three others, are all
  part of the Q1 staffing push" without inventing a fake area.
- `TaskBlocker` today captures **why** a task is blocked as free text. It
  cannot express "requisition approval (task T45) blocks offer letter (task
  T62)" in a way the UI can follow with a click.

## In scope

### Tags

- New `Tag` entity (name, slug, color hint).
- Many-to-many `task_tags` join table.
- Tag management in Settings (list, add, rename, delete, recolor, merge).
- Tag chips on the task panel (inline, compact) with add / remove controls.
- Tag filter in the Tasks tab search / filter bar.
- Tag-aware saved views (plan 01 must coexist cleanly).
- JSON export / import of tags matching the existing reference-data pattern.

### Task dependencies

- New `TaskDependency` entity: `blocker_task_id`, `blocked_task_id`, optional
  note.
- Dependencies panel on the task detail (small table of upstream and
  downstream links, inline or tab per layout preference).
- Cycle guard: creating a cycle raises a service-level error and surfaces as
  a `_notify`-style inline message.
- "Jump to" navigation from a dependency row to the linked task.
- Report / dashboard surface: a task whose upstream dependencies are not yet
  closed is marked visually (small badge / tooltip).

## Out of scope

- Automatic status propagation ("close me when all upstreams close"). Explicit
  only for now.
- Tags carrying semantics (no "priority tag", no "status tag" — tags stay
  free-form labels).
- Cross-vault tag syncing beyond JSON export / import.
- Dependency visualization as a full graph. Tabular view first; graph is a
  follow-up.

## Schema / data model changes

- `tags`:
  - `id`, `name` (unique), `slug` (unique lower-case), `color_hint`,
    `created_at`.
- `task_tags`:
  - `task_id` (FK CASCADE), `tag_id` (FK CASCADE), primary key (`task_id`,
    `tag_id`).
- `task_dependencies`:
  - `id`, `blocker_task_id` (FK CASCADE), `blocked_task_id` (FK CASCADE),
    `note` (TEXT NULL), `created_at`. Unique constraint on
    (`blocker_task_id`, `blocked_task_id`).
- Schema upgrade creates all three tables idempotently.

## Code touch list (expected files)

- `tasktracker/db/models.py` — `Tag`, `TaskDependency`, relationship wiring.
- `tasktracker/db/schema_upgrade.py` — create tables + join.
- `tasktracker/services/task_service.py` — tag CRUD, attach / detach,
  dependency CRUD, cycle check, list upstream / downstream.
- `tasktracker/services/reporting_service.py` — optional tag slice for
  throughput / workload reports (keep small; could be a follow-up).
- Main window filter bar / saved views store — add tag filter dimension.
- New dialog `tasktracker/ui/tags_dialog.py` — tag CRUD + merge.
- New widget `tasktracker/ui/dependencies_panel.py` — dependency table.
- `tests/test_tags.py`, `tests/test_dependencies.py` (new).

## Work breakdown

- [ ] Tag model + upgrade + service CRUD.
- [ ] Task-tag attach / detach service + tests.
- [ ] Tags dialog (Settings) with merge (one tag absorbs another's
      attachments).
- [ ] Tag chips on task panel with inline add / remove.
- [ ] Tag filter in the Tasks tab search bar.
- [ ] Dependency model + upgrade + service CRUD with cycle guard.
- [ ] Dependencies panel on task detail.
- [ ] Badge / tooltip on tasks blocked by open upstream deps.
- [ ] FTS integration (plan 02) sees task title + description; tags are
      filtered separately at SQL level. Keep search paths clean.
- [ ] JSON export / import for tags (match reference-data shape).
- [ ] Tests covering all above.

## Validation checklist

- [ ] Creating a cycle A->B->A raises the expected error and is not
      persisted.
- [ ] Deleting a task cascades to its `task_tags` and dependency rows.
- [ ] Merging tag A into B reassigns all `task_tags` rows from A to B without
      duplicates, then deletes A.
- [ ] Filtering by a tag returns exactly tasks holding that tag.
- [ ] "Blocked by open upstream" indicator flips when the upstream closes.
- [ ] JSON import is idempotent.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — tag model, dependency semantics, cycle policy.
- [ ] `tasktracker/resources/user_guide.html` — Tags section and Dependencies
      section.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.

## Risks / open questions

- **Tag proliferation.** Without discipline, tag lists grow unwieldy. The
  tags dialog should support merge + rename so cleanup is easy.
- **Dependency UX with big graphs.** Tabular view suffices initially; a
  graph view could follow.
- **Relationship with blockers.** `TaskBlocker` stays (captures external /
  human reasons); task dependencies capture internal gating. Document the
  difference in the user guide.
- **Search interplay with FTS (plan 02).** Tag filter is an AND on top of the
  FTS match; make sure SQL composes cleanly.

## Follow-ups discovered

_(empty at start of plan)_
