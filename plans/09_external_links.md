# Plan 09 - External links

## Goal

Add a first-class collection of external links per task so SharePoint URLs,
Databricks query IDs, Outlook message links, ticket URLs from other systems,
and similar references are structured rather than buried in descriptions.

## Problem it solves

- Analyst work lives in a constellation of other tools. Today, the only way
  to pin that context is to paste URLs into the description or a note —
  where they lose structure and become hard to click, label, or maintain.
- A dedicated link row with a label and a URL gives tasks a stable "see
  also" surface.

## In scope

- New `TaskLink` entity: `task_id`, `label`, `url`, `sort_order`,
  `created_at`.
- Links panel on the task detail (inline section, compact; one row per link).
- Add / edit / remove / reorder actions.
- Click-to-open uses `QDesktopServices.openUrl` (OS default handler).
- Link validation at save time: must be a non-empty URL with a recognized
  scheme (`http://`, `https://`, `file://`, `mailto:`, `msg://`, plus a
  short configurable allow-list).

## Out of scope

- Link previews / unfurling (no metadata fetch).
- Per-link permissions / ACL.
- Automatic link extraction from descriptions or notes.
- Outlook COM-based "save the current email as a link" (falls under plan 13
  email drop).

## Schema / data model changes

- `task_links`:
  - `id`, `task_id` (FK CASCADE), `label` VARCHAR(300) NOT NULL,
    `url` VARCHAR(2048) NOT NULL, `sort_order` INT NOT NULL DEFAULT 0,
    `created_at` DATETIME NOT NULL.
- Schema upgrade creates the table idempotently.

## Code touch list (expected files)

- `tasktracker/db/models.py` — `TaskLink`.
- `tasktracker/db/schema_upgrade.py` — create table.
- `tasktracker/services/task_service.py` — CRUD + reorder.
- New widget `tasktracker/ui/links_panel.py` — table with Add / Edit /
  Remove / Move up / Move down.
- `tasktracker/ui/main_window.py` — register the Links section in
  `TASK_SECTION_PLACEMENT`.
- `tests/test_task_links.py` (new).

## Work breakdown

- [ ] Model + upgrade.
- [ ] Service CRUD + reorder.
- [ ] URL validation helper (small, stdlib-only; no new dependency).
- [ ] Links panel widget.
- [ ] Section registration for inline-vs-tab placement.
- [ ] Tests: CRUD, reorder, validation, open-url plumbing (unit test the
      URL-opening call site, not the OS shell).

## Validation checklist

- [ ] Adding three links preserves insertion order; Move up / Move down
      persists the new order.
- [ ] Invalid URL (e.g. `ftp://something` if not in the allow-list) is
      rejected at save.
- [ ] Deleting a task cascades to its links.
- [ ] Existing test suite green.

## Docs to update on landing

- [ ] `tech_decisions.md` — note the scheme allow-list and why link unfurl
      is explicitly out of scope.
- [ ] `tasktracker/resources/user_guide.html` — "External links" section.
- [ ] `plans/README.md` — mark Done, log follow-ups / bugs.
- [ ] `FEATURE_GUIDE.md` — external links feature and constraints.

## Risks / open questions

- **Scheme allow-list scope.** Start small; widen only on real need.
- **URL length.** 2048 is plenty for most cases, but some SharePoint URLs
  push limits. Consider TEXT instead if trimming would be lossy.
- **Open-externally for `file://` paths.** On Windows, `file://` links to
  NAS shares are handy but may hang on disconnected shares — document.

## Follow-ups discovered

_(empty at start of plan)_
