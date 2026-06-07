from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import shlex
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ..helpers import (
    CONTINUE_REQUEST_TEXT,
    EXISTING_WORKSPACE,
    NON_STALE_SECONDS,
    NOW,
    STATUS_REQUEST_TEXT,
    _add_supervisor_goal,
    _append_supervisor_goal_status,
    _assistant_message,
    _codex_operation_context_result,
    _event,
    _record_cleanup_lifecycle_execution,
    _runner_args,
    _supervisor_send_command,
    _tmux_send_calls,
    _user_message,
    _write_managed_tmux_record,
    _write_session,
    _write_session_index,
    _write_state_threads,
)
from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor import flow as supervisor_flow
from isotope.features.supervisor import runner as supervisor_runner
from isotope.features.supervisor.flow import (
    CodexSessionSummary,
    CodexSupervisorFlow,
    CodexSupervisorReport,
    render_plain_report,
)
from isotope.features.supervisor.llm_action.llm_summary import (
    PoolEntry,
    PooledSummaryProvider,
    build_llm_action_messages,
    build_llm_summary_messages,
    generate_llm_action_decision,
    generate_llm_summary,
    resolve_summary_provider_from_env,
)
from isotope.features.supervisor.merge.merge_dispatch import DEFAULT_TARGET_NAME
from isotope.features.supervisor.notifications.context import (
    read_recent_context_results,
    request_project_context,
)
from isotope.features.supervisor.runner import (
    EXECUTABLE_ADVICE_TEXT,
    _advice_payload,
    _dashboard_payload,
    _execute_context_action,
    _execute_llm_action,
    _print_dashboard_plain,
    _report_fingerprint,
    _supervise_payload,
    main as supervisor_main,
)
from isotope.features.supervisor.state.worker_lifecycle import (
    record_worker_lifecycle_decision,
)

