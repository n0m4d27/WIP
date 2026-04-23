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

## Vault and startup flow
- App data is folder-based; each folder is a **vault** with its own `auth.json`, encrypted DB (`tasks.db.enc`), and runtime plaintext DB (`tasks.db` while running).
- On startup, if `TASKTRACKER_DATA` is set, use that folder directly; otherwise show a **vault picker** dialog with:
  - **Open existing vault** (choose folder)
  - **Create new vault** (choose/create folder)
- Each vault has its own password lifecycle:
  - Missing `auth.json` -> set new password and initialize a fresh schema.
  - Existing `auth.json` -> require password to unlock (incorrect password re-prompts; user can cancel to exit).
- This design allows multiple independent task collections, each with separate password protection.

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

### Task taxonomy and attribution
- Tasks support a vault-scoped taxonomy: **Category → Sub-category → Area**.
- Tasks can optionally reference an **Area**; category/sub-category are derived from that selected area.
- Tasks can optionally reference a **For person** attribution entry (`first_name`, `last_name`, `employee_id`).
- Taxonomy and people are managed in **Settings** and are persisted per vault.
- Taxonomy/people support **JSON export/import** so multiple vaults can be synchronized with the same reference data.

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

## Forward-looking plans and decisions log
- **Two documents, two jobs:** `tech_decisions.md` (this file) is the **retrospective** record — "why we built it this way, and what trade-offs we chose". The **`plans/`** folder at repo root is the **forward-looking roadmap** — one markdown file per planned feature (plus a master `plans/README.md` staging doc that tracks pipeline status, cross-plan dependencies, rollout bugs, and follow-ups). Plans describe work that has not shipped yet; this document describes work that has.
- **When a plan lands:** (1) append a short decision note here — plan number, a one-paragraph summary of what shipped and why, following the tone of the existing sections; (2) mark the plan row `Done` in `plans/README.md` with the finished date; (3) update `tasktracker/resources/user_guide.html` if the change is user-visible. The plan doc itself stays in `plans/` as historical context rather than being deleted.
- **Mid-flight scope shifts and bugs:** any deviation from a plan's original text (scope cut or expanded, approach changed) is logged in the master `plans/README.md` Decisions log rather than silently rewriting the plan. Bugs found during rollout go into the same doc's rollout-bugs table so regressions have a searchable history. `tech_decisions.md` stays clean and decisions-focused rather than turning into a bug tracker.
- **Working file for Access DB capture:** `access_workflow_capture.md` at repo root is the user's private working doc for describing how the legacy Access DB is used day to day — pain points, reports, fields, and migration thinking. It feeds plan 13 (intake and migration) and influences other plans where the Access shape matters. It is not bundled with the app.

## Dashboard and saved views (plan 01 — landed)
- **New Dashboard tab** is the leftmost tab and the default landing surface, answering "what needs my attention right now" without forcing the user to scroll the task list. Cards (Overdue, Due today, Due this week, Blocked, Top priority P1/P2) each show a live count, a compact list of the top N rows, and a **Show all** button that jumps to the Tasks tab with the matching filter applied. All card math is produced by a single service method — `TaskService.dashboard_sections(as_of, top_n)` — so tests and UI never disagree about, for example, what "this week" means. The card id tuple `DASHBOARD_CARD_IDS` is the single source of truth for ordering.
- **Dashboard is pure read + summarize**, on purpose. Clicking a task row opens it on the Tasks tab (same as the Tasks-list double-click) rather than an inline editor; inline drill-down was deferred to a later plan to avoid two editors pointing at the same task. Refresh is automatic on tab entry so save / close / import actions elsewhere can't leave stale counts up; the host window also calls `_refresh_dashboard()` once after startup in case the user launched straight into the tab.
- **Saved views sidebar** lives in the Tasks tab's left column, above the task list. Each view captures `search_text`, the set of enabled search-field checkboxes, and `hide_closed`. Persistence helpers (`get_saved_views` / `set_saved_views` / `add_saved_view` / `remove_saved_view` / `rename_saved_view` / `move_saved_view`) in `tasktracker/ui/settings_store.py` are the only code paths that mutate the list; each writes a coerced snapshot back into `ui_settings.json` so hand-edited files can't introduce duplicate or malformed entries. Name collisions on save are treated as "replace filters in place, keep the original casing and position" so an accidental lowercase "inbox" doesn't visually rename a carefully-cased "Inbox".
- **Forward-compatible view schema:** every saved view stores a `version` integer (currently `SAVED_VIEW_SCHEMA_VERSION == 1`). When a future plan widens the filter dimensions (e.g. tags from plan 06, categories, priority ranges), the coercion layer can branch on version to migrate entries in place without dropping the user's existing views.
- **Last-tab restore:** `ui_settings.json` also grows a `last_tab` key (default `"dashboard"`). `get_last_tab` / `set_last_tab` validate against `KNOWN_TAB_IDS` so an unknown tab on disk silently coerces to the Dashboard. The main window writes the value on every tab switch and reads it once on startup to decide which tab to show.

