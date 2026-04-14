# Technical Decisions

## Runtime and Language
- Python version: **3.11.2** (required).
- Project style: typed Python (`typing`, `dataclasses`/Pydantic models as needed).
- **Deployment shape:** single-user desktop app; Python must be available on each machine that runs the app. Database file may live on **NAS** so the same file is reachable from multiple workstations on the network (see SQLite note below).

## Architecture Direction
- Modular monolith: domain → application services → persistence → **desktop UI** (no separate HTTP tier).
- Separate layers:
  - domain models (task, todo, notes, recurrence)
  - application services (task lifecycle, recurring generation, calendar queries)
  - persistence layer (database repositories)
  - desktop UI layer (launches as the main application window)

## Application shell and delivery (explicit constraints)
- **No web servers of any kind** for this product direction: do not run HTTP servers (including `localhost`), use a browser as the primary UI, or rely on server-rendered web stacks for the main experience.
- The app is a **desktop application**: on launch it opens a **native GUI** (not a browser tab/window to a URL).
- The UI calls application services **directly** (in-process). REST/OpenAPI is **out of scope** unless this document is explicitly revised later.

## UI stack (to be chosen)
- Primary GUI toolkit not yet fixed (e.g. Qt via PySide/PyQt, Tkinter, wxPython). Document the chosen toolkit here once decided.

## Database
- Initial database: **SQLite** (single file; suitable for single-user, local or NAS-hosted file path).
- **NAS caveat:** SQLite on a network share can exhibit locking/latency issues with multiple machines or flaky connectivity. If that becomes painful, consider one workstation as the “authoritative” runner or a later migration to a client–server DB (would be a new decision).
- ORM: **SQLAlchemy 2.x**.
- Migration tool: **Alembic**.
- **Not in scope for v1:** shared multi-user database server; treat data as **one logical user / one file** even if the file is on NAS.

## Product decisions (confirmed)

### Task status
- Include **`on_hold`** and **`cancelled`** in addition to `open`, `in_progress`, `blocked`, `closed`.

### Closed tasks
- **Closed tasks remain editable** for notes and (as needed) other fields—no hard lock on post-close changes.

### Priority (ServiceNow-style, OOTB)
- Use **out-of-the-box ServiceNow** semantics: **Impact** and **Urgency** each on the standard **1–3** scale (1 = High, 2 = Medium, 3 = Low), and **Priority** computed as **P1–P5** via the standard **3×3 matrix** (no custom matrix for now).
- **No standalone priority override:** Impact and Urgency are the inputs; changing them **always** recomputes Priority automatically.
- **Matrix utility (UI):** a small **reference window** shows the OOTB Impact × Urgency → Priority matrix so you can decide which Impact/Urgency pair yields the Priority you want, then set those fields on the task accordingly.
- **When Impact/Urgency change** and Priority therefore changes: persist in the **field audit trail** and also surface in the **notes stream** (e.g. a short **system-generated note** or equivalent activity line—implementation detail—as long as it is visible alongside other notes).
- **Display:** task header and list views show **Impact, Urgency, and Priority** together (all three always visible where priority is shown).

**OOTB 3×3 reference (Impact row × Urgency column → Priority):**

| Impact \\ Urgency | 1 High | 2 Medium | 3 Low |
|-------------------|--------|----------|-------|
| **1 High** | P1 Critical | P2 High | P3 Moderate |
| **2 Medium** | P2 High | P3 Moderate | P4 Low |
| **3 Low** | P3 Moderate | P4 Low | P5 Planning |

*(Labels P1–P5 align with ServiceNow: Critical, High, Moderate, Low, Planning.)*

### Recurring tasks
- **Generation mode is configurable per recurring rule:** either **on task close** or **via a scheduled job** (user chooses when configuring the recurrence).
- **Skip weekends and holidays;** support a **configurable business holiday list** (dates or calendar the app loads—exact UI/storage TBD in implementation).
- **Todos for the next instance** come from a **template** tied to the recurring configuration (user-defined template per recurrence, not “copy all open todos” from the closed task).

### Milestones and todo ordering
- **Next milestone** respects **sequential todo order**: work is assumed in order, but the user may **manually reorder** todos (e.g. to reprioritize a past-due milestone).

### Notes
- **Rich text for MVP1** (bullets, dashes, formatting—not plain text only).
- Notes are **editable** with **version history** retained.

