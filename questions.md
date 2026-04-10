# Questions

**Product and technical choices are captured in `tech_decisions.md`.** This file is a short index; use it to see what was decided and where.

---

## Resolved (summary)

| Topic | Decision |
|--------|-----------|
| Recurring generation timing | **Configurable per rule:** on close **or** scheduled job |
| Weekends/holidays | **Skip both**; **user-maintained business holiday list** |
| Next instance todos | **Template** configured with the recurring task |
| Closed tasks | **Always allow** notes/edits |
| Status set | Add **`on_hold`**, **`cancelled`** |
| Priority | **OOTB ServiceNow** Impact × Urgency (1–3 each) → Priority P1–P5; **matrix utility** UI; **no priority override**; auto-recalc; **audit + note** when priority changes; **show all three** fields |
| Blockers | **Option A:** separate **`TaskBlocker`** rows |
| Milestones / order | **Sequential** with **manual reorder** |
| Performance + APR | **Phase 2** |
| Notes | **Rich text** MVP1; **editable** + **version history** |
| Calendar views | **Month** default; **week** + **agenda** optional |
| Calendar overlays | **Toggles** for all types; **default ON:** due + todo milestones; **default OFF:** received + closed |
| Closed on calendar | **Hidden by default**; **toggle** to show |
| Calendar visuals | **One color per type**, **legend**; **priority** signaled on tasks; **sort within day by priority** |
| DnD on calendar | **MVP1** |
| Deployment | Single-user desktop; DB file may sit on **NAS**; **offline-first**; **no shared multi-user DB server** for v1 |
| Reports | **Overdue**, **due this week**, **closure velocity** — all early |
| Export | **CSV + Excel** MVP1 |
| Audit + activity | **Field audit** + **notes**; **combined** timeline/query |
| Business holidays | **User-maintained data** for skip rules (confirmed) |

---

## If new questions come up

Add them here as a bullet list, then fold answers into `tech_decisions.md` when resolved.
