# Feature guide (catalog)

This file is the **standalone feature catalog** for Task Tracker: what exists in
the product today, where it lives in the UI, and how data is persisted. It
complements other docs:

| Document | Role |
|----------|------|
| `tasktracker/resources/user_guide.html` | In-app, step-by-step help for end users. |
| `FEATURE_GUIDE.md` (this file) | Maintainer / product inventory: capabilities, surfaces, storage. |
| `tech_decisions.md` | Why notable choices were made. |
| `plans/README.md` + `plans/0N_*.md` | Roadmap and per-feature delivery plans. |

When a plan ships user-visible behavior, update **this file** in the same PR as
`user_guide.html` (see `plans/README.md`, “Land the plan”).

---

## Application shell

- **Platform:** PySide6 desktop app; local-first, no HTTP server.
- **Vault:** Each data folder is an isolated vault. Startup uses `TASKTRACKER_DATA` if set; otherwise the user picks or creates a vault folder.
- **Encryption at rest:** While closed, the SQLite database is stored as `tasks.db.enc`; while running, a decrypted `tasks.db` exists in the vault. **Attachments** under `attachments/` are plaintext while unlocked and become per-file Fernet ciphertexts (sibling `*.enc` files) when the app closes, using the same key as the database. Master password gates launch (`auth.json` holds salt + PBKDF2 hash only).
- **Per-vault UI state:** `ui_settings.json` — layout, shortcuts, date format, theme, text scale, display timezone, dashboard/saved-view preferences, last tab, etc.
- **Personal notes:** `personal_usage.html` — editable from Help → User guide → My notes.

**UI entry:** File / vault switch, Help → User guide, Settings menu.

---

## Dashboard and saved views

- **Dashboard tab:** Read-only “attention now” cards backed by
  `TaskService.dashboard_sections`: **Overdue**, **Due today**, **Due this week**
  (next 7 days), **Blocked**, **Top priority (P1/P2)**. Activating a row or
  **Show all** switches to the **Tasks** tab with the matching filter (no
  inline editor on the dashboard).
- **Saved views:** Named filter presets; sidebar to apply, save, rename, delete. View payload is versioned for forward compatibility.
- **Last session:** Restores the last selected main tab (e.g. Tasks vs Dashboard); auto-applying a saved view at startup is intentionally not default behavior.

**Persistence:** Saved views and dashboard-related UI state in `ui_settings.json` / service-backed settings (see `settings_store` / `saved_views` modules).

**Plans:** `plans/01_dashboard_and_saved_views.md` (Done).

---

## Task list and search

- **Tasks tab:** Primary list/detail workflow; ticket numbers `T0`, `T1`, …
- **Selection:** Selection is preserved across refreshes where possible.
- **Search:**
  - Multi-term queries use **FTS5** over task fields and **note bodies** (HTML stripped for indexing).
  - Very short / single-character queries may fall back to `LIKE` for usability.
  - List tooltips can show **snippets** from matching note text.

**Persistence:** Tasks and notes in SQLite; FTS in `task_search_fts` (synced from application code on write).

**Plans:** `plans/02_notes_fulltext_search.md` (Done).

---

## Task detail: core fields

- **Lifecycle:** Received, due, closed dates; status (open, in progress, blocked, on hold, cancelled, closed).
- **Priority:** ServiceNow-style P1–P5 from impact and urgency.
- **Taxonomy:** Category → sub-category → area (per vault reference data).
- **People:** “For person” from vault people master data.

**UI:** Task editor on the Tasks tab; calendar-driven open from Calendar tab.

---

## Task templates

- **Templates:** Named presets: title/description patterns (with placeholders such as `{today}`, `{week}`), default area/person, impact/urgency/status, and seed **template todos** (with optional business-day milestone offsets).
- **Manage:** Settings → **Task templates…** — CRUD, reorder, JSON import/export (same pattern as taxonomy/people).
- **New from template:** Toolbar/menu opens picker; applies template to an **unsaved draft** until the user saves the task.

**Persistence:** `task_templates`, `task_template_todos` tables.

**Plans:** `plans/03_task_templates.md` (Done).

---

