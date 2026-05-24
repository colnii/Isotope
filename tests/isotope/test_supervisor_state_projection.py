from __future__ import annotations

import json
from datetime import UTC, datetime

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.decision_requests import record_decision_request
from isotope.features.supervisor.goal_queue import (
    record_supervisor_goal,
    record_supervisor_goal_status,
)
import isotope.features.supervisor.goal_queue as feature_goal_queue
import isotope.features.supervisor.lane_state as feature_lane_state
from isotope.features.supervisor.lane_state import record_lane_failure
from isotope.features.supervisor.runner import main as supervisor_main
import isotope.features.supervisor.state.projection as feature_projection
from isotope.platform.state.active_goal import SupervisorActiveGoal
from isotope.platform.state.decision_ledger import DecisionRequest
from isotope.platform.state.decision_request import SupervisorDecisionRequest
from isotope.platform.state.goal_status import SupervisorGoalStatus
from isotope.platform.state.lane_state import SupervisorLaneState
from isotope.platform.state.notification_summary import SupervisorNotificationSummary
from isotope.platform.state.supervisor_snapshot import SupervisorStateSnapshot
from isotope.features.supervisor.state.projection import build_supervisor_state_snapshot
from isotope.memory.worker_event_channel import publish_worker_event


def test_supervisor_state_projection_uses_platform_snapshot_schema(tmp_path):
    assert feature_projection.SupervisorStateSnapshot is SupervisorStateSnapshot

    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot == SupervisorStateSnapshot.empty(codex_home=tmp_path).to_dict()


def test_supervisor_goal_status_uses_platform_schema():
    assert feature_goal_queue.SupervisorGoalStatus is SupervisorGoalStatus

    status = SupervisorGoalStatus(
        goal_id="goal-1",
        status="blocked",
        created_at="2026-05-24T02:02:00+00:00",
        target_name="state-projection",
        session_id="session-goal",
        summary="等待主线重构完成",
        next_step="保持 projection 分支独立",
    )

    assert status.to_latest_payload() == {
        "goal_id": "goal-1",
        "last_status": "blocked",
        "last_status_at": "2026-05-24T02:02:00+00:00",
        "last_target_name": "state-projection",
        "last_session_id": "session-goal",
        "last_summary": "等待主线重构完成",
        "last_next": "保持 projection 分支独立",
    }


def test_supervisor_active_goal_uses_platform_schema():
    assert feature_projection.SupervisorActiveGoal is SupervisorActiveGoal

    goal = SupervisorActiveGoal(
        goal_id="goal-1",
        created_at="2026-05-24T02:01:00+00:00",
        cwd="/repo",
        goal="继续拆分 Supervisor 状态读取模型",
        target_name="state-projection",
        depends_on=("goal-0",),
        stage="projection",
        scope="supervisor",
        merge_gate="manual",
    )
    status = SupervisorGoalStatus(
        goal_id="goal-1",
        status="blocked",
        created_at="2026-05-24T02:02:00+00:00",
        target_name="state-projection",
        session_id="session-goal",
        summary="等待主线重构完成",
        next_step="保持 projection 分支独立",
    )

    assert goal.to_state_payload(latest_status=status.to_latest_payload()) == {
        "goal_id": "goal-1",
        "created_at": "2026-05-24T02:01:00+00:00",
        "cwd": "/repo",
        "goal": "继续拆分 Supervisor 状态读取模型",
        "target_name": "state-projection",
        "depends_on": ["goal-0"],
        "stage": "projection",
        "scope": "supervisor",
        "merge_gate": "manual",
        "last_status": "blocked",
        "last_status_at": "2026-05-24T02:02:00+00:00",
        "last_target_name": "state-projection",
        "last_session_id": "session-goal",
        "last_summary": "等待主线重构完成",
        "last_next": "保持 projection 分支独立",
    }


def test_supervisor_decision_request_uses_platform_schema():
    assert feature_projection.SupervisorDecisionRequest is SupervisorDecisionRequest

    request = DecisionRequest(
        request_id="decision-1",
        created_at="2026-05-24T01:02:00+00:00",
        session_id="session-1",
        target_name="worker-a",
        question="是否继续合并？",
        reason="worker 需要用户确认",
        context_status="conflict",
        gate={"raw_prompt": "RAW_PROMPT_SHOULD_NOT_LEAK"},
        goal_id="goal-1",
    )

    assert SupervisorDecisionRequest.from_ledger_request(request).to_state_payload() == {
        "request_id": "decision-1",
        "session_id": "session-1",
        "target_name": "worker-a",
        "goal_id": "goal-1",
        "question": "是否继续合并？",
        "reason": "worker 需要用户确认",
        "context_status": "conflict",
        "created_at": "2026-05-24T01:02:00+00:00",
    }


