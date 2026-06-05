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

from helpers import (
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


def test_codex_supervisor_runner_supervise_llm_execute_can_request_context(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 下一步节奏：由 LLM 主导，规则走执行协议。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )

    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            content = messages[1]["content"]
            assert '"context_capability"' in content
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": "Supervisor 下一步节奏",
                    "reason": "先查项目上下文再决定。",
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["llm_action"] == payload["supervisor_action"]
    context = _codex_operation_context_result(payload["executed"])
    assert context["query"] == "Supervisor 下一步节奏"
    assert context["items"][0]["path"] == "docs/current/status.md"
    assert "LLM 主导" in context["items"][0]["text"]

    context_log = codex_home / "supervisor" / "context_results.jsonl"
    records = [
        json.loads(line)
        for line in context_log.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["query"] == "Supervisor 下一步节奏"



def test_execute_context_action_routes_through_request_context_capability(
    tmp_path,
    monkeypatch,
):
    from isotope.features.supervisor import runner as runner_module

    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[dict[str, object]] = []

    def fail_direct_request_context(**kwargs: object) -> object:
        raise AssertionError("direct request_project_context should not be called")

    def stub_run_capability(
        self: object,
        capability_id: str,
        *,
        inputs: dict[str, object],
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append(
            {
                "capability_id": capability_id,
                "inputs": inputs,
                "kwargs": kwargs,
            }
        )
        return {
            "kind": "capability_run_result",
            "capability_id": "supervisor.request_context",
            "status": "completed",
            "runner_kind": "deterministic_projection",
            "context_result": {
                "result_id": "context-test",
                "cwd": str(workspace),
                "query": "Supervisor 下一步节奏",
                "created_at": "2026-05-23T12:00:00+00:00",
                "backend": "bm25",
                "item_count": 1,
                "items": [
                    {
                        "path": "docs/current/status.md",
                        "line": 1,
                        "title": "status",
                        "text": "LLM 主导",
                        "snippet": "LLM 主导",
                        "score": 1.0,
                        "match_reason": "query term",
                        "source_group": "docs/current",
                    }
                ],
            },
        }

    monkeypatch.setattr(
        runner_module,
        "request_project_context",
        fail_direct_request_context,
    )
    monkeypatch.setattr(
        runner_module.CapabilityRunner,
        "run_capability",
        stub_run_capability,
    )

    result = _execute_context_action(
        _runner_args(codex_home),
        {
            "kind": "request_context",
            "cwd": str(workspace),
            "query": "Supervisor 下一步节奏",
            "command_suggestion": {"command": "custom context command"},
        },
    )

    assert calls == [
        {
            "capability_id": "supervisor.request_context",
            "inputs": {
                "codex_home": str(codex_home),
                "cwd": str(workspace),
                "query": "Supervisor 下一步节奏",
            },
            "kwargs": {},
        }
    ]
    assert result == {
        "kind": "request_context",
        "command": "custom context command",
        "cwd": str(workspace),
        "query": "Supervisor 下一步节奏",
        "context": {
            "result_id": "context-test",
            "cwd": str(workspace),
            "query": "Supervisor 下一步节奏",
            "created_at": "2026-05-23T12:00:00+00:00",
            "backend": "bm25",
            "items": [
                {
                    "path": "docs/current/status.md",
                    "line": 1,
                    "title": "status",
                    "text": "LLM 主导",
                    "snippet": "LLM 主导",
                    "score": 1.0,
                    "match_reason": "query term",
                    "source_group": "docs/current",
                }
            ],
        },
    }



def test_execute_context_action_preserves_legacy_context_shape_with_real_capability(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor request_context capability keeps created_at for replan.\n",
        encoding="utf-8",
    )

    result = _execute_context_action(
        _runner_args(codex_home),
        {
            "kind": "request_context",
            "cwd": str(workspace),
            "query": "request_context capability created_at",
        },
    )

    assert result["kind"] == "request_context"
    assert result["command"] == shlex.join(
        [
            "isotope-supervisor",
            "context",
            "--cwd",
            str(workspace),
            "--query",
            "request_context capability created_at",
        ]
    )
    context = result["context"]
    assert set(context) == {
        "result_id",
        "cwd",
        "query",
        "created_at",
        "backend",
        "items",
    }
    assert context["cwd"] == str(workspace)
    assert context["query"] == "request_context capability created_at"
    assert context["backend"] == "bm25"
    assert isinstance(context["created_at"], str)
    assert context["created_at"]
    assert isinstance(context["items"], list)




def test_codex_supervisor_runner_supervise_request_context_replans_same_iteration(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 同轮闭环：查完上下文后可以继续推进。\n",
        encoding="utf-8",
    )
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
        lambda session: "› 等待输入\n  gpt-5.5 xhigh · main",
    )

    class DeterministicProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            if self.calls == 1:
                assert '"recent_context_results": []' in content
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "Supervisor 同轮闭环",
                        "reason": "先查上下文再决定动作。",
                    },
                    ensure_ascii=False,
                )
            assert "Supervisor 同轮闭环" in content
            assert "docs/current/status.md" in content
            return json.dumps(
                {
                    "kind": "send_status",
                    "target_name": "lane-a",
                    "reason": "读到上下文后，立刻请求托管窗口汇报状态。",
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command and command[0].endswith("rg"):
            return subprocess.CompletedProcess(command, 1, "", "")
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-execute",
            "--prompt-cooldown",
            "0",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["llm_action"] == payload["supervisor_action"]
    _codex_operation_context_result(payload["executed"])
    assert payload["supervisor_followup_action"]["kind"] == "send_status"
    assert payload["llm_followup_action"] == payload["supervisor_followup_action"]
    assert payload["followup_executed"]["kind"] == "send_status"
    assert calls == _tmux_send_calls(STATUS_REQUEST_TEXT)
    assert provider.calls == 2




def test_codex_supervisor_runner_supervise_respects_max_context_requests(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 上下文预算：同一轮按预算查一次。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "Supervisor 上下文预算",
                        "reason": "先查当前文档。",
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": "Supervisor 上下文预算 第二次",
                    "reason": "还想继续查。",
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-execute",
            "--max-context-requests",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["llm_action"] == payload["supervisor_action"]
    _codex_operation_context_result(payload["executed"])
    assert payload["supervisor_followup_action"]["kind"] == "request_context"
    assert payload["llm_followup_action"] == payload["supervisor_followup_action"]
    assert payload["followup_executed"] == {
        "kind": "request_context",
        "skipped": True,
        "reason": "context request budget exhausted",
        "context_request_count": 1,
        "max_context_requests": 1,
    }
    context_log = codex_home / "supervisor" / "context_results.jsonl"
    records = [
        json.loads(line)
        for line in context_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["query"] for record in records] == ["Supervisor 上下文预算"]
    assert provider.calls == 2




def test_codex_supervisor_runner_supervise_default_allows_context_followup(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "Supervisor 默认预算要宽松，避免阻碍长任务。\n",
        encoding="utf-8",
    )
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "上一轮已完成。")],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    class DeterministicProvider:
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            return json.dumps(
                {
                    "kind": "request_context",
                    "cwd": str(workspace),
                    "query": f"默认宽松预算 {self.calls}",
                    "reason": "继续查上下文。",
                },
                ensure_ascii=False,
            )

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    _codex_operation_context_result(payload["executed"])
    _codex_operation_context_result(payload["followup_executed"])
    assert "skipped" not in payload["followup_executed"]
    context_log = codex_home / "supervisor" / "context_results.jsonl"
    records = [
        json.loads(line)
        for line in context_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["query"] for record in records] == [
        "默认宽松预算 1",
        "默认宽松预算 2",
    ]
    assert provider.calls == 2




def test_codex_supervisor_runner_supervise_context_followup_can_ask_user_after_gate(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs" / "current"
    docs_dir.mkdir(parents=True)
    (docs_dir / "status.md").write_text(
        "目录迁移文档和现有代码冲突，需要人工确认兼容策略。\n",
        encoding="utf-8",
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
        calls = 0

        def summarize(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            content = messages[1]["content"]
            if self.calls == 1:
                return json.dumps(
                    {
                        "kind": "request_context",
                        "cwd": str(workspace),
                        "query": "目录迁移 兼容策略",
                        "reason": "先查文档和现状再决定是否问用户。",
                    },
                    ensure_ascii=False,
                )
            assert "目录迁移文档和现有代码冲突" in content
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

    provider = DeterministicProvider()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: provider,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--llm-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supervisor_action"]["kind"] == "request_context"
    assert payload["llm_action"] == payload["supervisor_action"]
    _codex_operation_context_result(payload["executed"])
    assert payload["supervisor_followup_action"]["kind"] == "ask_user"
    assert payload["llm_followup_action"] == payload["supervisor_followup_action"]
    followup = payload["followup_executed"]
    assert followup["kind"] == "ask_user"
    assert followup["requires_user"] is True
    assert followup["session_id"] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert followup["target_name"] == "resume-019e35a2"
    assert followup["question"] == "目录迁移是保留兼容层，还是直接迁移并删除旧入口？"
    assert followup["reason"] == "Codex 明确要拍板，既有指示不足，文档和现状冲突。"
    assert followup["context_status"] == "conflict"
    assert followup["gate"] == {
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "context_status": "conflict",
    }
    decision_request = followup["decision_request"]
    assert decision_request["event"] == "decision_request"
    assert decision_request["session_id"] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert decision_request["target_name"] == "resume-019e35a2"
    assert decision_request["question"] == "目录迁移是保留兼容层，还是直接迁移并删除旧入口？"
    assert decision_request["reason"] == "Codex 明确要拍板，既有指示不足，文档和现状冲突。"
    assert decision_request["context_status"] == "conflict"
    assert decision_request["gate"] == {
        "codex_requested_decision": True,
        "instructions_exhausted": True,
        "context_status": "conflict",
    }
    assert decision_request["request_id"].startswith("decision-")
    assert decision_request["created_at"]
    decision_log = codex_home / "supervisor" / "decision_requests.jsonl"
    records = [
        json.loads(line)
        for line in decision_log.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["event"] == "decision_request"
    assert records[0]["question"] == "目录迁移是保留兼容层，还是直接迁移并删除旧入口？"
    assert provider.calls == 2




def test_codex_supervisor_runner_supervise_reports_no_managed_lane(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    _write_session(
        codex_home,
        "2026/05/16/rollout-active.jsonl",
        session_id="active-session",
        cwd="/home/lumber/Github/isotope",
        events=[
            _event(
                "2026-05-16T11:59:20Z",
                "event_msg",
                {"type": "agent_reasoning", "message": "reading files"},
            )
        ],
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["automation"] == {
        "ready": False,
        "managed_tmux_count": 0,
        "managed_process_count": 0,
        "managed_names": [],
        "reason": "当前没有托管的 Codex 进程或可旁观 tmux lane。",
        "launch_hint": "isotope-supervisor launch --name <name> --cwd <repo> --prompt '<task>'",
        "adopt_hint": "isotope-supervisor adopt --name <name> --cwd <repo> --tmux-session <session>",
    }
    assert payload["executed"]["reason"] == "no managed tmux lane"

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "当前没有托管的 Codex 进程或可旁观 tmux lane。" in text
    assert "isotope-supervisor launch --name <name>" in text
    assert "isotope-supervisor adopt --name" in text




def test_codex_supervisor_runner_supervise_ignores_exited_managed_lane(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["automation"]["ready"] is False
    assert payload["auto_action"] == {
        "kind": "monitor",
        "reason": "no managed tmux lane",
    }
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "no managed tmux lane",
    }
    assert calls == []




def test_codex_supervisor_runner_supervise_plain_omits_exited_managed_lanes(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_session_exists",
        lambda session: False,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._tmux_window_has_bell",
        lambda session: False,
    )

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--auto-execute",
        ]
    )

    text = capsys.readouterr().out
    assert exit_code == 0
    assert "managed:managed-001" not in text
    assert "托管：lane-a" not in text
    assert "已退出" not in text
    assert "工作中：0" in text




def test_codex_supervisor_runner_supervise_llm_execute_rejects_other_execute_modes(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"

    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--llm-execute",
            "--auto-execute",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "cannot be used together" in payload["error"]["message"]