def test_codex_supervisor_web_serves_dashboard_html_and_json(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server
    from isotope.features.notifications.flow import NotificationFlow

    codex_home = tmp_path / ".codex"
    notification = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="approval",
        title="Worker needs approval",
        source_ref={"ref_type": "supervisor_run", "run_id": "run_123"},
    )
    unsafe_notification = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="approval",
        title="Worker source check",
        source_ref={
            "ref_type": "supervisor_run",
            "run_id": "run_unsafe",
            "prompt": "RAW_PROMPT_SHOULD_NOT_LEAK",
            "api_key": "sk-test-secret",
            "log_path": "/tmp/raw.log",
        },
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-blocked.jsonl",
        session_id="blocked-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: blocked",
                        "SUPERVISOR_SUMMARY: 测试环境缺少 tmux。",
                    ]
                ),
            )
        ],
    )

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/")
        html_response = conn.getresponse()
        html = html_response.read().decode("utf-8")
        conn.request("GET", "/dashboard.json")
        json_response = conn.getresponse()
        payload = json.loads(json_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert html_response.status == 200
    assert "text/html" in html_response.getheader("content-type", "")
    assert 'data-group="needs_attention"' in html
    assert "short_session_id" in html
    assert "display_title" in html
    assert "managed_display_title" in html
    assert "copyResumeCommand" in html
    assert "copyControlCommand" in html
    assert "copyControlLabel" in html
    assert "snapshot-meta" in html
    assert "payload.state_snapshot_meta" in html
    assert "snapshotMeta.schema_status" in html
    assert "snapshotMeta.schema_reason" in html
    assert 'document.getElementById("snapshot-meta")' in html
    assert "读模型：" in html
    assert "复制状态" in html
    assert "复制继续" in html
    assert "sendManagedCommand" in html
    assert "requestLlmAction" in html
    assert "renderDecisionRequest" in html
    assert "renderDecisionRequests" in html
    assert "operator-focus" in html
    assert "运行焦点" in html
    assert "renderOperatorFocus" in html
    assert "renderFocusItem" in html
    assert "focus-primary-action" in html
    assert "supervised-execution-focus" in html
    assert "renderSupervisedExecutionFocus" in html
    assert "recent_capacity_runs" in html
    assert "function capacityRunDetailText(" in html
    assert "capacityRunDetailText(latest)" in html
    assert "capacityRunDetailText(capacityRunFromWorker(worker))" in html
    assert "preferredWorkspaceItems" in html
    assert "itemInWorkspace" in html
    assert "workspace_cwd" in html
    assert "control-center" in html
    assert "Supervisor 控制台" in html
    assert "sendSupervisorServiceAction" in html
    assert "状态已刷新" in html
    assert "/daemon/start" in html
    assert "/daemon/stop" in html
    assert "/watcher/start" in html
    assert "/watcher/stop" in html
    assert "goal-queue-panel" in html
    assert "目标队列" in html
    assert "submitGoalAdd" in html
    assert "submitGoalPlan" in html
    assert "goalPlanRequestBody" in html
    assert "collectEditedGoalPlanPayload" in html
    assert "renderEditableGoalCandidate" in html
    assert "renderEditableParallelRecommendation" in html
    assert "value.split(/[\\n,，/]+/)" in html
    assert "value.split(/[\n" not in html
    assert "上移" in html
    assert "下移" in html
    assert "latestGoalPlanPayload" in html
    assert "renderGoalPlanPreview" in html
    assert "/goal/plan" in html
    assert "规划目标" in html
    assert "写入规划目标" in html
    assert "/goal/add" in html
    assert "renderNotifications" in html
    assert "current-list" in html
    assert "当前批次" in html
    assert "renderCurrentBatch" in html
    assert "current-count" in html
    assert "暂无当前目标" in html
    assert "暂无托管 worker" in html
    assert "dependency-batch" in html
    assert "依赖批次" in html
    assert "renderDependencyBatch" in html
    assert "ready_goals" in html
    assert "blocked_goals" in html
    assert "等待依赖" in html
    assert "worker-detail-list" in html
    assert "Worker 详情" in html
    assert "renderWorkerDetails" in html
    assert "renderWorkerDetailCard" in html
    assert "workerDetailField" in html
    assert "worker-detail:" in html
    assert "multi-worker-panel" in html
    assert "多 Worker 状态" in html
    assert "renderMultiWorkerStatus" in html
    assert "renderMultiWorkerCard" in html
    assert "notification-list" in html
    assert "通知列表" in html
    assert "notification-toggle" in html
    assert "renderNotificationSummary" in html
    assert "notificationSourceSummary" in html
    assert "展开通知" in html
    assert "默认折叠" in html
    assert "submitDecisionAnswer" in html
    assert "/decision/answer" in html
    assert "填写答案" in html
    assert "提交答案" in html
    assert "copyDecisionArchiveCommand" in html
    assert "复制归档拍板" in html
    assert "等待拍板列表" in html
    assert "decision_requests" in html
    assert "等待拍板" in html
    assert "context_status" in html
    assert "renderSupervisorProtocol" in html
    assert "状态汇报" in html
    assert "下一步" in html
    assert "connectSupervisorEvents" in html
    assert "EventSource" in html
    assert "applyLlmActionHighlight" in html
    assert "suggested-action" in html
    assert "data-command-kind" in html
    assert "data-lane-name" in html
    assert "renderCardSource" in html
    assert "卡片来源" in html
    assert "普通历史会话" in html
    assert "renderManagedDetails" in html
    assert "renderLinkedMatch" in html
    assert "linked_match" in html
    assert "绑定依据" in html
    assert "managed_terminal_excerpt" in html
    assert "最近输出" in html
    assert "bell：" in html
    assert "未收到" in html
    assert "bell hook" in html
    assert "终端状态" in html
    assert "scrollTerminalExcerptToBottom" in html
    assert "rememberTerminalExcerptScroll" in html
    assert "restoreTerminalExcerptScroll" in html
    assert "/managed/send" in html
    assert "/llm-action" in html
    assert "/events" in html
    assert "模型建议" in html
    assert "status_evidence" in html
    assert "依据：" in html
    assert "codex resume " in html
    assert '"tmux attach -t " + item.managed_tmux_session' not in html
    assert "Codex Supervisor" in html
    assert "dashboard.json" in html
    assert json_response.status == 200
    assert payload["status"] == "ok"
    assert payload["workspace_cwd"] == str(Path.cwd())
    assert payload["current"] == {
        "active_goals": [],
        "managed_workers": [],
        "worker_reviews": {
            "summary": {"total": 0},
            "workers": [],
            "automation_candidates": {},
        },
        "automation_candidates": {},
        "counts": {
            "active_goals": 0,
            "managed_workers": 0,
            "worker_reviews": 0,
            "automation_candidates": 0,
            "total": 0,
        },
        "target_names": [],
    }
    assert payload["counts"]["needs_attention"] == 1
    assert payload["decision_requests"] == []
    assert payload["notifications"] == [
        notification.to_dict(),
        {
            **unsafe_notification.to_dict(),
            "source_ref": {"ref_type": "supervisor_run", "run_id": "run_unsafe"},
        },
    ]
    raw_payload = json.dumps(payload, ensure_ascii=False)
    assert "RAW_PROMPT_SHOULD_NOT_LEAK" not in raw_payload
    assert "sk-test-secret" not in raw_payload
    assert "/tmp/raw.log" not in raw_payload
    assert payload["notification_counts"] == {"total": 2, "unread": 2}
    assert payload["groups"]["needs_attention"][0]["session_id"] == "blocked-session"
    assert payload["groups"]["needs_attention"][0]["status_evidence"]["source"] == (
        "supervisor_protocol"
    )



def test_codex_supervisor_web_dashboard_payload_builder_keeps_page_fields(tmp_path):
    from isotope.features.supervisor.web import build_dashboard_web_payload

    codex_home = tmp_path / ".codex"
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())

    payload = build_dashboard_web_payload(
        report,
        codex_home=codex_home,
        workspace_cwd=Path("/tmp/isotope-workspace"),
    )

    assert payload["status"] == "ok"
    assert payload["workspace_cwd"] == "/tmp/isotope-workspace"
    assert payload["daemon"]["status"] == "not_running"
    assert payload["watcher"]["status"] == "not_running"
    assert payload["state_snapshot_meta"] == {
        "kind": "supervisor_state_snapshot",
        "schema_version": 1,
        "schema_label": "supervisor_state_snapshot v1",
        "schema_status": "ok",
        "schema_reason": None,
        "source_label": (
            "goal queue / decision requests / lane state / "
            "worker events / notifications / memory records / artifact summaries / "
            "agent groups / worker lifecycle"
        ),
    }
    assert payload["state_snapshot"]["summary"] == {
        "active_goals": 0,
        "goals_done": 0,
        "goals_blocked": 0,
        "goals_needs_user": 0,
        "active_decisions": 0,
        "failed_lanes": 0,
        "worker_events": 0,
        "notifications": 0,
        "unread_notifications": 0,
        "memory_records": 0,
        "artifact_summaries": 0,
        "agent_groups": 0,
    }
    assert payload["current"]["counts"] == {
        "active_goals": 0,
        "managed_workers": 0,
        "worker_reviews": 0,
        "automation_candidates": 0,
        "total": 0,
    }