def test_supervisor_lane_state_uses_platform_schema():
    assert feature_lane_state.LaneState is SupervisorLaneState

    state = SupervisorLaneState(
        name="worker-a",
        tmux_session=None,
        last_status="failed",
        last_failure_reason="exit_code",
        last_failure_exit_code=1,
        last_failure_stderr_summary="pytest failed",
        last_failure_record_id="managed-1",
        last_failed_at="2026-05-24T01:03:00+00:00",
        failure_count=1,
        worker_retry_count=2,
    )

    assert state.to_failed_lane_payload() == {
        "name": "worker-a",
        "last_failure_reason": "exit_code",
        "last_failure_exit_code": 1,
        "last_failure_stderr_summary": "pytest failed",
        "last_failure_record_id": "managed-1",
        "last_failed_at": "2026-05-24T01:03:00+00:00",
        "failure_count": 1,
        "worker_retry_count": 2,
    }


def test_supervisor_notification_summary_uses_platform_schema():
    assert feature_projection.SupervisorNotificationSummary is SupervisorNotificationSummary

    summary = SupervisorNotificationSummary(
        notification_id="notif-manual",
        notification_type="manual",
        title="人工提醒",
        unread=True,
        created_at="2026-05-24T01:04:00+00:00",
        read_at=None,
        source_ref={
            "ref_type": "supervisor_run",
            "run_id": "run-1",
            "timeout_seconds": 30,
            "raw_prompt": "RAW_PROMPT_SHOULD_NOT_LEAK",
            "api_key": "sk-test-secret",
            "nested": {"run_id": "nested-run"},
        },
    )

    assert summary.to_state_payload() == {
        "notification_id": "notif-manual",
        "type": "manual",
        "title": "人工提醒",
        "unread": True,
        "created_at": "2026-05-24T01:04:00+00:00",
        "read_at": None,
        "source_ref": {
            "ref_type": "supervisor_run",
            "run_id": "run-1",
            "timeout_seconds": 30,
        },
    }


def test_supervisor_state_snapshot_empty_root_is_read_only(tmp_path):
    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot == {
        "status": "ok",
        "kind": "supervisor_state_snapshot",
        "schema_version": 1,
        "codex_home": str(tmp_path),
        "summary": {
            "active_goals": 0,
            "goals_done": 0,
            "goals_blocked": 0,
            "goals_needs_user": 0,
            "active_decisions": 0,
            "failed_lanes": 0,
            "worker_events": 0,
            "notifications": 0,
            "unread_notifications": 0,
        },
        "active_goals": [],
        "active_decisions": [],
        "failed_lanes": [],
        "recent_worker_events": [],
        "notifications": {"total": 0, "unread": 0, "recent": []},
    }
    assert list(tmp_path.rglob("*")) == []


def test_supervisor_state_snapshot_projects_existing_low_sensitive_state(tmp_path):
    record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-1",
            "target_name": "worker-a",
            "question": "是否继续合并？",
            "reason": "worker 需要用户确认",
            "context_status": "conflict",
            "gate": {"context_status": "conflict"},
        },
        now=lambda: datetime(2026, 5, 24, 1, 2, tzinfo=UTC),
    )
    record_lane_failure(
        codex_home=tmp_path,
        name="worker-a",
        tmux_session=None,
        reason="exit_code",
        exit_code=1,
        stderr_summary="pytest failed",
        record_id="managed-1",
        now=datetime(2026, 5, 24, 1, 3, tzinfo=UTC),
    )
    publish_worker_event(
        root=tmp_path,
        from_worker="worker-a",
        to_worker="worker-b",
        event_type="handoff",
        message="Ready for review.",
        payload={"branch": "feature/a"},
    )
    NotificationFlow(
        tmp_path,
        clock=lambda: datetime(2026, 5, 24, 1, 4, tzinfo=UTC),
        id_factory=lambda: "notif_manual",
    ).create_notification(
        notification_type="manual",
        title="人工提醒",
        source_ref={
            "ref_type": "supervisor_run",
            "run_id": "run-1",
            "raw_prompt": "RAW_PROMPT_SHOULD_NOT_LEAK",
            "api_key": "sk-test-secret",
        },
    )

    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot["summary"] == {
        "active_goals": 0,
        "goals_done": 0,
        "goals_blocked": 0,
        "goals_needs_user": 0,
        "active_decisions": 1,
        "failed_lanes": 1,
        "worker_events": 1,
        "notifications": 2,
        "unread_notifications": 2,
    }
    assert snapshot["active_decisions"] == [
        {
            "request_id": snapshot["active_decisions"][0]["request_id"],
            "session_id": "session-1",
            "target_name": "worker-a",
            "goal_id": None,
            "question": "是否继续合并？",
            "reason": "worker 需要用户确认",
            "context_status": "conflict",
            "created_at": "2026-05-24T01:02:00+00:00",
        }
    ]
    assert snapshot["failed_lanes"] == [
        {
            "name": "worker-a",
            "last_failure_reason": "exit_code",
            "last_failure_exit_code": 1,
            "last_failure_stderr_summary": "pytest failed",
            "last_failure_record_id": "managed-1",
            "last_failed_at": "2026-05-24T01:03:00+00:00",
            "failure_count": 1,
            "worker_retry_count": 0,
        }
    ]
    assert snapshot["recent_worker_events"][0]["from_worker"] == "worker-a"
    assert snapshot["recent_worker_events"][0]["to_worker"] == "worker-b"
    assert snapshot["recent_worker_events"][0]["event_type"] == "handoff"
    assert snapshot["recent_worker_events"][0]["payload"] == {"branch": "feature/a"}
    assert snapshot["notifications"]["total"] == 2
    assert snapshot["notifications"]["unread"] == 2
    assert [item["type"] for item in snapshot["notifications"]["recent"]] == [
        "supervisor_decision_request",
        "manual",
    ]
    assert snapshot["notifications"]["recent"][1]["source_ref"] == {
        "ref_type": "supervisor_run",
        "run_id": "run-1",
    }
    assert "content" not in repr(snapshot)
    assert "RAW_PROMPT_SHOULD_NOT_LEAK" not in repr(snapshot)
    assert "sk-test-secret" not in repr(snapshot)


