from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from isotope.features.supervisor.notifications.context import ContextItem, ContextResult
from isotope.features.supervisor.notifications.context import append_context_result
from isotope.features.supervisor.notifications.context import default_context_results_path
from isotope.features.supervisor.state.lane_state import record_lane_prompt
from isotope.features.supervisor.runner import EXECUTABLE_ADVICE_TEXT
from isotope.features.supervisor.runner import main as supervisor_main


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
LONG_COOLDOWN_SECONDS = "999999999"


def test_supervisor_loop_monitors_when_no_controllable_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"

    class FailingProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            raise AssertionError("idle loop should not call the LLM provider")

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: FailingProvider(),
    )

    payload = _run_loop(codex_home=codex_home, workspace_root=tmp_path, capsys=capsys)

    assert payload["supervisor_action"] == {
        "kind": "monitor",
        "target_name": None,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
        "command_suggestion": None,
    }
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
    }


@pytest.mark.parametrize(
    ("kind", "expected_text"),
    [
        ("send_status", EXECUTABLE_ADVICE_TEXT["send_status"]),
        ("send_continue", EXECUTABLE_ADVICE_TEXT["send_continue"]),
    ],
)
def test_supervisor_loop_executes_managed_tmux_prompt_actions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    expected_text: str,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    run_calls: list[list[str]] = []

    _patch_managed_tmux(monkeypatch, run_calls=run_calls)
    _patch_provider(
        monkeypatch,
        {
            "kind": kind,
            "target_name": "lane-a",
            "reason": f"测试 {kind} 受控动作。",
        },
    )

    payload = _run_loop(codex_home=codex_home, workspace_root=tmp_path, capsys=capsys)

    assert payload["executed"]["kind"] == kind
    assert payload["executed"]["text"] == expected_text
    tmux_calls = [call for call in run_calls if call and call[0] == "tmux"]
    assert [call[:2] for call in tmux_calls] == [
        ["tmux", "set-buffer"],
        ["tmux", "paste-buffer"],
        ["tmux", "send-keys"],
    ]
    assert tmux_calls[0][-1] == expected_text
    assert tmux_calls[1][-1] == "isotope-lane-a"
    assert tmux_calls[2][-1] == "C-m"


def test_supervisor_loop_blocks_prompt_action_during_cooldown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    record_lane_prompt(
        codex_home=codex_home,
        name="lane-a",
        tmux_session="isotope-lane-a",
        status="working",
        prompt_kind="send_status",
        now=NOW,
    )
    run_calls: list[list[str]] = []

    _patch_managed_tmux(monkeypatch, run_calls=run_calls)
    _patch_provider(
        monkeypatch,
        {
            "kind": "send_status",
            "target_name": "lane-a",
            "reason": "刚问过状态，冷却期应拦截。",
        },
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--prompt-cooldown", LONG_COOLDOWN_SECONDS],
    )

    assert payload["executed"]["kind"] == "send_status"
    assert payload["executed"]["skipped"] is True
    assert payload["executed"]["reason"] == "lane prompt cooldown active"
    assert [call for call in run_calls if call and call[0] == "tmux"] == []


def test_supervisor_loop_blocks_continue_when_lane_budget_is_exhausted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    record_lane_prompt(
        codex_home=codex_home,
        name="lane-a",
        tmux_session="isotope-lane-a",
        status="done",
        prompt_kind="send_continue",
        now=NOW,
    )
    run_calls: list[list[str]] = []

    _patch_managed_tmux(monkeypatch, run_calls=run_calls)
    _patch_provider(
        monkeypatch,
        {
            "kind": "send_continue",
            "target_name": "lane-a",
            "reason": "继续次数已经达到预算。",
        },
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--max-continue-count", "1"],
    )

    assert payload["executed"]["kind"] == "send_continue"
    assert payload["executed"]["skipped"] is True
    assert payload["executed"]["reason"] == "lane continue budget exhausted"
    assert [call for call in run_calls if call and call[0] == "tmux"] == []


def test_supervisor_loop_turns_empty_llm_response_into_monitor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _patch_managed_tmux(monkeypatch, run_calls=[])

    class EmptyProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return ""

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: EmptyProvider(),
    )

    payload = _run_loop(codex_home=codex_home, workspace_root=tmp_path, capsys=capsys)

    assert payload["supervisor_action"]["kind"] == "monitor"
    assert "LLM action must be a JSON object" in payload["supervisor_action"]["error"]
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "monitor"
    assert payload["executed"]["skipped"] is True


