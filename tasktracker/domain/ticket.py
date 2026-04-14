"""Human-readable task reference (ServiceNow-style incremental ticket)."""

from __future__ import annotations


def format_task_ticket(ticket_number: int | None) -> str:
    """Display form ``T{n}`` (e.g. T0, T1). ``ticket_number`` is a monotonic integer per database."""
    if ticket_number is None:
        return "T—"
    return f"T{ticket_number}"
