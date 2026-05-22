from __future__ import annotations

from datetime import datetime, timezone

from isotope.platform.state.decision_ledger import DecisionRequest, DecisionRequestLedger
from isotope.platform.state.failure_ledger import FailureLedger


def test_decision_request_ledger_tracks_active_requests_and_recent_answers(tmp_path):
    ledger = DecisionRequestLedger(tmp_path / "decision_requests.jsonl")
    request = DecisionRequest(
        request_id="decision-001",
        created_at="2026-05-22T08:00:00+00:00",
        session_id="session-a",
        target_name="lane-a",
        question="继续还是暂停？",
        reason="需要用户拍板。",
        context_status="conflict",
        gate={"codex_requested_decision": True},
        goal_id="goal-a",
    )

    ledger.append_request(request)
    answer = ledger.append_answer(
        request=request,
        answer="继续迁移账本边界。",
        now=lambda: datetime(2026, 5, 22, 8, 5, tzinfo=timezone.utc),
    )

    assert ledger.read_active_requests() == ()
    assert ledger.read_recent_answers() == (answer,)


def test_failure_ledger_records_retry_count_in_platform_state(tmp_path):
    ledger = FailureLedger(tmp_path / "failure_events.jsonl")
    now = datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc)

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

    assert first["retry_count"] == 1
    assert second["retry_count"] == 2
    assert ledger.read_recent(limit=2) == (second, first)