def test_supervisor_loop_escalates_repeated_empty_llm_response_to_decision_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _patch_managed_tmux(monkeypatch, run_calls=[])

    class EmptyProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return ""

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: EmptyProvider(),
    )

    first = _run_loop(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--max-failure-retries", "1"],
    )
    second = _run_loop(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--max-failure-retries", "1"],
    )

    assert first["executed"]["kind"] == "monitor"
    assert second["supervisor_action"]["kind"] == "ask_user"
    assert second["llm_action"] == second["supervisor_action"]
    assert second["executed"]["kind"] == "ask_user"
    assert second["executed"]["requires_user"] is True
    assert second["executed"]["target_name"] == "lane-a"
    assert second["decision_requests"][0]["target_name"] == "lane-a"
    assert second["decision_requests"][0]["session_id"] == (
        "failure:llm_planner_invalid_response:lane-a"
    )
    ledger_path = codex_home / "supervisor" / "failure_events.jsonl"
    events = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["retry_count"] for event in events] == [1, 2]
    assert events[-1]["event_type"] == "llm_planner_invalid_response"
    notifications = json.loads(
        (codex_home / "notifications" / "index.json").read_text(encoding="utf-8")
    )
    assert notifications["notifications"][0]["type"] == "supervisor_decision_request"


def test_supervisor_loop_turns_unknown_target_into_monitor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_managed_tmux_record(codex_home, workspace=workspace)
    _patch_managed_tmux(monkeypatch, run_calls=[])
    _patch_provider(
        monkeypatch,
        {
            "kind": "send_status",
            "target_name": "missing-lane",
            "reason": "模型误选了不存在的目标。",
        },
    )

    payload = _run_loop(codex_home=codex_home, workspace_root=tmp_path, capsys=capsys)

    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["supervisor_action"]["error"] == (
        "unknown managed target for LLM action: missing-lane"
    )
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"]["kind"] == "monitor"


def test_supervisor_loop_executes_resume_session(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-stale.jsonl",
        session_id="resume-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:40:00Z", "上一轮还没完成。")],
    )
    captured: dict[str, Any] = {}

    class StubRecord:
        name = "resume-resume-session"
        record_id = "managed-resume"
        pid = 56789
        backend = "codex_exec_resume"
        resume_session_id = "resume-session"

    def stub_resume_managed_codex(**kwargs: Any) -> StubRecord:
        captured.update(kwargs)
        return StubRecord()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resume_managed_codex",
        stub_resume_managed_codex,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )
    _patch_provider(
        monkeypatch,
        {
            "kind": "resume_session",
            "session_id": "resume-session",
            "prompt_kind": "send_status",
            "reason": "恢复历史会话查看状态。",
        },
    )

    payload = _run_supervise(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--llm-execute", "--worker-codex-model", "gpt-5.4-mini"],
    )

    assert payload["executed"]["kind"] == "resume_session"
    assert payload["executed"]["managed"]["resume_session_id"] == "resume-session"
    assert captured["cwd"] == workspace
    assert captured["name"] == "resume-resume-session"
    assert captured["prompt"] == EXECUTABLE_ADVICE_TEXT["send_status"]
    assert captured["session_id"] == "resume-session"
    assert captured["codex_model"] == "gpt-5.4-mini"


def test_supervisor_loop_executes_launch_session(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    goal = "继续推进 Supervisor 集成测试。"
    captured: dict[str, Any] = {}

    class StubProcess:
        pid = 45678

    def stub_popen(
        command: list[str],
        *,
        cwd: str,
        stdin: object,
        stdout: object,
        stderr: object,
        start_new_session: bool,
    ) -> StubProcess:
        captured["command"] = command
        captured["cwd"] = cwd
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)
    _patch_provider(
        monkeypatch,
        {
            "kind": "launch_session",
            "target_name": "new-worker",
            "cwd": str(workspace),
            "prompt": goal,
            "reason": "启动新 worker 推进目标。",
        },
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace_root=workspace,
        capsys=capsys,
        extra_args=["--goal", goal],
    )

    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["managed"]["name"] == "new-worker"
    assert payload["executed"]["managed"]["pid"] == 45678
    assert payload["executed"]["worktree"] == {
        "enabled": False,
        "source_cwd": str(workspace),
        "cwd": str(workspace),
        "reason": "not_git_repo",
    }
    assert captured["cwd"] == str(workspace)
    assert captured["command"][0:2] == ["codex", "exec"]
    assert f"goal: {goal}" in captured["command"][-1]