def test_codex_supervisor_web_dashboard_payload_reads_persisted_worker_lifecycle(tmp_path):
    from isotope.features.supervisor.web import build_dashboard_web_payload

    codex_home = tmp_path / ".codex"
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())
    record_worker_lifecycle_decision(
        codex_home=codex_home,
        worker_lifecycle_decision={
            "stage": "worktree_cleaned",
            "next_step": "monitor",
            "policy": {
                "policy_status": "program_resolved",
                "program_action": "cleanup_worktree",
                "remaining_step": "monitor",
                "blocked_reason": None,
            },
            "timeline": [
                {
                    "stage": "worktree_cleaned",
                    "action": "cleanup_worktree",
                    "source": "cleanup",
                    "status": "executed",
                    "executed": True,
                }
            ],
        },
    )

    payload = build_dashboard_web_payload(
        report,
        codex_home=codex_home,
        workspace_cwd=Path("/tmp/isotope-workspace"),
    )

    assert payload["worker_lifecycle"] == {
        "status": "ok",
        "stage": "worktree_cleaned",
        "next_step": "monitor",
        "policy_status": "program_resolved",
        "program_action": "cleanup_worktree",
        "remaining_step": "monitor",
        "blocked_reason": None,
        "timeline": [
            {
                "stage": "worktree_cleaned",
                "action": "cleanup_worktree",
                "source": "cleanup",
                "status": "executed",
                "executed": True,
            }
        ],
    }
    assert payload["state_snapshot"]["worker_lifecycle"] == payload["worker_lifecycle"]