## Notes full-text search (plan 02 — landed)
- **SQLite FTS5** backs task search for **Title**, **Description**, and **Notes** via virtual table `task_search_fts` (columns `title`, `description`, `notes`; `task_id` stored UNINDEXED; tokenizer `porter unicode61 remove_diacritics 2`). Plain text for notes comes from the **latest `TaskNoteVersion.body_html` per note** after the same HTML-stripping path used elsewhere (`_to_plain_text`), so indexed words match what users see, not raw markup tags.
- **Why FTS5 instead of widening LIKE:** tokenization and stemming scale better on large vaults; note bodies no longer require per-row substring scans or fragile `EXISTS` chains over every version row. **Trade-off:** the FTS index adds DB size (often noticeable when notes are long); acceptable for single-user local vaults.
- **Sync strategy:** **service-layer**, not SQL triggers. `sync_task_search_fts` runs after task create/update, note add/edit, and when a recurring successor task is created, so the FTS row stays aligned with ORM writes. `upgrade_schema` creates the FTS table if missing and **`sync_all_task_search_fts_if_stale`** repopulates when row counts diverge (idempotent; safe on every startup). Any future code path that mutates tasks or note bodies outside `TaskService` must call sync or rely on that backfill.
- **Search behavior:** `TaskService.search_tasks` returns **`TaskSearchHit`** objects (`task` + optional **`snippet`**). When only indexed fields are selected (no Todos / Blockers / Audit) and the query is **FTS-eligible** (roughly: multi-character tokens), the implementation uses **`MATCH`** and FTS **`snippet()`**; very short or token-poor queries fall back to the legacy **LIKE** path so single-character and punctuation-heavy searches still behave. Searches that include Todos, Blockers, or Audit always use the LIKE / `EXISTS` path for those dimensions.
- **UI:** the Tasks tab search box has a tooltip describing full-text vs fallback; task list rows show a **plain-text excerpt** in the tooltip when a hit came from FTS with a snippet.

## Task templates (plan 03 — landed)
- **Purpose:** reusable **one-off** task shapes (name, title/description patterns, default taxonomy, I/U/status, seed todos) distinct from **`RecurringRule`**, which ties the next instance to **closing** a specific recurring task. A task created from a template can still get a recurring rule later; the two features are orthogonal.
- **Schema:** `task_templates` (unique `name`, `title_pattern`, optional `description_pattern`, optional `default_area_id` / `default_person_id` with **ON DELETE SET NULL**, `default_impact` / `default_urgency` / `default_status`, `sort_order`, timestamps) and child `task_template_todos` (`sort_order`, `title`, optional `milestone_offset_days` in **business days** from the instance **received** date, computed with `shift_business_days` and the vault holiday list).
- **Placeholders** in patterns and todo titles: `{today}`, `{yyyy}`, `{mm}`, `{dd}`, `{week}` (ISO week number), expanded from the **received date** the user picks in the picker. Non-HTML description text is wrapped in a single `<p>` with HTML escaping.
- **UX:** **Settings → Task templates…** manages CRUD, reorder, and JSON export/import (idempotent **by template name**; `area_path` as `Category / Subcategory / Area` and `person_employee_id` for portable imports). Toolbar **New from template…** opens a filterable list + received/due dates, then fills the task detail as an **unsaved draft**; **Save Task** persists the task and seed todos. Draft mode blocks todos/notes/blockers/recurrence until save.
- **Deletion:** `TaskService.delete_task` removes a task and its FTS row (no main-window delete button yet — optional follow-up).