def test_supervisor_loop_records_worker_launch_failure_without_crashing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fail_popen(*args: Any, **kwargs: Any) -> None:
        raise OSError("codex binary missing")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", fail_popen)
    _patch_provider(
        monkeypatch,
        {
            "kind": "launch_session",
            "target_name": "new-worker",
            "cwd": str(workspace),
            "prompt": "继续推进 Supervisor 集成测试。",
            "reason": "启动新 worker 推进目标。",
        },
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace_root=workspace,
        capsys=capsys,
        extra_args=["--goal", "继续推进 Supervisor 集成测试。"],
    )

    assert payload["executed"]["kind"] == "launch_session"
    assert payload["executed"]["skipped"] is True
    assert payload["executed"]["reason"] == "supervisor action failed"
    assert payload["executed"]["failure_event"]["event_type"] == "worker_launch_failed"
    ledger_path = codex_home / "supervisor" / "failure_events.jsonl"
    events = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["lane_name"] == "new-worker"
    assert events[-1]["retry_count"] == 1


def test_supervisor_loop_executes_request_context(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "status.md").write_text("Supervisor 当前状态：等待测试。\n", encoding="utf-8")
    _write_session(
        codex_home,
        "2026/05/16/rollout-source.jsonl",
        session_id="source-session",
        cwd=str(workspace),
        events=[_assistant_message("2026-05-16T11:59:20Z", "还需要看项目上下文。")],
    )
    _patch_provider(
        monkeypatch,
        {
            "kind": "request_context",
            "cwd": str(workspace),
            "query": "Supervisor 当前状态",
            "reason": "先取当前项目上下文。",
        },
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--goal", "查明 Supervisor 当前状态。"],
    )

    assert payload["executed"]["kind"] == "call_capacity"
    assert payload["executed"]["capacity_id"] == "supervisor.codex_operation"
    assert payload["executed"]["operation"] == "request_context"
    action_result = payload["executed"]["agent_loop"]["step_result"]["action_result"]
    context = action_result["capability_run"]["operation_result"]["context_result"]
    assert context["cwd"] == str(workspace)
    assert context["query"] == "Supervisor 当前状态"
    assert context["items"]


def test_supervisor_loop_executes_ask_user_after_context_check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_session(
        codex_home,
        "2026/05/16/rollout-needs-user.jsonl",
        session_id="needs-user-session",
        cwd=str(workspace),
        events=[
            _assistant_message(
                "2026-05-16T11:59:20Z",
                "\n".join(
                    [
                        "SUPERVISOR_STATUS: needs_user",
                        "SUPERVISOR_SUMMARY: 需要用户确认保留 A 方案还是 B 方案。",
                        "SUPERVISOR_NEXT: 等待用户拍板。",
                    ]
                ),
            )
        ],
    )
    append_context_result(
        default_context_results_path(codex_home),
        ContextResult(
            result_id="context-ask-user",
            cwd=str(workspace),
            query="方案 A B 冲突",
            created_at=NOW.isoformat(),
            items=(
                ContextItem(
                    path="status.md",
                    line=1,
                    text="A/B 方案都被提到，但没有用户最终选择。",
                    score=1.0,
                    title="status.md",
                    snippet="A/B 方案都被提到",
                    match_reason="keyword",
                ),
            ),
        ),
    )
    _patch_provider(
        monkeypatch,
        {
            "kind": "ask_user",
            "session_id": "needs-user-session",
            "question": "请确认本轮保留 A 方案还是 B 方案？",
            "codex_requested_decision": True,
            "instructions_exhausted": True,
            "context_status": "conflict",
            "reason": "上下文显示方案冲突，需要用户拍板。",
        },
    )

    payload = _run_loop(
        codex_home=codex_home,
        workspace_root=tmp_path,
        capsys=capsys,
        extra_args=["--goal", "处理需要用户拍板的方案冲突。"],
    )

    assert payload["executed"]["kind"] == "ask_user"
    assert payload["executed"]["requires_user"] is True
    assert payload["executed"]["session_id"] == "needs-user-session"
    assert payload["executed"]["context_status"] == "conflict"
    assert payload["decision_requests"][0]["question"] == "请确认本轮保留 A 方案还是 B 方案？"


