# WIP - Task Tracker Desktop App

Task Tracker is a local-first desktop application for managing operational work with a ServiceNow-style workflow, but without a browser or web server.  
It is built for a single user who needs clear task ownership, traceable changes, recurring work support, and practical planning tools (todos, notes, calendar, reports) in one native UI.

The app is intentionally designed around:
- **Desktop-first operation:** native PySide6 interface, no HTTP service.
- **Single-file local data model:** SQLite inside a vault folder.
- **Security at rest:** password-gated vault with encrypted database when closed.
- **Operational clarity:** status + impact/urgency/priority, milestones, blockers, and combined activity timeline.

## Main Features

- **Task lifecycle management**
  - Track `received`, `due`, and `closed` dates.
  - Statuses include: open, in progress, blocked, on hold, cancelled, closed.
  - ServiceNow-style priority from impact and urgency (P1-P5).
  - Unique ticket numbers formatted like `T0`, `T1`, `T2`, ...

- **Structured task execution**
  - Ordered todo list per task, with milestone dates.
  - Next milestone auto-derived from the first open dated todo.
  - Blockers tracked separately and clearable independently.
  - Optional task attribution fields for taxonomy and assignee target.

- **Taxonomy and people master data (per vault)**
  - Custom **Category -> Sub-category -> Area** hierarchy.
  - Per-task area selection (with category/sub-category context).
  - Per-task **For person** selection from people entries (first, last, employee ID).
  - Settings tools to manage this reference data and keep it vault-specific.
  - JSON export/import to sync category/person reference data across vaults.

- **Notes, history, and activity**
  - Rich-text notes with editable user notes and version history.
  - Field-level audit trail for task changes.
  - Combined activity panel (audit + notes) for quick timeline review.

- **Recurring work automation**
  - Recurrence can be configured as `on close` or `scheduled`.
  - Supports skipping weekends and user-maintained business holidays.
  - Recurring instances can use template todos.

- **Calendar and reporting**
  - Calendar overlays for due dates, milestones, received dates, and closed dates.
  - Per-day event listing with priority-aware ordering.
  - Reports for overdue, due-this-week, and closure velocity.
  - CSV and Excel export.

- **Usability and customization**
  - Selection persistence across task/detail list refreshes.
  - Settings to reorder task panel sections.
  - Configurable shortcuts for `New Task`, `Save Task`, and `Close Task`.
  - Built-in user guide + personal usage notes area.

## Data, Vaults, and Security

- **Vault-based data folders:** each selected folder is an independent vault.
  - If `TASKTRACKER_DATA` is not set, startup prompts for vault folder (open existing / create new).
  - If `TASKTRACKER_DATA` is set, the app uses that path directly.
- Vault contents:
  - `<vault>/auth.json` - password verification data (salt + PBKDF2 hash; not raw password).
  - `<vault>/tasks.db` - SQLite file **only while app is running** (decrypted).
  - `<vault>/tasks.db.enc` - encrypted database **at rest** when app is closed.
  - `<vault>/ui_settings.json` - user UI preferences (layout + shortcuts).
  - `<vault>/personal_usage.html` - personal in-app notes from Help -> User guide -> My notes.
- **Master password:** set on first launch; required each launch. If lost, vault data cannot be recovered.

## Run

```powershell
# From repo root (PowerShell: use `;` instead of `&&` on Windows PowerShell 5.1)
Set-Location c:\CProj\WIP
py -3.11 -m pip install -e ".[dev]"
py -3.11 -m tasktracker
```

## Tests

```powershell
Set-Location c:\CProj\WIP
py -3.11 -m pytest tests -v --tb=short
```

## Project Documents

- `app_overview.md` - product goals and workflow baseline.
- `features.md` - MVP and post-MVP feature scope.
- `FEATURE_GUIDE.md` - catalog of shipped features (UI surfaces, persistence); update when behavior changes.
- `tech_decisions.md` - architecture and implementation decisions.
- `questions.md` - resolved and open product questions.
- `todo.md` - phased implementation checklist.

## Source Relationship Reference

- `WIP_DB_Relationships.png` is used as the preliminary relationship model input.
- Table relationships are treated as baseline constraints.
- Field names are provisional and can evolve during schema design.