## Interaction consistency
- After save/update actions that refresh list-backed panes (tasks, notes, todos, blockers, holidays), the UI should preserve the previously selected item when it still exists; for newly created items, prefer selecting the new row. This is a deliberate usability rule to avoid forcing re-selection while editing.
- **Todo editing:** Todos are editable post-creation. Selecting a todo and pressing **Edit…** (or double-clicking the row) opens the same dialog used to add a todo, pre-filled with the current title and milestone. Milestones can be set, changed, or cleared; an empty/whitespace title is treated as a no-op rather than an error. The parent task's next-milestone cache refreshes whenever a milestone changes. Service-layer entry point: `TaskService.update_todo` (see `tasktracker/services/task_service.py`), using the same `_UNSET` sentinel pattern as `update_task_fields` so callers can distinguish "leave alone" from "clear to `None`".

## Task detail layout and shortcuts
- **Two-column core form:** The core task fields are laid out in two columns below the **Task actions** row. The **left column** (wider, stretch 2) holds text-heavy inputs — Ticket, Title, a combined **Status / I / U / P** row, and a **Description** editor that expands vertically to fill available space. The **right column** (narrower, stretch 1) holds dates and taxonomy — Received, Due, Closed, Category, Sub-category, Area, For person, Next milestone. The split relieves horizontal squishing that the old single-column form caused when long titles or rich descriptions pushed the form out of alignment.
- **Hybrid sections (inline + tabs):** Below the core form, **Todos**, **Blockers**, and **Recurring** render **inline** as stacked group boxes (always visible, compact). **Notes** and **Activity** render as **tabs** in a `QTabWidget` that fills the remaining vertical space. This reflects typical content growth: notes and audit timelines can grow without bound, while the inline sections stay at a predictable height. Placement is driven by `TASK_SECTION_PLACEMENT` in `tasktracker/ui/settings_store.py`; tab captions come from `TASK_SECTION_TAB_LABELS`.
- **Customize task panel layout:** The **Settings → Customize task panel layout…** dialog now presents two independently-reorderable groups — **Inline sections** and **Tabs** — each with its own Move up / Move down controls. Cross-group moves are not offered by design (changing a section from inline to tab would require re-allocating screen real-estate); the saved order is still a single list concatenating inline order followed by tab order, stored in **`ui_settings.json`**.
- **Movable sections:** Below the core task fields (ticket through next milestone), the blocks **Todos**, **Notes**, **Blockers**, **Recurring**, and **Activity** can be reordered via **Settings → Customize task panel layout…**. Order is stored in the vault data folder as **`ui_settings.json`** (with **`auth.json`** and the database).
- **Task commands placement:** **New Task**, **Save Task**, and **Close Task** remain on the main toolbar for discoverability; the same three actions are duplicated in a **Task actions** row at the top of the task detail (right) pane so frequent edits do not require moving the pointer to the window top edge. Capitalize **Task** in these labels.
- **Keyboard shortcuts:** The same three actions have **application-wide** shortcuts (defaults: **Ctrl+N**, **Ctrl+S**, **Ctrl+Shift+C** for Close Task so **Ctrl+W** stays free for typical “close window” semantics). Users can change them in **Settings → Keyboard shortcuts…**; shortcuts are persisted in **`ui_settings.json`**.
- After the user picks a vault folder (when `TASKTRACKER_DATA` was not preset), startup sets **`TASKTRACKER_DATA`** to that folder so all `app_data`-relative paths (including UI settings and personal notes) resolve to the active vault.

## Notifications and confirmations
- **Status-bar for routine confirmations:** Successful and "gentle nudge" feedback (e.g. *Task saved*, *Todo updated*, *Select a task first*, *Reference data exported*, *Recurrence settings saved*, *Due date set to …*) is delivered through `QMainWindow.statusBar().showMessage(msg, timeout_ms)` via the `MainWindow._notify` helper. Default timeout is **4000 ms**; the longer **Close Task** message (which includes the newly-spawned child ticket number, if any) uses **6000 ms** so the user has time to read it.
- **Modal dialogs reserved for errors and summaries:** `QMessageBox.warning` / `.critical` / `.question` remain the right tool for errors, destructive-action confirmations, and multi-line import/export summaries (e.g. the reference-data import report) that the user genuinely needs to read and acknowledge. The rule of thumb is: if dismissing the message without reading it would be harmful, use a modal; otherwise use the status bar.
- **Why:** Modal popups for trivial successes were the single biggest interruption in the save / iterate loop. A transient status bar message keeps focus in the task form (keyboard and mouse caret stay put) so **Ctrl+S** → continue editing now has no extra click.

