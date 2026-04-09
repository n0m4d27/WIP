# Open Questions

## Product and Workflow
- Should recurring task generation happen:
  - immediately when task is closed, or
  - on a scheduled background job?
- Can recurring tasks skip weekends/holidays?
- Should the next recurring task inherit all open todos, or start with a template set?
- Do closed tasks allow post-close notes/edits, or are they locked?

## Status and Prioritization
- Final status set: do we keep `open/in_progress/blocked/closed`, or add `on_hold/cancelled`?
- How should priority be represented (numeric, enum, labels)?
- Should "next milestone" ignore overdue todos that are already past date?

## Data Model Clarifications
- Is `Performance` + `APR` required for MVP, or phase 2?
- Should blockers be separate rows (`TaskBlocker`) or represented as task status + note?
- Do updates need full field-level audit trail, or user-entered activity entries only?

## Notes Experience
- Must notes support rich text/markdown, or plain text only initially?
- Should notes be editable after creation, and if so, do we keep edit history?

## Calendar and Views
- Which default calendar granularity is most important: month, week, or agenda list?
- Should the calendar show received and closed dates, or only due/milestone dates by default?
- Need drag-and-drop date changes in calendar for MVP or later?

## Technical and Deployment
- Single-user local desktop app vs multi-user web app from day one?
- Is offline-first required?
- Preferred hosting target (local machine, internal server, cloud)?

## Reporting
- What minimum reports are needed early (overdue tasks, tasks due this week, closure velocity)?
- Do we need export to CSV/Excel in MVP?
