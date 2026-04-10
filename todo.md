# Build TODO

## Phase 0 - Foundation
- [ ] Confirm product decisions in `questions.md`.
- [ ] Finalize MVP scope and explicitly defer non-MVP features.
- [ ] Create Python 3.11.2 virtual environment and dependency baseline.
- [ ] Initialize project structure (app, domain, services, db, tests).

## Phase 1 - Data Model and Persistence
- [ ] Design SQLAlchemy models for:
  - Task
  - RecurringRule
  - TodoItem
  - TaskNote
  - TaskBlocker
  - TaskUpdateLog
- [ ] Implement relationships based on Access diagram as baseline.
- [ ] Add migrations with Alembic.
- [ ] Seed sample data for task, todo, notes, recurrence.

## Phase 2 - Core Services
- [ ] Implement task CRUD service.
- [ ] Implement task close flow with `closed_date`.
- [ ] Implement recurring generation service (create next iteration automatically).
- [ ] Implement todo milestone derivation (`next_milestone_date` on task).
- [ ] Implement notes timeline + combined audit/activity query (service layer).

## Phase 3 - Desktop UI
- [ ] Wire UI to services (tasks, todos, notes, recurrence, calendar) — no HTTP server.
- [ ] Build task detail view with:
  - lifecycle fields
  - notes timeline
  - todo list and milestones
- [ ] Build calendar (month default; week + agenda); drag-and-drop date changes (MVP1).
- [ ] Add filtering and sorting by next milestone.
- [ ] Reports: overdue, due this week, closure velocity; CSV and Excel export (MVP1).

## Phase 4 - Quality and Release Readiness
- [ ] Add unit tests for recurrence and milestone logic.
- [ ] Add integration tests for task close -> next task generation.
- [ ] Add integration tests for core services (and UI adapters where practical).
- [ ] Add basic logging and error handling.
- [ ] Prepare first usable internal release.

## Immediate Next 5 Actions
- [ ] Resolve all open questions that block schema finalization.
- [ ] Create initial SQLAlchemy ERD from current relationship assumptions.
- [ ] Implement database schema migration 001.
- [ ] Build task creation and task close flows in UI + services first.
- [ ] Validate recurring automation with test fixtures.