def test_supervisor_loop_ignores_missing_worktree_delete_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / ".codex"
    missing_worktree = tmp_path / "repo" / ".worktrees" / "supervisor" / "gone-12345678"
    _write_managed_process_record(
        codex_home,
        name="gone-worker",
        cwd=missing_worktree,
        status="launched",
        log_text="SUPERVISOR_STATUS: blocked\nSUPERVISOR_SUMMARY: worktree 已缺失。\n",
    )

    _patch_provider(
        monkeypatch,
        {
            "kind": "delete_worktree",
            "target_name": "gone-worker",
            "confirm_delete_worktree": True,
            "reason": "worker worktree 已缺失，模型想清理记录。",
        },
    )

    payload = _run_loop(codex_home=codex_home, workspace_root=tmp_path, capsys=capsys)

    assert payload["supervisor_action"]["kind"] == "monitor"
    assert payload["supervisor_action"]["error"] == (
        "delete_worktree target is not an allowed cleanup candidate"
    )
    assert payload["llm_action"] == payload["supervisor_action"]
    assert payload["executed"] == {
        "kind": "monitor",
        "skipped": True,
        "reason": payload["supervisor_action"]["reason"],
    }
    assert not missing_worktree.exists()


def _run_loop(
    *,
    codex_home: Path,
    workspace_root: Path,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace_root),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
            *(extra_args or []),
        ]
    )
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)


def _run_supervise(
    *,
    codex_home: Path,
    workspace_root: Path,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    exit_code = supervisor_main(
        [
            "supervise",
            "--codex-home",
            str(codex_home),
            "--workspace-root",
            str(workspace_root),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--json",
            *(extra_args or []),
        ]
    )
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)


def _patch_provider(monkeypatch: pytest.MonkeyPatch, action: dict[str, Any]) -> None:
    class DeterministicProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(action, ensure_ascii=False)

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.resolve_summary_provider_from_env",
        lambda **_: DeterministicProvider(),
    )


def _patch_managed_tmux(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_calls: list[list[str]],
) -> None:
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
        lambda session: "SUPERVISOR_STATUS: working\nSUPERVISOR_SUMMARY: 等待输入。",
    )

    def stub_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool = False,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        run_calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)


def _write_session(
    codex_home: Path,
    relative_path: str,
    *,
    session_id: str,
    cwd: str,
    events: list[dict[str, object]],
) -> Path:
    path = codex_home / "sessions" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-05-16T11:45:00Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": cwd,
                "cli_version": "0.130.0",
                "model_provider": "openai",
            },
        },
        *events,
    ]
    path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _write_managed_tmux_record(
    codex_home: Path,
    *,
    workspace: Path,
    name: str = "lane-a",
    record_id: str = "managed-001",
    tmux_session: str = "isotope-lane-a",
) -> None:
    _write_managed_record(
        codex_home,
        {
            "record_id": record_id,
            "name": name,
            "cwd": str(workspace),
            "prompt": "等待输入",
            "command": ["tmux", "new-session", "-d", "-s", tmux_session],
            "pid": 0,
            "started_at": NOW.isoformat(),
            "log_path": str(codex_home / "supervisor" / "logs" / f"{record_id}.log"),
            "status": "launched",
            "backend": "tmux",
            "tmux_session": tmux_session,
        },
    )


def _write_managed_process_record(
    codex_home: Path,
    *,
    name: str,
    cwd: Path,
    status: str,
    log_text: str,
) -> None:
    log_path = codex_home / "supervisor" / "logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log_text, encoding="utf-8")
    _write_managed_record(
        codex_home,
        {
            "record_id": f"managed-{name}",
            "name": name,
            "cwd": str(cwd),
            "prompt": "处理缺失 worktree。",
            "command": ["codex", "exec", "-C", str(cwd), "WORK ORDER"],
            "pid": 4242,
            "started_at": NOW.isoformat(),
            "log_path": str(log_path),
            "status": status,
            "backend": "process",
        },
    )


def _write_managed_record(codex_home: Path, record: dict[str, Any]) -> None:
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _event(timestamp: str, type_: str, payload: dict[str, object]) -> dict[str, object]:
    return {"timestamp": timestamp, "type": type_, "payload": payload}


def _assistant_message(timestamp: str, text: str) -> dict[str, object]:
    return _event(
        timestamp,
        "response_item",
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        },
    )