## Reporting and exports
- **Dedicated `ReportingService`:** Management-style reports live in `tasktracker/services/reporting_service.py`, separate from the CRUD-oriented `TaskService`. Each report function returns a small `ReportResult` dataclass (`name`, `columns`, `rows`, `meta`, `summary`) so the in-app table, the CSV writer, the rich Excel workbook, and the per-report CSV bundle all consume the same shape. The legacy `TaskService.report_overdue` / `report_due_this_week` / `report_closure_velocity` helpers stay for backward compatibility but the Reports tab no longer calls them.
- **Six reports:** `wip_aging` (open tasks bucketed `0-7 / 8-30 / 31-90 / 90+` calendar days, cross-tabbed by status and priority), `throughput` (closed counts by ISO week or month, optional split by category or **for-person**), `workload` (per **for-person** open count + overdue + P1/P2 + oldest received + average age, with an explicit `(unassigned)` bucket), `sla` (on-time vs late closes per category, miss rate %, average days late; tasks closed without a due date counted separately as `no_sla` and excluded from miss-rate math), `category_mix` (received vs closed in the window per category plus current open for backlog growth), and `weekly_status` (composite "what's closed / open / due / blocked" readout sized for an emailable status update).
- **"For person" terminology in reports:** the column key and the Group-by label read `for_person` (`By for-person` in the UI) rather than `person`, so the reports match the `For person` form label on the task panel and the existing `for_person` / `for_person_employee_id` columns on the flat Tasks export. The reporting service silently accepts the legacy `group_by="person"` value as a back-compat alias so `ui_settings.json` files written before the rename keep loading without manual editing.
- **Calendar days, not business days:** Ages and "days late" in reports are calendar days. Business-day math stays in the recurrence engine (where it materially affects spawning successor due dates) but management pivots in Excel intuitively against `received_date` / `closed_date`, so we don't second-guess them with skip-weekends logic.
- **Reports tab UX:** Left list of report names → param panel that swaps via `QStackedWidget` so each report only shows its own controls (Date / From / To / Period / Group by) → `QTableWidget` of rows → buttons for **Run**, **Export this report (CSV)…**, and **Copy summary to clipboard** (the `summary` string from `ReportResult`, suitable for pasting into Teams / email). Default date range is first-of-current-month → today; last-used parameters per report are persisted under `reports.last_params` in `ui_settings.json` (helpers: `get_report_params` / `set_report_params`).
- **Two export shapes:** under the **File** menu we keep the existing `Export tasks to CSV…` / `Export tasks to Excel…` flat dumps, and add (a) **Export rich workbook (xlsx)…** which calls `tasktracker/services/excel_export.py::build_rich_workbook` to write a multi-sheet workbook (`Summary`, `Tasks` with computed `age_days` / `days_to_due` / `days_late` / `was_closed_late`, `Todos`, `Notes` with `body_text` derived from a HTML strip of the latest version, `Activity`, plus one sheet per report — `WIP_Aging`, `Throughput_Weekly`, `Throughput_Monthly`, `Workload`, `SLA`, `CategoryMix`, `WeeklyStatus`); and (b) **Export reports bundle (CSVs in folder)…** which writes one CSV per report (`wip_aging.csv`, `throughput_weekly.csv`, `throughput_monthly.csv`, `workload.csv`, `sla.csv`, `category_mix.csv`, `weekly_status.csv`) into a chosen folder, sized for emailing or piping into other tools. Both surfaces reuse `ReportingService` so the rows match the in-app table exactly.
- **Workbook polish:** every data sheet in the rich workbook gets a frozen header row (`A2`) and an Excel auto-filter on the populated range, so the file is immediately usable for sort / filter / pivot without per-sheet setup. `openpyxl` was already a dependency for the legacy single-sheet `Excel` export, so no new packages were introduced.

