from __future__ import annotations

from datetime import datetime, timezone

from isotope.features.supervisor.state.failure_ledger import FailureLedger


def test_failure_ledger_records_required_fields_and_retry_count(tmp_path):
    ledger = FailureLedger(tmp_path / "failure_events.jsonl")
    now = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)

    first = ledger.record_failure(
        event_type="llm_planner_invalid_response",
        lane_name="lane-a",
        goal_id="goal-123",
        error_summary="LLM action must be a JSON object",
        now=lambda: now,
    )
    second = ledger.record_failure(
        event_type="llm_planner_invalid_response",
        lane_name="lane-a",
        goal_id="goal-123",
        error_summary="LLM action must be a JSON object",
        now=lambda: now,
    )
    other_lane = ledger.record_failure(
        event_type="llm_planner_invalid_response",
        lane_name="lane-b",
        goal_id="goal-123",
        error_summary="LLM action must be a JSON object",
        now=lambda: now,
    )

    assert first == {
        "timestamp": "2026-05-21T09:00:00+00:00",
        "event_type": "llm_planner_invalid_response",
        "lane_name": "lane-a",
        "goal_id": "goal-123",
        "error_summary": "LLM action must be a JSON object",
        "retry_count": 1,
    }
    assert second["retry_count"] == 2
    assert other_lane["retry_count"] == 1
    assert ledger.read_recent(limit=10) == (other_lane, second, first)
