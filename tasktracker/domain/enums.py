from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class RecurrenceGenerationMode(StrEnum):
    ON_CLOSE = "on_close"
    SCHEDULED = "scheduled"
