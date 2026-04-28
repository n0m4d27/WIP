from __future__ import annotations

from tasktracker.ui.parent_picker_dialog import ParentCandidate, parent_candidate_matches_query


def test_parent_candidate_matches_empty_query() -> None:
    c = ParentCandidate(task_id=1, ticket_number=42, title="Reset account lock", status="open")
    assert parent_candidate_matches_query(c, "") is True


def test_parent_candidate_matches_by_ticket_and_title_case_insensitive() -> None:
    c = ParentCandidate(task_id=1, ticket_number=42, title="Reset account lock", status="open")
    assert parent_candidate_matches_query(c, "T42") is True
    assert parent_candidate_matches_query(c, "42") is True
    assert parent_candidate_matches_query(c, "ACCOUNT") is True
    assert parent_candidate_matches_query(c, "printer") is False
