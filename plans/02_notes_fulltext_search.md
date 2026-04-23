# Plan 02 - Notes full-text search

## Goal

Make search reach into the content of notes and task descriptions — not just
titles — using SQLite's built-in FTS5 extension so the existing search bar
surfaces tasks whose context lives in the notes stream.

## Problem it solves

- `TaskService.search_tasks` today matches on title / description only.
- Rich-text notes carry most of the real context (what was tried, what the
  stakeholder said, why a decision was made) and currently cannot be searched.
- Once the vault grows past a few hundred tasks, finding a thread by its
  content becomes the dominant search mode.

## In scope

- Create a `task_search_fts` FTS5 virtual table that indexes, per task, the
  normalized plain-text content of:
  - `Task.title`
  - `Task.description`
  - All `TaskNoteVersion.body_html` (latest version per note) with HTML
    stripped to plain text.
- Triggers (or a service-layer writer — decide during implementation) keep the
  FTS table in sync on insert / update / delete for tasks, notes, and note
  versions.
- Search path: `search_tasks` uses FTS5 MATCH when the user's query is
  non-trivial, falls back to LIKE for short / punctuation-heavy queries.
- Snippet support: return a short highlighted excerpt per hit so the Tasks
  list (or a dedicated search results area) can show *why* each result
  matched.
- One-time backfill on schema upgrade to populate FTS from existing data.

## Out of scope

- Search over blockers, activity log, attachment file names. Possible
  follow-ups, each adds indexing surface.
- Tag-filtered search (covered by plan 06).
- A standalone search results tab. Keep the Tasks tab as the results surface.
- Custom ranking beyond FTS5's default BM25.

## Schema / data model changes

- Virtual table:
  ```sql
  CREATE VIRTUAL TABLE task_search_fts USING fts5(
    task_id UNINDEXED,
    title,
    description,
    notes,
    tokenize = 'porter unicode61 remove_diacritics 2'
  );
  ```
- Triggers on `tasks`, `task_notes`, `task_note_versions` (or a single
  service-layer sync function called from `TaskService` write paths — pick one
  during implementation).
- `schema_upgrade.py`: create the virtual table, install triggers, backfill
  rows from existing data. Upgrade is idempotent.

## Code touch list (expected files)

- `tasktracker/db/schema_upgrade.py` — new upgrade step for FTS creation +
  backfill; safe to re-run.
- `tasktracker/services/task_service.py` — `search_tasks` branch to FTS path;
  helper for HTML-to-text normalization; sync hooks in note / description /
  title writes.
- `tasktracker/ui/main_window.py` — search bar may gain a tooltip explaining
  that note content is searchable.
- `tests/test_search_fts.py` (new) — coverage for backfill, trigger sync, HTML
  stripping, FTS vs LIKE fallback.
- Existing `tests/test_task_service.py` — extend with note-content search
  cases; confirm existing tests still pass.

## Work breakdown

- [x] Add HTML-to-plaintext helper (handle the subset Qt rich text emits).
- [x] Write schema upgrade step that creates `task_search_fts` and backfills.
- [x] Decide: SQL triggers vs service-layer sync. Implement the chosen
      approach; prefer service-layer for testability unless triggers clearly
      win.
- [x] Extend `search_tasks` to MATCH on FTS for multi-term queries; keep LIKE
      fallback for single-char / punctuation queries.
- [x] Return snippets (FTS5 `snippet()` function) with the rows so the UI can
      display hit context.
- [x] UI pass: surface snippets in task list tooltips or a small results
      detail area (minimal; don't redesign the list).
- [x] Unit tests for each above piece.
- [x] Migration / smoke test: open a pre-plan vault, run the upgrade, verify
      FTS populated and search works.

## Validation checklist

- [x] FTS virtual table exists and row count equals `select count(*) from tasks`.
- [x] Inserting a new task, editing a description, adding / editing a note all
      keep FTS in sync without manual rebuild.
- [x] Deleting a task removes its FTS row. *(``TaskService.delete_task`` removes the task and FTS row; UI may expose delete later.)*
- [x] Search for a term appearing only in note content returns the task.
- [x] Search for a term appearing only in title still works (regression).
- [x] Multi-term search uses FTS (visible via snippet); single-char query
      still falls back to LIKE.
- [x] Backfill is idempotent — running the upgrade twice produces no dupes.
- [x] Existing `tests/test_task_service.py` suite is green.

## Docs to update on landing

- [x] `tech_decisions.md` — note the FTS5 adoption, why we chose FTS5 over
      raw LIKE, and the sync strategy (trigger vs service).
- [x] `tasktracker/resources/user_guide.html` — update the Search section so
      users know notes are now indexed.
- [x] `plans/README.md` — mark Done, log follow-ups / bugs.
- [x] `FEATURE_GUIDE.md` — Search + FTS / note indexing behavior.

## Risks / open questions

- **HTML normalization fidelity.** Qt's rich-text HTML has quirks; we want to
  strip tags without dropping stylized-but-meaningful whitespace. Write tests
  against real emitted HTML.
- **Index size.** FTS5 on note bodies can double the DB size. Acceptable for
  single-user vaults; monitor during validation.
- **Trigger vs service sync.** Triggers are atomic and free of app-side bugs;
  service-layer sync is easier to test and to extend. Pick one and document.
- **Re-encrypt implications.** FTS adds more pages but still lives inside
  `tasks.db`, so the encrypted-vault story is unchanged.

## Follow-ups discovered

| Item | Notes |
|------|-------|
| Task delete in UI | Service method `delete_task` exists; optional menu / context-menu exposure is a small follow-up if users need it. |