## Editing tasks from the Calendar tab
- **Quick-edit dialog (chosen):** Double-clicking an event in the Calendar tab's day list (or clicking **Edit selected task…**) opens a focused modal in `tasktracker/ui/calendar_quick_edit_dialog.py` with the high-traffic fields only — **Status**, **Due**, **Closed**, **Impact / Urgency** (with live priority readout), **For person**, and **Area** (flat `Category / Sub / Area` list to avoid rebuilding the three-combo cascade for a quick edit). The title is shown but not editable from here; renames belong on the full editor.
- **Close-transition parity:** The dialog's save path mirrors `MainWindow._save_task_detail`. When the user flips status from open-ish to `closed` it delegates to `TaskService.close_task` so recurrence successors still spawn from a calendar quick-edit, then surfaces the same "Task closed. Created successor T{n} (id …)." status-bar message (6000 ms).
- **One-click escape to the full editor:** The dialog includes an **Open in Tasks tab for full edit** link button, and the Calendar tab has a matching **Open in Tasks tab** button, both backed by a single `MainWindow._jump_to_task_in_tasks_tab(task_id)` helper. The helper switches the central `QTabWidget` back to the Tasks tab and reuses `_select_list_item_by_id` to highlight the task; if the task isn't currently visible (filtered out by search or closed-only toggle) the user gets a status-bar nudge rather than a silent no-op.
- **Why not refactor the full task panel into a popout:** The existing task detail panel is welded to `MainWindow` state (`self._current_task_id`, `self._loading_task_form`, ~30 `self.f_*` widgets, and handlers like `_save_task_detail` / `_close_current_task` / `_edit_todo` / `_apply_task_section_order`). Extracting it into a reusable widget so a non-modal `QDialog` can host the whole editor is a real refactor and was deferred as a follow-up so this calendar-editing improvement doesn't get gated on it. The quick-edit dialog + jump button cover the vast majority of calendar-driven workflows (status changes, due / closed date tweaks, reassignment) in the meantime.
- **Todos + notes inside the quick edit:** The quick-edit dialog embeds (a) a **Todos / milestones** editor (`QTableWidget` with Add / Edit / Mark done / Delete) and (b) a **read-only notes snapshot** list below, in a vertical splitter. Notes can be opened in a nested read-only viewer by double-click. A form-level **"Also shift todo milestones"** checkbox (with a **Business days** sub-toggle) applies the same delta as the task's due-date change to every attached todo milestone at save time via `TaskService.shift_task_milestones`. A compact **"Shift selected: N day(s) / Business days / Apply to selection"** strip above the todos table lets the user shift only the currently-selected rows by invoking `ShiftService.preview_todo_shift` + `apply_shift`; the returned `ShiftResult` is registered with `MainWindow.record_bulk_shift` so **Edit → Undo last bulk shift** picks it up. Full note editing, description, blockers, and recurrence still require the Tasks-tab editor — the calendar dialog is a reschedule-oriented surface, not a general replacement for the full panel.