### Calendar
- **Default view: month.** **Week** and **agenda** views available as options.
- **Drag-and-drop date changes** on the calendar are **MVP1**.
- **Overlays:** every date category has a **toggle**. **Default ON:** task **due dates** and **todo milestone** dates. **Default OFF:** **received** date and **closed** date (user can enable via toggles).
- **Closed tasks:** **hidden from the calendar by default**; optional **toggle** to include them (e.g. when showing closed-date overlay).
- **Visual design:** **one distinct color per event type** plus a **legend** linking colors to types.
- **Priority on calendar:** each task shown should **signal its priority** (e.g. badge, border, or icon—exact styling with chosen GUI toolkit). **Within each day**, items are **sorted by priority** (consistent ordering tie-break, e.g. then due date or title—TBD in UI polish).

### Reporting and export
- Early reports: **overdue tasks**, **tasks due this week**, **closure velocity** (all in scope for first wave).
- **CSV and Excel export** in **MVP1**.

### Scope phases
- **`Performance` + `APR`:** **phase 2**, not MVP1.

### Offline
- **Offline-first:** yes (local file / NAS path; no dependency on a remote web service for core use).

### Activity and audit
- **Both:** (1) **field-level audit trail** for changes on task (and related entities as agreed), and (2) **notes as human activity**. The app should support a **combined timeline/query** that surfaces audit events and note activity together (exact UX TBD).

### Blockers
- **Option A:** **`TaskBlocker` as separate rows**—multiple blockers per task, raised/cleared dates, optional attribution; task may still use status `blocked` when at least one active blocker exists (workflow detail in implementation).

### Business holidays
- **User-maintained** holiday list (settings or import—UI TBD); used by recurrence skip logic and any calendar/holiday hints. No code deploy to add holidays each year.

## Preliminary Data Model Decisions
Based on Access relationship structure, preserve these cardinalities (MVP1 unless noted):
- One `Task` → many `TaskNote` (with **version history** for note edits)
- One `Task` → many `TodoItem` (ordered; template source for recurring tasks)
- One `Task` → many **`TaskBlocker`** (separate blocker records)
- One `Task` → many `TaskUpdateLog` / audit rows for field changes
- One `Task` → zero/one `RecurringRule` (with template todos, weekend/holiday skips, holiday list, generation mode)

Field names from Access are inputs only; schema uses Pythonic consistency:
- snake_case columns
- explicit datetime vs date semantics
- strong foreign keys and indexes on date/status fields for calendar and queue views

## Recurrence Engine Decision
- Implement recurrence in the **service layer** (no HTTP).
- Respect per-rule setting: **on close** vs **scheduled job** (scheduler runs inside the desktop app or OS-scheduled process—implementation detail).
- On generation: apply **weekend/holiday** rules and **todo template** from the rule.
- Use explicit transactions to avoid duplicate next-task creation.

## Date and Time Strategy
- Store timestamps in UTC where time matters.
- Store date-only fields for `received_date`, `due_date`, `closed_date` where time-of-day is not needed.
- Store `created_at` (and note version timestamps) with timezone-aware datetime as needed.

## Calendar Strategy
- Calendar data derives from task due dates, todo milestone dates, and (per user toggles) received/closed dates; closed tasks omitted unless toggle says otherwise.
- Indexed query paths for upcoming 7/14/30 day windows.
- **MVP1:** drag-and-drop to change dates from the calendar UI; legend, per-type colors, priority indication, and **within-day sort by priority**.

## Rich text
- MVP1 supports formatted note content (implementation choice: e.g. subset HTML, Qt rich text, or markdown rendered in the widget—pick one stack when UI toolkit is chosen).

## Testing Strategy
- Pytest.
- Unit tests for recurrence rules, holiday/weekend skipping, and milestone derivation with ordered todos.
- Integration tests for task close + next-task generation (both trigger modes where applicable).
- Integration tests for application services and UI adapters (**no HTTP server**).

## Documentation and in-app help
- **Feature documentation:** Whenever behavior or UI is added or materially changed, update the shipped **user guide** (`tasktracker/resources/user_guide.html`) so Help → **User guide** stays accurate. Treat it as part of the same change as the feature (same PR / same release habit).
- **Personal usage notes:** End users maintain **`app_data/personal_usage.html`** via Help → User guide → **My notes** (rich text, explicit Save). That file is for private conventions (what goes in each field, naming patterns, workflow tweaks) and is not bundled with the app—it lives only in the data directory.

## Deferred Decisions
- Authentication/authorization model (single-user desktop may stay minimal).
- Notification delivery channel (email/Teams/etc.).
- Exact desktop GUI toolkit and packaging (installer vs portable folder).
- `Performance` / `APR` (phase 2).