## Todos

- Ordered checklist per task; optional **milestone** dates on items.
- **Next milestone** on the task is derived from the first open dated todo.

---

## Notes

- **Rich text** notes per task with history/versioning.
- Full-text search includes note content (see Search).

---

## Attachments

- **Inline section** on the Tasks tab (default order with Todos / Blockers / Recurring; can move under **Settings → Customize task panel layout…**).
- **Add** via file picker (multi-select) or drag-and-drop; **Open** copies to a session temp directory and launches the OS default handler; **Rename** adjusts display name only; **Remove** deletes row + vault file.
- **Soft limit:** ~100 MB per file with a confirm dialog above that.
- **Storage:** `attachments/<task_id>/<sha256>_<filename>` relative to vault; metadata in `task_attachments` table (`display_name`, `storage_relpath`, `content_sha256`, `size_bytes`, `mime_hint`, `created_at`).
- **Task delete:** Folder `attachments/<task_id>/` is removed after the task is deleted.

**Plans:** `plans/04_attachments.md` (Done).

---

## Blockers

- Separate list from todos; can be cleared independently; supports workflow clarity for “blocked” status.

---

## Recurring work

- **RecurringRule** on a task: **on close** or **scheduled** patterns.
- Options include skipping weekends and respecting **business holidays**.
- Can use **recurring todo templates** for spawned instances.

---

## Calendar

- Tab showing tasks on dates: due, milestone, received, closed overlays.
- Per-day listing with priority-aware ordering.
- **Editing:** Opening a task from a calendar cell follows the in-app flow described in the user guide (double-click / edit path).

---

## Bulk date shifts

- **Re-task** multiple tasks at once: shift received/due/milestone (and related fields per dialog) with a preview.
- Respects business-day logic where applicable (see user guide).
- **Undo:** Edit → **Undo last bulk shift** reverses the most recent apply (one level only; hidden when nothing to undo).

---

## Reports and export

- Reports for **overdue**, **due this week**, **closure velocity**, etc.
- **CSV** and **Excel** export.
- **Date display** follows Settings → Date format in the UI; **exports use ISO `yyyy-MM-dd`** for spreadsheet sorting regardless of display setting.

---

## Holidays

- User-maintained **business holiday** list used by recurrence and business-day calculations.

---

## Activity and audit

- **Field-level audit** trail for task changes.
- **Activity** panel combines audit events and note activity for a unified timeline.

---

## Notifications

- Desktop notifications for selected events (see user guide for scope and behavior).

---

## View menu

- **Theme:** Light / dark / system — applies application-wide immediately; persisted to `ui_settings.json`.

---

## Settings

All below are under the **Settings** menu unless noted.

| Item | Purpose |
|------|---------|
| Customize task panel layout… | Reorder inline sections (Todos, Blockers, Recurring) and tabs (Notes, Activity). Per vault → `ui_settings.json`. |
| Keyboard shortcuts… | New Task, Save Task, Close Task. |
| Date format… | Display-only format across UI (pickers, lists, reports, bulk-shift preview). Exports stay ISO. |
| Display timezone… | How dates/times are interpreted for display. |
| Text size… | UI text scaling. |
| Task templates… | Template CRUD and JSON I/O. |
| Manage / Export / Import categories and people… | Taxonomy and people master data; JSON for vault sync. |
| Switch vault… | Change vault folder (also available from File / startup flow). |

---

## Help

- **User guide** — embedded HTML; includes “My notes” editor for `personal_usage.html`.

---

## Roadmap features (not in this catalog until shipped)

Items covered by `plans/05_*.md` onward (quick capture, tags, child tasks, effort/time, external links, inbox actions, reminders/aging, board, intake, safety net) should be added **here** when their plan lands, alongside `user_guide.html` and `tech_decisions.md`.

---

## Suggested update checklist (per change)

1. User-facing steps → `user_guide.html`.
2. Capability inventory / storage / entry points → this file (`FEATURE_GUIDE.md`).
3. Non-obvious rationale → `tech_decisions.md`.
4. Plan doc → tick “Docs to update on landing” including the `FEATURE_GUIDE.md` line.
