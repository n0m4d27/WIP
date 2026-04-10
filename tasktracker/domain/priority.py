from __future__ import annotations

# OOTB ServiceNow-style: Impact 1–3 (High→Low), Urgency 1–3 → Priority 1–5
# Rows: Impact, Cols: Urgency
_PRIORITY_MATRIX: tuple[tuple[int, ...], ...] = (
    (1, 2, 3),  # Impact 1 High
    (2, 3, 4),  # Impact 2 Medium
    (3, 4, 5),  # Impact 3 Low
)

PRIORITY_LABELS: dict[int, str] = {
    1: "Critical",
    2: "High",
    3: "Moderate",
    4: "Low",
    5: "Planning",
}


def compute_priority(*, impact: int, urgency: int) -> int:
    """Return priority P1–P5 from 1-based Impact and Urgency (each 1–3)."""
    if impact not in (1, 2, 3) or urgency not in (1, 2, 3):
        raise ValueError("impact and urgency must each be 1, 2, or 3")
    return _PRIORITY_MATRIX[impact - 1][urgency - 1]


def priority_display(priority: int) -> str:
    label = PRIORITY_LABELS.get(priority, "?")
    return f"P{priority} {label}"
