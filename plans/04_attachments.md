# Plan 04 - Attachments

## Goal

First-class file attachments per task (PDFs, screenshots, spreadsheets,
emails), stored inside the vault folder and encrypted at rest alongside the
database.

## Problem it solves

- Analyst work depends on screenshots, xlsx, pdf, and `.msg` context. Today
  those can only be pasted into rich-text notes, which is clunky for anything
  bigger than a paragraph and lossy for binary formats.
- Without attachments, the vault cannot be the single source of truth; the
  user ends up with a parallel file tree elsewhere, which defeats the purpose.

## In scope

- New `TaskAttachment` entity capturing: task_id, original file name,
  content-addressed storage path inside the vault, MIME hint, size in bytes,
  uploaded_at, uploaded-from note (optional).
- Attachments stored as files under `<vault>/attachments/<task_id>/<sha>_<name>`.
- Encryption-at-rest parity with the DB: the attachments folder is included in
  the vault re-encrypt routine on shutdown and decrypt routine on open, using
  the same password-derived key. (Implementation detail: either encrypt each
  file individually or tar+encrypt the folder — decide during planning.)
- Attachments list inline on the task panel (new section, respecting the
  existing inline-vs-tab placement pattern).
- Actions: Add (file picker, multi-select), Remove, Open (launch via OS
  default handler from a temp location — decrypted on demand), Rename
  original display name.
- Size guardrails: per-file soft cap (e.g. 100 MB) with a warning; per-task
  attachment count surfaced as a small badge.

## Out of scope

- Preview rendering inside the app for PDFs or images (opens externally).
- Attachments on anything other than tasks (no attachments on todos, blockers,
  notes). Could revisit.
- Cloud-backed storage (e.g. SharePoint mirroring). Vault-local only.
- Content-based indexing of attachment text (not in FTS).

## Schema / data model changes

- `task_attachments` table:
  - `id`, `task_id` (FK CASCADE), `display_name`, `storage_relpath` (relative
    to the vault root), `content_sha256`, `size_bytes`, `mime_hint`,
    `created_at`.
- Filesystem convention: `<vault>/attachments/<task_id>/<sha>_<safe_name>`.
- Vault lifecycle: the encrypt / decrypt flow learns about the `attachments/`
  subtree. A companion `attachments_manifest.json` at the vault root may be
  useful for verifying integrity at open-time.

## Code touch list (expected files)

- `tasktracker/db/models.py` — `TaskAttachment`.
- `tasktracker/db/schema_upgrade.py` — create table.
- `tasktracker/services/task_service.py` (or new
  `tasktracker/services/attachment_service.py`) — add, remove, get_path,
  verify_integrity.
- Vault lifecycle code (`auth_dialogs.py` / `__main__.py` / any
  vault encrypt helper) — fold the attachments subtree into encrypt / decrypt.
- `tasktracker/ui/main_window.py` — attachments section placement registration.
- New module `tasktracker/ui/attachments_panel.py` — list widget and drop
  target.
- `tasktracker/paths.py` — helper for `attachments_dir(vault_root)` and
  `decrypted_temp_dir()` where "open externally" stages the file.
- `tests/test_attachments.py` (new) — add / remove / integrity,
  encrypt-decrypt round-trip, orphan detection.

## Work breakdown

- [x] Model + upgrade step.
- [x] Storage layout helpers (path builder, collision handling, sha check).
- [x] Service methods: `add_attachment(task_id, source_path) -> TaskAttachment`,
      `remove_attachment(id)`, `materialize_for_open(id) -> Path`.
- [x] Decide encryption granularity (per-file vs folder-tar). Implement and
      unit-test the round-trip.
- [x] Wire vault startup to decrypt attachments alongside the DB.
- [x] Wire vault shutdown to re-encrypt attachments alongside the DB.
- [x] Attachments panel widget (list, drag-drop, Add / Remove / Open).
- [x] Integrate panel into task detail with inline-vs-tab placement respecting
      `TASK_SECTION_PLACEMENT`.
- [x] Temp file cleanup on app exit (no stray decrypted files left on disk).
- [x] Tests covering add, remove, open round-trip, and crash mid-shutdown (no
      corruption).

## Validation checklist

- [x] Adding a 5 MB PDF, closing the vault, reopening, and opening the
      attachment yields the same bytes (sha check).
- [x] Removing an attachment deletes both the DB row and the on-disk file.
- [x] Deleting a task cascades to its attachments (rows and files).
- [x] An attachment stored while the app was unlocked is **not** readable on
      disk when the vault is closed (bytes differ from plaintext).
- [x] App exit cleans up any decrypted temp files opened externally during
      the session.
- [x] Encrypt / decrypt flow is robust to interrupted shutdown (plan for
      recovery on next open).
- [x] Existing test suite green.

## Docs to update on landing

- [x] `tech_decisions.md` — encryption granularity decision, storage layout,
      interaction with vault lifecycle.
- [x] `tasktracker/resources/user_guide.html` — new Attachments section +
      note in the security / vault section.
- [x] `plans/README.md` — mark Done, log follow-ups / bugs.
- [x] `FEATURE_GUIDE.md` — attachments capability, storage, UI entry points.

## Risks / open questions

- **NAS throughput.** Large attachments over SMB will be slow; display a
  progress indicator on add / open.
- **Integrity on crash mid re-encrypt.** Mitigation: write ciphertext to a
  sibling temp path, fsync, then rename into place. Verify manifest on open.
- **Duplicate files across tasks.** The content-addressed storage allows
  future dedup, but MVP keeps one physical file per attachment row for simple
  delete semantics.
- **Open-externally leak risk.** The decrypted temp directory must be a
  user-local, app-private folder (not NAS).

## Follow-ups discovered

_(empty at start of plan)_
