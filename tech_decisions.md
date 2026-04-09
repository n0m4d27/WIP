# Technical Decisions (Initial)

## Runtime and Language
- Python version: **3.11.2** (required).
- Project style: typed Python (`typing`, `dataclasses`/Pydantic models as needed).

## Architecture Direction
- Start with a modular monolith for speed and maintainability.
- Separate layers:
  - domain models (task, todo, notes, recurrence)
  - application services (task lifecycle, recurring generation, calendar queries)
  - persistence layer (database repositories)
  - UI/API layer

## Backend Interface
- Preferred backend framework: **FastAPI** for API-first design and future UI/mobile flexibility.
- Alternative acceptable path: server-rendered app with Flask + HTMX (if simplicity is prioritized).

## Database
- Initial database: **SQLite** for local-first development and easy setup.
- ORM: **SQLAlchemy 2.x**.
- Migration tool: **Alembic**.
- Target upgrade path: PostgreSQL with minimal model changes.

## Preliminary Data Model Decisions
Based on Access relationship structure, preserve these cardinalities:
- One `Task` -> many `TaskNote`
- One `Task` -> many `TodoItem`
- One `Task` -> many `TaskBlocker`
- One `Task` -> many `TaskUpdateLog`
- One `Task` -> zero/one `RecurringRule` (or one rule -> many generated tasks)

Field names from Access are inputs only; schema will use Pythonic consistency:
- snake_case columns
- explicit datetime vs date semantics
- strong foreign keys and indexes on date/status fields for calendar and queue views

## Recurrence Engine Decision
- Implement deterministic recurrence generation in service layer:
  - close task
  - detect recurrence rule
  - create next task with computed dates
  - log automation event
- Use explicit transaction to avoid duplicate generation.

## Date and Time Strategy
- Store timestamps in UTC.
- Store date-only fields for `received_date`, `due_date`, `closed_date` where time-of-day is not needed.
- Store `created_at` for notes/todos/updates with timezone-aware datetime.

## Calendar Strategy
- Calendar queries derive from:
  - task due dates
  - todo milestone dates
- "Next milestone" is computed from nearest open todo milestone.
- Provide indexed query path for upcoming 7/14/30 day windows.

## Testing Strategy
- Pytest.
- Unit tests for recurrence rules and milestone derivation.
- Integration tests for task close + auto-generation transaction.
- API tests for core CRUD and calendar endpoints.

## Deferred Decisions
- Authentication/authorization model.
- Notification delivery channel (email/Teams/etc.).
- Web frontend stack (server rendered vs separate SPA).
