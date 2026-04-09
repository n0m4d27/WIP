# Task Tracking App - Overview

## Purpose
Build a Python 3.11.2 task tracking app for work that supports:
- overarching tasks as the center of all activity
- recurring tasks with automated next-task generation
- date tracking across the task lifecycle
- note history with timestamps
- per-task todo milestones
- calendar-first planning and visibility

## Core Workflow
1. Create a task with required dates (`received_date`, `due_date`) and optional `close_target_date`.
2. Add todos to the task, each with an optional milestone date.
3. The task computes the "next milestone" from the nearest open todo milestone date.
4. Add timestamped notes to capture ongoing progress and context.
5. Complete/close the task with `closed_date` when work is done.
6. If task is recurring, automatically generate the next task iteration when the current task closes (or based on scheduling rule).

## Preliminary Relationship Model (from Access)
The Access diagram implies `Task` is the hub with one-to-many relationships to:
- `Notes`
- `Todo`
- `Blockers`
- `Updates` (audit/change history style table)

Other modeled relationships:
- `Performance` links to both `Task` and `APR` (reference/objective data).
- `RecurringTasks` exists as a scheduling definition linked conceptually to `Task` (diagram indicates a recurring entity centered on task identity/interval).

These relationships are retained as a baseline, but field names and normalization may evolve for Python implementation.

## Proposed Python Domain Objects (v1)
- `Task`
- `RecurringRule`
- `TodoItem`
- `TaskNote`
- `TaskBlocker`
- `TaskUpdateLog`
- `PerformanceLink` (optional in initial release)
- `APRReference` (optional in initial release)

## Date Handling Requirements
Each task should support at least:
- `received_date` (when assigned)
- `due_date` (expected delivery)
- `closed_date` (when actually closed; null until complete)
- `next_milestone_date` (derived from open todo items)

Todo items should support:
- `milestone_date` (optional but recommended for planning)
- `completed_at` (timestamp)

Notes should support:
- `created_at` timestamp
- immutable chronological ordering

## Recurring Task Behavior (initial policy)
- A recurring rule defines interval semantics (daily/weekly/monthly/custom days).
- Closing a recurring task triggers generation of the next task instance.
- New instance copies selected metadata (title/template description/owner/tags) and resets status fields/dates according to the rule.
- The closed task remains immutable for historical reporting.

## Calendar View Expectations
Calendar must display at minimum:
- task due dates
- upcoming todo milestone dates
- optional received and closed dates (filterable overlays)
- quick jump from date entry to task detail

## Non-Goals for Initial Version
- Full enterprise permissions model
- External integrations (email/Slack/Teams)
- Advanced analytics dashboards beyond basic calendar and task lists
