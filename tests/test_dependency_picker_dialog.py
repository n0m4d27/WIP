from __future__ import annotations

from tasktracker.ui.dependency_picker_dialog import DependencyCandidate, candidate_matches_query


def test_candidate_matches_empty_query() -> None:
    c = DependencyCandidate(task_id=1, ticket_number=42, title="Reset account lock", status="open")
    assert candidate_matches_query(c, "") is True


def test_candidate_matches_by_ticket_and_title_case_insensitive() -> None:
    c = DependencyCandidate(task_id=1, ticket_number=42, title="Reset account lock", status="open")
    assert candidate_matches_query(c, "T42") is True
    assert candidate_matches_query(c, "42") is True
    assert candidate_matches_query(c, "ACCOUNT") is True
    assert candidate_matches_query(c, "printer") is False