def test_codex_supervisor_web_executes_current_worker_lifecycle_plan(tmp_path):
    from isotope.features.supervisor import web

    codex_home = tmp_path / ".codex"
    _record_cleanup_lifecycle_execution(codex_home, with_result=True)
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        _record_cleanup_lifecycle_execution(codex_home, executed=True)
        assert check is False
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "status": "ok",
                    "executed": {
                        "kind": "cleanup_worktree",
                        "source": "worker_lifecycle",
                        "deleted": [{"target_name": "source-worker"}],
                    },
                },
                ensure_ascii=False,
            ),
            "",
        )

    server = web.create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        lifecycle_run=stub_run,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps(
            {
                "execute_command": (
                    "isotope-supervisor loop --iterations 1 "
                    "--lifecycle-cleanup-execute"
                )
            }
        ).encode("utf-8")
        conn.request(
            "POST",
            "/worker-lifecycle/execute",
            body,
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["execution"]["executed"]["kind"] == "cleanup_worktree"
    assert payload["dashboard"]["status"] == "ok"
    assert payload["dashboard"]["worker_lifecycle_execution"]["execution_status"] == "executed"
    assert payload["dashboard"]["worker_lifecycle_execution"]["result_summary"] == (
        "deleted source-worker"
    )
    assert payload["dashboard"]["worker_lifecycle_execution"]["summary"] == {
        "archivable": 0,
        "delete_ready": 1,
        "delete_blocked": 0,
        "result_actions": 1,
    }
    assert (
        payload["dashboard"]["worker_lifecycle_execution"]["recommended_next_step"]
        == "monitor"
    )
    assert calls == [
        [
            "isotope-supervisor",
            "loop",
            "--codex-home",
            str(codex_home),
            "--limit",
            "5",
            "--stale-after",
            "999999",
            "--active-within",
            "180",
            "--iterations",
            "1",
            "--json",
            "--lifecycle-cleanup-execute",
        ]
    ]



def test_codex_supervisor_web_rejects_stale_worker_lifecycle_execute_command(tmp_path):
    from isotope.features.supervisor import web

    codex_home = tmp_path / ".codex"
    _record_cleanup_lifecycle_execution(codex_home)
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "{}", "")

    server = web.create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        lifecycle_run=stub_run,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps(
            {
                "execute_command": (
                    "isotope-supervisor loop --iterations 1 "
                    "--merge-dispatch-execute"
                )
            }
        ).encode("utf-8")
        conn.request(
            "POST",
            "/worker-lifecycle/execute",
            body,
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 409
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "worker_lifecycle_execute_stale"
    assert calls == []


def _record_cleanup_lifecycle_execution(
    codex_home: Path,
    *,
    with_result: bool = False,
    executed: bool = False,
) -> None:
    result = None
    if executed:
        result = {
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "deleted": [
                {
                    "kind": "delete_worktree",
                    "target_name": "source-worker",
                    "managed": {
                        "record_id": "managed-source",
                        "name": "source-worker",
                    },
                }
            ],
        }
    elif with_result:
        result = {
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "skipped": True,
            "reason": "lifecycle cleanup execution requires --lifecycle-cleanup-execute",
            "count": 1,
        }
    record_worker_lifecycle_decision(
        codex_home=codex_home,
        worker_lifecycle_decision={
            "stage": "archived",
            "next_step": "cleanup_worktree",
            "policy": {
                "policy_status": "program_resolved",
                "program_action": "archive_integrated",
                "remaining_step": "cleanup_worktree",
                "blocked_reason": None,
            },
        },
        worker_lifecycle_execution={
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "next_step": "cleanup_worktree",
            "status": "ready_to_delete",
            "delete_worktree_actions": [
                {
                    "kind": "delete_worktree",
                    "target_name": "source-worker",
                    "record_id": "managed-source",
                    "confirm_delete_worktree": True,
                    "base_ref": "main",
                    "source": "worker_lifecycle",
                }
            ],
        },
        worker_lifecycle_execution_result=result,
    )



def test_codex_supervisor_web_dashboard_payload_builder_keeps_degraded_snapshot_meta(
    tmp_path,
):
    from isotope.features.supervisor.web import build_dashboard_web_payload

    codex_home = tmp_path / ".codex"
    report = CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())
    legacy_snapshot = {
        "status": "ok",
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

    payload = build_dashboard_web_payload(
        report,
        codex_home=codex_home,
        workspace_cwd=Path("/tmp/isotope-workspace"),
        state_snapshot=legacy_snapshot,
    )

    assert payload["state_snapshot"] == legacy_snapshot
    assert payload["state_snapshot_meta"] == {
        "kind": None,
        "schema_version": None,
        "schema_label": "degraded snapshot schema",
        "schema_status": "degraded",
        "schema_reason": "missing kind",
        "source_label": (
            "goal queue / decision requests / lane state / "
            "worker events / notifications / memory records / artifact summaries / "
            "agent groups / worker lifecycle"
        ),
    }
    assert payload["workspace_cwd"] == "/tmp/isotope-workspace"



def test_codex_supervisor_web_can_control_daemon_and_watcher(tmp_path, monkeypatch):
    from isotope.features.supervisor import web

    codex_home = tmp_path / ".codex"
    calls: list[tuple[str, dict[str, object]]] = []

    def stub_start_daemon(**kwargs):
        calls.append(("daemon_start", dict(kwargs)))
        return {"action": "started", "status": "running", "pid": 111}

    def stub_stop_daemon(**kwargs):
        calls.append(("daemon_stop", dict(kwargs)))
        return {"status": "stopped", "pid": 111}

    def stub_start_watcher(**kwargs):
        calls.append(("watcher_start", dict(kwargs)))
        return {"action": "started", "status": "running", "pid": 222}

    def stub_stop_watcher(**kwargs):
        calls.append(("watcher_stop", dict(kwargs)))
        return {"status": "stopped", "pid": 222}

    monkeypatch.setattr(web, "start_supervisor_daemon", stub_start_daemon)
    monkeypatch.setattr(web, "stop_supervisor_daemon", stub_stop_daemon)
    monkeypatch.setattr(web, "start_supervisor_watcher", stub_start_watcher)
    monkeypatch.setattr(web, "stop_supervisor_watcher", stub_stop_watcher)

    server = web.create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=7,
        stale_after_seconds=901,
        active_within_seconds=123,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        responses = []
        for path in ["/daemon/start", "/daemon/stop", "/watcher/start", "/watcher/stop"]:
            conn.request("POST", path, body="{}", headers={"content-type": "application/json"})
            response = conn.getresponse()
            responses.append(json.loads(response.read().decode("utf-8")))
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert [response["status"] for response in responses] == ["ok", "ok", "ok", "ok"]
    assert [call[0] for call in calls] == [
        "daemon_start",
        "daemon_stop",
        "watcher_start",
        "watcher_stop",
    ]
    assert calls[0][1]["codex_home"] == codex_home
    assert calls[0][1]["limit"] == 7
    assert calls[0][1]["stale_after"] == 901
    assert calls[0][1]["active_within"] == 123
    assert calls[0][1]["worker_codex_model"] == "gpt-5.5"
    assert calls[0][1]["worker_codex_config"] == ('model_reasoning_effort="high"',)
    assert calls[2][1] == {"codex_home": codex_home, "interval": 60}



def test_codex_supervisor_web_can_add_goal_from_page(tmp_path):
    from isotope.features.supervisor import web

    codex_home = tmp_path / ".codex"
    server = web.create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=600,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"goal": "从页面新增目标。"}, ensure_ascii=False).encode("utf-8")
        conn.request("POST", "/goal/add", body=body, headers={"content-type": "application/json"})
        add_response = conn.getresponse()
        add_payload = json.loads(add_response.read().decode("utf-8"))
        conn.request("GET", "/dashboard.json")
        dashboard_response = conn.getresponse()
        dashboard_payload = json.loads(dashboard_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert add_response.status == 200
    assert add_payload["status"] == "ok"
    assert add_payload["goal"]["goal"] == "从页面新增目标。"
    assert add_payload["goal"]["cwd"] == str(Path.cwd())
    assert dashboard_response.status == 200
    assert dashboard_payload["current"]["active_goals"][0]["goal"] == "从页面新增目标。"



def test_codex_supervisor_web_can_plan_goals_from_page(tmp_path):
    from isotope.features.supervisor import web

    class DeterministicProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize(self, messages):
            self.calls += 1
            if self.calls > 1:
                raise AssertionError("write should reuse preview candidates without recalling LLM")
            payload = json.loads(messages[1]["content"])
            assert payload["user_goal"] == "并行推进三个方向。"
            assert payload["write_mode"] is False
            return json.dumps(
                {
                    "plan_summary": "拆成三个并行 worker。",
                    "parallel_recommendations": [
                        {
                            "batch": "第一批",
                            "targets": ["supervisor-modularize", "agent-loop-capacity"],
                            "reason": "修改范围不同。",
                        }
                    ],
                    "goals": [
                        {
                            "goal": "整理 Supervisor 模块边界。",
                            "target_name": "supervisor-modularize",
                            "reason": "runner 复杂度较高。",
                        },
                        {
                            "goal": "打通 agent loop 能力调用。",
                            "target_name": "agent-loop-capacity",
                            "reason": "agent loop 是产品主线。",
                        },
                    ],
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    codex_home = tmp_path / ".codex"
    server = web.create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=600,
        active_within_seconds=180,
        llm_action_provider=provider,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"goal": "并行推进三个方向。"}, ensure_ascii=False).encode("utf-8")
        conn.request("POST", "/goal/plan", body=body, headers={"content-type": "application/json"})
        plan_response = conn.getresponse()
        plan_payload = json.loads(plan_response.read().decode("utf-8"))
        write_body = json.dumps(
            {
                "goal": "并行推进三个方向。",
                "write": True,
                "candidates": plan_payload["candidates"],
                "plan_summary": plan_payload["plan_summary"],
                "parallel_recommendations": plan_payload["parallel_recommendations"],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        conn.request(
            "POST",
            "/goal/plan",
            body=write_body,
            headers={"content-type": "application/json"},
        )
        write_response = conn.getresponse()
        write_payload = json.loads(write_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert plan_response.status == 200
    assert plan_payload["mode"] == "preview"
    assert plan_payload["plan_summary"] == "拆成三个并行 worker。"
    assert [item["target_name"] for item in plan_payload["candidates"]] == [
        "supervisor-modularize",
        "agent-loop-capacity",
    ]
    assert write_response.status == 200
    assert write_payload["mode"] == "write"
    assert [item["target_name"] for item in write_payload["written_goals"]] == [
        "supervisor-modularize",
        "agent-loop-capacity",
    ]
    assert provider.calls == 1



def test_codex_supervisor_web_dashboard_highlights_night_overview(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace, name="merge-worker")
    state_dir = codex_home / "supervisor"
    state_dir.mkdir(parents=True, exist_ok=True)
    for filename, pid, log_name in (
        ("daemon.json", 45678, "daemon.log"),
        ("watcher.json", 33333, "watcher.log"),
    ):
        (state_dir / filename).write_text(
            json.dumps(
                {
                    "pid": pid,
                    "status": "running",
                    "started_at": "2026-05-18T10:00:00+00:00",
                    "stopped_at": None,
                    "command": ["python", "-m", "isotope.features.supervisor.runner"],
                    "codex_home": str(codex_home),
                    "log_path": str(state_dir / "logs" / log_name),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(
        "isotope.features.supervisor.daemon._process_is_alive",
        lambda pid: pid in {33333, 45678},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda _session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda _session: "SUPERVISOR_STATUS: working\nSUPERVISOR_SUMMARY: 合并中。",
    )

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/")
        html_response = conn.getresponse()
        html = html_response.read().decode("utf-8")
        conn.request("GET", "/dashboard.json")
        json_response = conn.getresponse()
        payload = json.loads(json_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert html_response.status == 200
    assert "night-overview" in html
    assert "renderNightOverview" in html
    assert "daemon running" in html
    assert "watcher running" in html
    assert "active goals" in html
    assert "running workers" in html
    assert "ready_to_integrate" in html
    assert "merge worker" in html
    assert json_response.status == 200
    assert payload["daemon"]["status"] == "running"
    assert payload["watcher"]["status"] == "running"



def test_codex_supervisor_web_events_stream_bell_changes(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/events")
        response = conn.getresponse()
        first_line = response.readline().decode("utf-8").strip()
        event_path = codex_home / "supervisor" / "bell_events.jsonl"
        event_path.parent.mkdir(parents=True)
        event_path.write_text(
            (
                '{"event":"bell","name":"lane-a","tmux_session":"isotope-lane-a",'
                '"created_at":"2026-05-16T12:00:00Z"}\n'
            ),
            encoding="utf-8",
        )
        lines: list[str] = []
        while len(lines) < 4:
            lines.append(response.readline().decode("utf-8").strip())
            if "tmux_session" in lines[-1]:
                break
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert response.getheader("content-type") == "text/event-stream; charset=utf-8"
    assert first_line == "event: ready"
    assert "event: bell" in lines
    assert any('"tmux_session": "isotope-lane-a"' in line for line in lines)



def test_codex_supervisor_web_events_stream_keeps_ready_after_ready_race(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor import web

    codex_home = tmp_path / ".codex"
    event_path = codex_home / "supervisor" / "bell_events.jsonl"
    original_write_sse = web._DashboardRequestHandler._write_sse

    def write_sse_and_create_event(self, event, payload):
        original_write_sse(self, event, payload)
        if event != "ready":
            return
        event_path.parent.mkdir(parents=True)
        event_path.write_text(
            (
                '{"event":"bell","name":"lane-a","tmux_session":"isotope-lane-a",'
                '"created_at":"2026-05-16T12:00:00Z"}\n'
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        web._DashboardRequestHandler,
        "_write_sse",
        write_sse_and_create_event,
    )
    server = web.create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/events")
        response = conn.getresponse()
        lines: list[str] = []
        while len(lines) < 6:
            lines.append(response.readline().decode("utf-8").strip())
            if "tmux_session" in lines[-1]:
                break
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert lines[0] == "event: ready"
    assert "event: bell" in lines
    assert any('"tmux_session": "isotope-lane-a"' in line for line in lines)



def test_codex_supervisor_web_repairs_bell_hooks_on_startup(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        text: bool,
        capture_output: bool,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        assert check is (command[:2] == ["tmux", "set-hook"])
        return subprocess.CompletedProcess(command, 0, "", "")

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        repair_run=stub_run,
    )
    server.server_close()

    assert calls[0] == ["tmux", "has-session", "-t", "isotope-lane-a"]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]
    assert [result.to_dict() for result in server.bell_hook_repairs] == [
        {
            "name": "lane-a",
            "tmux_session": "isotope-lane-a",
            "status": "installed",
            "message": None,
        }
    ]



def test_codex_supervisor_web_returns_manual_llm_action_without_sending(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: session == "isotope-lane-a",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._tmux_capture_pane",
        lambda session: (
            "SUPERVISOR_STATUS: blocked\n"
            "SUPERVISOR_SUMMARY: 需要用户提供 API key。\n"
            "SUPERVISOR_NEXT: 等待用户处理。"
        ),
    )
    send_calls: list[list[str]] = []

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            assert "command_suggestions" in messages[1]["content"]
            return '{"kind":"send_status","target_name":"lane-a","reason":"先看进度。"}'

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        send_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        send_run=stub_run,
        llm_action_provider=DeterministicProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/llm-action",
            b"{}",
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["supervisor_action"] == {
        "kind": "send_status",
        "target_name": "lane-a",
        "reason": "先看进度。",
        "command_suggestion": {
            "command": _supervisor_send_command("lane-a", STATUS_REQUEST_TEXT),
            "kind": "send_status",
            "label": "让托管 Codex 汇报状态",
        },
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert send_calls == []


def test_codex_supervisor_web_returns_ask_user_after_context_gate(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "目录迁移文档和现状冲突，需要用户拍板兼容策略。\n",
        encoding="utf-8",
    )
    request_project_context(
        codex_home=codex_home,
        cwd=workspace,
        query="目录迁移 兼容策略",
        rg_bin=None,
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-needs-user.jsonl",
        session_id="019e35a2-e442-75e2-84ab-3761a685a736",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: needs_user",
                        "SUPERVISOR_SUMMARY: 目录迁移有两种不可兼容方案。",
                        "SUPERVISOR_NEXT: 请用户拍板选择保留兼容层还是直接迁移。",
                    ]
                ),
            )
        ],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert "目录迁移文档和现状冲突" in content
            return json.dumps(
                {
                    "kind": "ask_user",
                    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                    "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                    "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
                },
                ensure_ascii=False,
            )

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        llm_action_provider=DeterministicProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/llm-action",
            b"{}",
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["supervisor_action"] == {
        "kind": "ask_user",
        "target_name": "resume-019e35a2",
        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
        "question": "目录迁移是保留兼容层，还是直接迁移并删除旧入口？",
        "context_status": "conflict",
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "reason": "Codex 明确要拍板，既有指示不足，文档和现状冲突。",
        "command_suggestion": None,
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["recent_context_results"][0]["query"] == "目录迁移 兼容策略"



def test_codex_supervisor_web_can_submit_decision_answer(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    decision_path = codex_home / "supervisor" / "decision_requests.jsonl"
    decision_path.parent.mkdir(parents=True)
    decision_path.write_text(
        json.dumps(
            {
                "event": "decision_request",
                "request_id": "decision-001",
                "created_at": "2026-05-20T12:00:00+00:00",
                "session_id": "goal:goal-001",
                "goal_id": "goal-001",
                "target_name": "goal-supervisor",
                "question": "保留兼容层还是直接迁移？",
                "reason": "目标明确请求拍板。",
                "context_status": "conflict",
                "gate": {
                    "codex_requested_decision": True,
                    "instructions_exhausted": True,
                    "context_status": "conflict",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/decision/answer",
            json.dumps(
                {
                    "request_id": "decision-001",
                    "answer": "保留兼容层，后续再清理旧入口。",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        conn.request("GET", "/dashboard.json")
        dashboard_response = conn.getresponse()
        dashboard_payload = json.loads(dashboard_response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["answered"]["event"] == "decision_answer"
    assert payload["answered"]["request_id"] == "decision-001"
    assert payload["answered"]["goal_id"] == "goal-001"
    assert payload["answered"]["answer"] == "保留兼容层，后续再清理旧入口。"
    assert payload["decision_requests"] == []
    assert dashboard_response.status == 200
    assert dashboard_payload["decision_requests"] == []



def test_codex_supervisor_web_rejects_invalid_manual_llm_action(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return '{"kind":"delete_branch","reason":"危险动作"}'

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        llm_action_provider=DeterministicProvider(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/llm-action",
            b"{}",
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 400
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "codex_supervisor_web_error"
    assert "unsupported LLM action" in payload["error"]["message"]



def test_codex_supervisor_web_can_send_allowed_managed_command(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert check is True
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(command, 0, "", "")

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        send_run=stub_run,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"name": "lane-a", "kind": "send_status"}).encode("utf-8")
        conn.request(
            "POST",
            "/managed/send",
            body,
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload["status"] == "ok"
    assert payload["kind"] == "send_status"
    assert payload["text"] == STATUS_REQUEST_TEXT
    assert payload["managed"]["tmux_session"] == "isotope-lane-a"
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)
    lane_state = json.loads(
        (codex_home / "supervisor" / "lane_state.json").read_text(encoding="utf-8")
    )
    assert lane_state["lane-a"]["last_status"] == "send_status"
    assert lane_state["lane-a"]["prompt_count"] == 1



def test_codex_supervisor_web_rejects_unsupported_managed_command(tmp_path):
    from isotope.features.supervisor.web import create_dashboard_server

    codex_home = tmp_path / ".codex"

    server = create_dashboard_server(
        codex_home=codex_home,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"name": "lane-a", "kind": "tmux_attach"}).encode("utf-8")
        conn.request(
            "POST",
            "/managed/send",
            body,
            {"content-type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 400
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "codex_supervisor_web_error"
    assert "send_status" in payload["error"]["message"]