## Color themes
- **Four curated palettes, all Fusion-based.** `tasktracker/ui/themes.py` ships a small registry (`THEMES` tuple) with four entries: **Light** (first-launch default), **Dark**, **Light gray (reading)**, and **Sepia (reading)**. Every palette is rendered through Qt's `Fusion` style — there is no "hand off to the platform style" escape hatch, because Qt's native Windows style (`windowsvista`) draws most controls through Win32 API calls and **ignores `QPalette` for buttons, combos, line edits, date pickers, plain-text / text edits, checkboxes, and scrollbars**. That inconsistency was why the first-cut dark theme only recolored containers and left every input Windows 7-era gray; the fix is to apply Fusion universally so the palette actually covers every widget. The registry order is also the menu order, so reshuffling is a one-line change.
- **Light palette — "Soft light".** The default Light theme deliberately sits between pure white and the gray reading theme: Window `#ececec` (softly off-white, avoids the glare of `#ffffff`), Base `#fbfbfb` (near-white input fields so inputs stand out against the chrome), Button `#e4e4e4` (just darker than the window so bevels read), Highlight `#2a6db3` (cool muted blue — neutral on purpose so it doesn't encroach on the warm sepia territory). Full role coverage + a `disabled_spec` block keep disabled text readable on top of Fusion's auto-derivation.
- **Legacy `"system"` migrates to `"light"` for free.** Earlier releases shipped a `"system"` theme id that deferred to Qt's platform style. When that option was removed, we didn't add an explicit migration step: `_coerce_theme_id` already resolves unknown ids to `DEFAULT_THEME_ID`, and `get_theme` does the same lookup, so any persisted `"theme": "system"` silently becomes `"light"` on the next load. `tests/test_themes.py::test_legacy_system_theme_id_migrates_to_light` pins this behaviour.
- **Palette spec covers the full role set.** Each `Theme.palette_spec` covers every widget-facing `QPalette.ColorRole`: Window / WindowText / Base / AlternateBase / Text / Button / ButtonText / BrightText / Highlight / HighlightedText / ToolTip\* / PlaceholderText / Link / LinkVisited **plus** the Fusion-frame roles (Mid / Midlight / Dark / Light / Shadow) that scroll tracks, focus rings, and groupbox bevels read from. Each color is set across the **Active**, **Inactive**, and **Disabled** `ColorGroup`s so focus changes never flash a default palette through. Themes also ship an optional `disabled_spec` (Text / WindowText / ButtonText / HighlightedText only) that overrides Fusion's auto-derived disabled shades where the derivation is hard to read — notably on the dark theme, where Fusion's default disabled-text color is too close to the window background.
- **Stylesheets are tiny on purpose.** Because Fusion handles every standard widget via the palette, the per-theme stylesheet fragment is reduced to just two or three rules: tooltip frame colors, and the dark theme's `QMenu::separator` accent. Heavy QSS tends to fight Fusion's own paint routines and look worse than palette-only theming, so we deliberately keep the QSS surface small. Adding a new theme needs a palette dict + an (optional) disabled spec — no stylesheet work in the typical case.
- **Theme-aware calendar day shading.** The Calendar tab highlights any day carrying a visible event (due / milestone / received / closed). The background-and-foreground pair for that highlight lives in each theme's `extras` dict (`calendar_event_bg` / `calendar_event_fg`), surfaced through `tasktracker/ui/themes.py::calendar_event_colors(theme_id)`. The old implementation hard-coded a pale-blue background and let Qt pick the foreground; on the Dark theme Fusion's light-gray day digits blended into the pale blue so the user could not tell which day of the month was flagged. Each curated theme now ships an explicit fg/bg pair (pale blue + dark navy for the light palettes; deep steel blue + white for Dark; warm amber + sepia ink for Sepia) and `MainWindow._highlight_calendar_month` applies both. `MainWindow._on_theme_selected` also re-runs the highlighter so theme switches are live without a tab revisit.
- **Persistence + startup wiring.** `ui_settings.json` carries a `theme` key (default `"light"`) with a `_coerce_theme_id` validator that silently resets unknown or non-string values to the default so a hand-edited / corrupted settings file never breaks launch. `set_theme_id` / `get_theme_id` are the round-trip helpers. `__main__.py` calls `apply_theme(app, get_theme_id(load_ui_settings()))` right after resolving the vault and setting `TASKTRACKER_DATA` — before the login dialog — so the user's theme covers the **entire** session, not just the main window. Theme failures during startup are caught and ignored so a broken theme can never lock the user out.
- **View menu + live switching.** `MainWindow._build_theme_menu(view_menu)` adds a **View → Theme** submenu populated from `list_themes()`. Entries are `QAction(checkable=True)` items in a single `QActionGroup` with `setExclusive(True)`, giving radio-button semantics without custom bookkeeping — toggling one theme automatically unchecks the previous one. Selecting an entry calls `_on_theme_selected(theme_id)` which **persists first, then applies**, so a crash between write and paint still leaves the next launch in the intended state. `apply_theme` swaps the style + palette + stylesheet on the running `QApplication`; Qt repaints every open widget automatically, so there's no need to reload views or restart the app.
- **Menu bar ordering.** Adding the View menu was the natural moment to reorder the menu bar to the standard Windows sequence: **File → Edit → View → Settings → Help**. Previously menus were added in the order they were implemented (Edit / Settings / File / Help), which clashed with muscle memory from every other Windows / cross-platform app. No functional change beyond the insertion order.

## Date display format
- **User-configurable Qt format:** `ui_settings.json` now stores a `date_format` key (default `"yyyy-MM-dd"`), settable via **Settings → Date format…**. The dialog offers a curated list of presets (ISO, US, EU, short / long month-name variants) and a **Custom…** escape hatch that accepts any Qt `QDateEdit.setDisplayFormat` pattern, with a live preview against today's date. Persistence, validation, and round-trip helpers live in `tasktracker/ui/settings_store.py` (`get_date_format_qt` / `set_date_format_qt` / `_coerce_date_format`).
- **Scope: UI surfaces only, exports stay ISO.** Pickers (`QDateEdit`), read-only UI strings (Tasks list subtitles, Next milestone label, todo milestone cells, status-bar confirmations, Holidays list, Reports table cells, Reports summary panel, Shift preview table + summary) all honour the user's chosen format. **CSV / Excel / JSON exports, service-layer return shapes, and on-disk `ShiftPlan.params` always use ISO `yyyy-MM-dd`** so downstream spreadsheets / pandas / scripts never have to guess the locale. The rule of thumb: formats change what the eye sees in the UI; they never touch wire / file representations.
- **Qt → Python translation:** `tasktracker/ui/date_format.py::qt_to_py_format` walks the Qt pattern token-by-token (ordered from longest to shortest so `yyyy` is not consumed as `y` × 4), producing a `strftime` string. Unknown tokens pass through unchanged so free-text custom formats degrade gracefully. `format_date(date, qt_fmt)` is the one-call rendering helper; `reformat_iso_dates_in_text(text, qt_fmt)` and `iso_string_to_display(value, qt_fmt)` rewrite pre-formatted ISO strings from the service layer so report summaries / table cells can be re-rendered without re-plumbing every service to take a format arg.
- **Live refresh without relaunch:** on save the Settings dialog's caller calls `MainWindow._apply_date_format_to_widgets()` (which walks `findChildren(QDateEdit)`) and `_refresh_date_dependent_surfaces()` (which re-invokes the task list / holidays / task detail / reports / calendar render passes). Dialog-local `QDateEdit` widgets constructed before any settings change already pick up the stored format via `tasktracker/ui/date_format.format_from_parent(parent)`, which walks the parent chain looking for the `MainWindow._ui_settings` dict.
- **Safety rails:** `_coerce_date_format` rejects non-strings, empty / whitespace-only entries, and strings longer than 64 characters so a corrupt `ui_settings.json` can't produce a ridiculous format string that would be evaluated for every date widget. `format_date` falls back to ISO if `strftime` raises a platform-specific `ValueError` (e.g. an unknown directive). The dialog's free-text field clamps an empty "Custom…" entry back to the ISO default on OK.

## Launcher state and default vault
- **Launcher settings file:** A Qt-free `tasktracker/launcher_settings.py` module persists **`launcher.json`** in the user's standard config directory (`QStandardPaths.AppConfigLocation`, with a dotfile fallback). The file tracks `last_opened`, `default_vault` (pinned), and a bounded `recent_vaults` list (max 8). This file lives **outside** every vault on purpose, so the launcher can recover even when no vault has been opened yet and so multiple vaults don't race to rewrite each other's launcher state.
- **Startup resolution order:** On every launch `__main__.py` resolves the target vault in this priority:
  1. `--pick-vault` CLI flag (always shows the picker),
  2. `TASKTRACKER_DATA` environment variable (unchanged from before),
  3. `default_vault` from `launcher.json` if the folder still exists,
  4. `last_opened` from `launcher.json` if it still exists,
  5. fall through to the vault picker dialog.
  If a cached path no longer exists, the app falls through to the picker and passes a one-line `startup_notice` into `MainWindow` ("Could not open previous vault: \<path\>; please choose another.") which the status bar shows once. The resolved vault is re-recorded via `record_opened` and `launcher.json` is saved immediately.
- **Picker dialog extensions:** `run_vault_picker_dialog` now takes an optional `LauncherSettings` handle. When present, it adds a **Recent vaults** drop-down (pre-populates Open / Create paths when chosen), an **"Always open this vault on launch"** checkbox (sets / clears the pinned default), and a **Clear pinned default** button that calls `clear_default`. The picker only mutates the in-memory object; the caller (`__main__.py`) is responsible for calling `save` so disk I/O stays centralised.
- **Escape hatches when auto-open is on:** Users aren't locked into the default vault. The login dialog grows a **Switch vault…** button (returns the `SWITCH_VAULT_REQUESTED` sentinel from `run_login_dialog`), and the main window's **Settings → Switch vault…** menu action both trigger the same relaunch path: `secure_shutdown` + `subprocess.Popen([sys.executable, "-m", "tasktracker", "--pick-vault"])` + `QApplication.quit()`. Relaunching (instead of swapping DB handles inside the running process) sidesteps every cached service / session / encryption-key reference that currently points at the old vault.

## Bulk date shifts ("slip forward" / multi-task shift)
- **`ShiftService` facade:** All bulk date changes flow through `tasktracker/services/shift_service.py`. The service defines three immutable dataclasses — `ShiftPlanRow` (one proposed change with Kind / Ticket / Title / Field / Old / New / Flag), `ShiftPlan` (rows + human summary + JSON-friendly params for logging / undo), and `ShiftResult` (the applied shift with `shift_id`, `applied_at`, actually-written rows, and an `inverse` plan) — and exposes three symmetric preview methods: `preview_task_shift(task_ids, delta_days, *, business_days, include_todos)`, `preview_slip_from_date(anchor, delta_days, *, business_days, filters…)`, and `preview_todo_shift(todo_ids, delta_days, *, business_days)`. `apply_shift` is the single write path (atomic commit + optimistic locking that skips rows whose current DB value no longer matches the plan's "old" value) and `undo_shift` simply calls `apply_shift(result.inverse)`.
- **Business-day + holiday aware:** Shifts default to business days. `task_service.shift_business_days(start, days, holidays, *, skip_weekends, skip_holidays)` extends the existing forward-only `add_business_days` helper to bidirectional math so the same helper powers both "+5 days" and "-3 days" without callers flipping signs. Calendar-day mode is still available via the dialog checkbox — useful when the user wants to land on a specific weekday regardless of weekends. Both modes tag any row that lands on a weekend / holiday / no-op with a `flag`, and the preview dialog colors those rows so the user notices before applying.
- **Entry points:**
  - **Tasks tab → multi-select + "Shift dates…":** `task_list` now uses `ExtendedSelection`; a right-click context menu and the new **Edit → Shift selected tasks…** menu action open `ShiftScopeDialog(mode="tasks")` with the current selection pre-bound.
  - **Global "Slip schedule from date…":** **Edit → Slip schedule from date…** opens `ShiftScopeDialog(mode="slip")` with filter controls (anchor date, for-person, area, min priority, status). This fans through `preview_slip_from_date`, which excludes `closed` / `cancelled` by default.
  - **Calendar quick-edit:** the selection-shift strip (above) shifts only the rows the user has highlighted in that dialog's todos table.
- **Mandatory preview before apply:** Every entry point routes through `ShiftPreviewDialog` — a sortable table of `ShiftPlanRow`s with old / new columns, flag-based row tinting, and a summary header. The user must click **Apply** in the preview for anything to be written.
- **Single-level undo:** `MainWindow` caches the most recent `ShiftResult` in `self._last_bulk_shift` and toggles **Edit → Undo last bulk shift** (**Ctrl+Shift+Z**, also available from the task-list context menu and the calendar dialog's strip) between enabled and disabled with a tooltip that describes what would be reverted ("Revert {n} changes applied at {ts}"). Undo clears the cached result so it can only be applied once, by design. Non-shift edits between the shift and the undo will fail their individual rows via the optimistic-lock check and be skipped cleanly rather than overwriting fresh work.
- **Audit:** `apply_shift` writes one `bulk_shift` entry in the change log per affected task (summary line + the plan's `params`) so reports / compliance exports still see each row's provenance.

## Deferred Decisions
- Authentication/authorization model (single-user desktop may stay minimal).
- Notification delivery channel (email/Teams/etc.).
- Exact desktop GUI toolkit and packaging (installer vs portable folder).
- `Performance` / `APR` (phase 2).