def test_supervisor_state_snapshot_includes_active_goal_status_summary(tmp_path):
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="继续拆分 Supervisor 状态读取模型",
        target_name="state-projection",
        stage="projection",
        scope="supervisor",
        merge_gate="manual",
        now=lambda: datetime(2026, 5, 24, 2, 1, tzinfo=UTC),
    )
    record_supervisor_goal_status(
        codex_home=tmp_path,
        goal_id=goal.goal_id,
        status="blocked",
        target_name="state-projection",
        session_id="session-goal",
        summary="等待主线重构完成",
        next_step="保持 projection 分支独立",
        now=lambda: datetime(2026, 5, 24, 2, 2, tzinfo=UTC),
    )

    snapshot = build_supervisor_state_snapshot(codex_home=tmp_path)

    assert snapshot["summary"]["active_goals"] == 1
    assert snapshot["summary"]["goals_blocked"] == 1
    assert snapshot["summary"]["goals_done"] == 0
    assert snapshot["summary"]["goals_needs_user"] == 0
    assert snapshot["active_goals"] == [
        {
            "goal_id": goal.goal_id,
            "created_at": "2026-05-24T02:01:00+00:00",
            "cwd": str(tmp_path),
            "goal": "继续拆分 Supervisor 状态读取模型",
            "target_name": "state-projection",
            "depends_on": [],
            "stage": "projection",
            "scope": "supervisor",
            "merge_gate": "manual",
            "last_status": "blocked",
            "last_status_at": "2026-05-24T02:02:00+00:00",
            "last_target_name": "state-projection",
            "last_session_id": "session-goal",
            "last_summary": "等待主线重构完成",
            "last_next": "保持 projection 分支独立",
        }
    ]


def test_supervisor_state_command_outputs_snapshot_json(tmp_path, capsys):
    goal = record_supervisor_goal(
        codex_home=tmp_path,
        cwd=tmp_path,
        goal="统一 Supervisor 状态读取入口",
        target_name="state-command",
        now=lambda: datetime(2026, 5, 24, 3, 1, tzinfo=UTC),
    )

    exit_code = supervisor_main(
        ["state", "--codex-home", str(tmp_path), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "supervisor_state_snapshot"
    assert payload["schema_version"] == 1
    assert payload["summary"]["active_goals"] == 1
    assert payload["active_goals"][0]["goal_id"] == goal.goal_id
    assert payload["active_goals"][0]["target_name"] == "state-command"


def test_supervisor_state_command_plain_prints_compact_summary(tmp_path, capsys):
    record_decision_request(
        codex_home=tmp_path,
        action={
            "session_id": "session-1",
            "target_name": "worker-a",
            "question": "是否继续？",
            "reason": "需要拍板",
            "context_status": "needs_user",
        },
        now=lambda: datetime(2026, 5, 24, 3, 2, tzinfo=UTC),
    )

    exit_code = supervisor_main(["state", "--codex-home", str(tmp_path)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Supervisor state]" in text
    assert "状态快照：supervisor_state_snapshot v1" in text
    assert (
        "来源账本：goal queue / decision requests / lane state / "
        "worker events / notifications"
    ) in text
    assert "active goals：0" in text
    assert "decisions：1" in text
    assert "failed lanes：0" in text
    assert "notifications：1 / unread 1" in text
