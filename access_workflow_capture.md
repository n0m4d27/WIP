# Access DB workflow capture

> Private working doc. Fill sections in as things come to mind — it does not
> have to be complete before it is useful. The purpose is to make the
> invisible knowledge in your head (how you actually use the Access DB day to
> day) visible enough that the Task Tracker roadmap can be shaped around it.
>
> Everything here is an input to future plans. When a section sparks an idea
> that belongs in a specific plan under `plans/`, add a bullet there and link
> back from here.

---

## 1. The Access DB at a glance

- Rough table list and what each one holds:
- Ballpark record count per table:
- How long have you been using this DB:
- Who else sees it (read-only shares, exports, screenshots in decks):
- Where does the `.accdb` live today (local disk, NAS, OneDrive):

## 2. A typical day

Walk through a normal workday. Stream of consciousness is fine.

- First thing you open Access for in the morning:
- Where do new work items arrive from (email, Teams, IM, verbal, ticket
  system, walk-ups):
- Where do they land first before Access (notebook, sticky, email flag,
  Excel, nowhere):
- What do you do with Access at the end of the day:
- Anything you consistently forget to do:

## 3. A typical week

- Standing reports you produce (who they go to, what form):
- Monday morning ritual:
- End-of-week close-out:
- Anything that fires only on a specific weekday:

## 4. Recurring work categories

For each big bucket, jot notes. Add or drop buckets freely.

### Headcount
- Cadence (daily, weekly, monthly, per-request):
- Typical fields / attributes you capture:
- Typical lifespan of an item from intake to close:
- What "done" looks like:

### Workforce management
- Cadence:
- Typical fields:
- Typical lifespan:
- What "done" looks like:

### Staffing
- Cadence:
- Typical fields:
- Typical lifespan:
- What "done" looks like:

### Ad-hoc projects
- Cadence:
- Typical fields:
- Typical lifespan:
- What "done" looks like:

### Other
-

## 5. Pain points with Access (be specific)

- Things that are slow:
- Things that silently break (e.g. a query you only notice returned wrong
  results later):
- Things that are easy to forget or lose:
- Things you have worked around with external files (Excel alongside Access,
  Word docs, OneNote, sticky notes):
- Things that do not scale (forms that choke past N records, queries that
  hang, report layouts that break):
- Things you cannot do because the DB is access-limited (no macros, no
  admin, no linked tables):

## 6. What Access does well (do not lose these)

- Features or behaviors you would miss if you migrated away:
- Report layouts worth keeping:
- Form patterns that are pleasant to use:

## 7. Reports and queries you run

| Name | Frequency | Inputs | Output shape | Who sees it |
|------|-----------|--------|--------------|-------------|
|      |           |        |              |             |
|      |           |        |              |             |

## 8. Fields you cannot live without

- Custom fields in Access that must come over to Task Tracker:
- Conventions or lookup values (even informal ones, like color codes on a
  combo box):
- Default values / calculated fields that quietly carry a lot of load:

## 9. Migration thinking

- Is there historical data worth bringing over, or is this a clean start:
- If migrating, one-shot dump or phased ("new items here, old items stay in
  Access"):
- Cutover risks (people who depend on Access views directly, embedded links
  in emails, scheduled jobs that read the file):
- Deadline pressure (any specific date the move must happen by):

## 10. Things I wish Access did

Feed these directly into the Task Tracker roadmap. When one of these maps
onto an existing plan under `plans/`, add a bullet there and reference it
here.

-
-
-

---

## Cross-references to plans

As you fill this in, note which plans each observation influences. Example:

- _"Intake comes from Outlook with `.msg` forwards" -> plan 13
  (intake and migration)._
- _"Three months of historical tasks should migrate one-shot" -> plan 13
  (CSV import path)._
- _"Would like to group 'Q1 Staffing' items across areas" -> plan 06 (tags)._
