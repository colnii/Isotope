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

def test_codex_supervisor_runner_guide_prints_usable_workflow(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--tmux-session",
            "doc-tmux",
            "--prompt",
            "继续推进文档任务",
            "--interval",
            "30",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Codex Supervisor 使用入口]" in text
    assert "isotope-supervisor resume --name doc-lane" in text
    assert "--session-id '<session-id>'" in text
    assert "--last --prompt '继续推进文档任务'" in text
    assert f"isotope-supervisor launch --name doc-lane --cwd {workspace}" in text
    assert (
        "isotope-supervisor launch --backend tmux --name doc-lane "
        "--tmux-session doc-tmux"
    ) in text
    assert f"--cwd {workspace}" in text
    assert "--prompt '继续推进文档任务'" in text
    assert (
        "isotope-supervisor adopt --name doc-lane "
        f"--cwd {workspace} --tmux-session doc-tmux"
    ) in text
    assert (
        "isotope-supervisor daemon start --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    ) in text
    assert (
        "isotope-supervisor loop --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    ) in text
    assert "isotope-supervisor web" in text
    assert "isotope-supervisor archive --name doc-lane" in text



def test_codex_supervisor_runner_guide_can_print_json(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workflow"]["lane_name"] == "doc-lane"
    assert payload["workflow"]["tmux_session"] == "doc-lane"
    assert payload["workflow"]["cwd"] == str(workspace)
    assert payload["workflow"]["worker_codex_model"] == "gpt-5.5"
    assert payload["workflow"]["worker_codex_config"] == [
        'model_reasoning_effort="high"'
    ]
    assert payload["commands"]["resume"] == (
        "isotope-supervisor resume --name doc-lane "
        f"--cwd {workspace} --session-id '<session-id>' "
        "--prompt '继续推进当前任务，并在完成或阻塞时按 "
        "SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。'"
    )
    assert payload["commands"]["resume_last"] == (
        "isotope-supervisor resume --name doc-lane "
        f"--cwd {workspace} --last --prompt '继续推进当前任务，并在完成或阻塞时按 "
        "SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。'"
    )
    assert payload["commands"]["launch_process"] == (
        "isotope-supervisor launch --name doc-lane "
        f"--cwd {workspace} --prompt '继续推进当前任务，并在完成或阻塞时按 "
        "SUPERVISOR_STATUS/SUMMARY/NEXT 汇报。'"
    )
    assert payload["commands"]["supervise"] == (
        "isotope-supervisor loop --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    )
    assert payload["commands"]["daemon"] == (
        "isotope-supervisor daemon start --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"high\"'"
    )
    assert payload["commands"]["archive"] == "isotope-supervisor archive --name doc-lane"



def test_codex_supervisor_runner_guide_can_override_worker_options(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--worker-codex-model",
            "gpt-5.4-mini",
            "--worker-codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"]["worker_codex_model"] == "gpt-5.4-mini"
    assert payload["workflow"]["worker_codex_config"] == [
        'model_reasoning_effort="low"'
    ]
    assert payload["commands"]["daemon"] == (
        "isotope-supervisor daemon start --interval 30 "
        "--worker-codex-model gpt-5.4-mini "
        "--worker-codex-config 'model_reasoning_effort=\"low\"'"
    )



def test_codex_supervisor_runner_guide_can_use_light_worker_profile(tmp_path, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    exit_code = supervisor_main(
        [
            "guide",
            "--cwd",
            str(workspace),
            "--name",
            "doc-lane",
            "--worker-profile",
            "light",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"]["worker_profile"] == "light"
    assert payload["workflow"]["worker_codex_model"] == "gpt-5.5"
    assert payload["workflow"]["worker_codex_config"] == [
        'model_reasoning_effort="low"'
    ]
    assert payload["commands"]["supervise"] == (
        "isotope-supervisor loop --interval 30 "
        "--worker-codex-model gpt-5.5 "
        "--worker-codex-config 'model_reasoning_effort=\"low\"'"
    )



def test_codex_supervisor_runner_discover_lists_adoptable_tmux_codex_sessions(
    tmp_path,
    capsys,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        if command[:3] == ["tmux", "list-sessions", "-F"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "iso_dev\t0\t1\nplain-shell\t1\t1\n",
                "",
            )
        if command[:3] == ["tmux", "capture-pane", "-p"]:
            session = command[4]
            panes = {
                "iso_dev": "› 好，下一步\n  gpt-5.5 xhigh · Context 80% left\n",
                "plain-shell": "vim README.md\n",
            }
            return subprocess.CompletedProcess(command, 0, panes[session], "")
        if command[:3] == ["tmux", "display-message", "-p"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--cwd",
            str(workspace),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["cwd"] == str(workspace)
    assert payload["candidates"] == [
        {
            "tmux_session": "iso_dev",
            "suggested_name": "iso-dev",
            "cwd": str(workspace),
            "attached": False,
            "windows": 1,
            "looks_like_codex": True,
            "reason": "pane text looks like Codex",
            "adopt_command": (
                "isotope-supervisor adopt --name iso-dev "
                f"--cwd {workspace} --tmux-session iso_dev"
            ),
            "attach_command": "tmux attach -t iso_dev",
            "excerpt": "› 好，下一步\n  gpt-5.5 xhigh · Context 80% left",
        }
    ]
    assert calls[0] == [
        "tmux",
        "list-sessions",
        "-F",
        "#{session_name}\t#{session_attached}\t#{session_windows}",
    ]



def test_codex_supervisor_runner_discover_treats_missing_tmux_socket_as_empty(
    tmp_path,
    capsys,
    monkeypatch,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def stub_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["tmux", "list-sessions", "-F"]
        assert check is False
        assert text is True
        assert capture_output is True
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            "error connecting to /tmp/tmux-1001/default (No such file or directory)",
        )

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--cwd",
            str(workspace),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["candidates"] == []



def test_codex_supervisor_runner_discover_can_adopt_candidate_by_index(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[list[str]] = []

    def stub_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert text is True
        assert capture_output is True
        if command[:3] == ["tmux", "list-sessions", "-F"]:
            return subprocess.CompletedProcess(command, 0, "iso_dev\t0\t1\n", "")
        if command[:3] == ["tmux", "capture-pane", "-p"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "› 继续开发 supervisor\n  gpt-5.5 xhigh · Context 80% left\n",
                "",
            )
        if command[:3] == ["tmux", "display-message", "-p"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[:3] == ["tmux", "has-session", "-t"]:
            assert command[3] == "iso_dev"
            assert check is False
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["tmux", "set-hook", "-t", "iso_dev"]:
            assert check is True
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--adopt-index",
            "1",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["adopted_candidate"]["tmux_session"] == "iso_dev"
    assert payload["managed"]["name"] == "iso-dev"
    assert payload["managed"]["status"] == "adopted"
    assert payload["managed"]["backend"] == "tmux"
    assert payload["managed"]["tmux_session"] == "iso_dev"
    assert payload["next_commands"] == {
        "attach": "tmux attach -t iso_dev",
        "loop": "isotope-supervisor loop --interval 30",
        "archive": "isotope-supervisor archive --name iso-dev",
    }
    records = [
        json.loads(line)
        for line in (codex_home / "supervisor" / "managed_sessions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records == [payload["managed"]]



def test_codex_supervisor_runner_discover_can_adopt_first_candidate(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def stub_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert text is True
        assert capture_output is True
        if command[:3] == ["tmux", "list-sessions", "-F"]:
            return subprocess.CompletedProcess(command, 0, "iso_dev\t0\t1\n", "")
        if command[:3] == ["tmux", "capture-pane", "-p"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "› 继续开发 supervisor\n  gpt-5.5 xhigh · Context 80% left\n",
                "",
            )
        if command[:3] == ["tmux", "display-message", "-p"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[:3] == ["tmux", "has-session", "-t"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["tmux", "set-hook", "-t", "iso_dev"]:
            assert check is True
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "discover",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--adopt-first",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "已接管：iso-dev / tmux=iso_dev" in text
    assert "监督：isotope-supervisor loop --interval 30" in text



def test_codex_supervisor_runner_launch_records_managed_codex(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 12345

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
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "launch",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--prompt",
            "继续实现 supervisor",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["managed"]["name"] == "lane-a"
    assert payload["managed"]["pid"] == 12345
    assert payload["managed"]["cwd"] == str(workspace)
    assert payload["managed"]["prompt"] == "继续实现 supervisor"
    assert payload["managed"]["log_path"].endswith(".log")
    assert captured["command"][:5] == [
        "codex",
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
    ]
    assert captured["command"][5].startswith("继续实现 supervisor")
    assert "SUPERVISOR_STATUS" in captured["command"][5]
    assert "SUPERVISOR_SUMMARY" in captured["command"][5]
    assert "SUPERVISOR_NEXT" in captured["command"][5]
    assert payload["managed"]["prompt"] == "继续实现 supervisor"
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    records = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [payload["managed"]]



def test_codex_supervisor_runner_launch_can_override_codex_worker_options(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 12346

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
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "launch",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--prompt",
            "低成本检查",
            "--codex-model",
            "gpt-5.4-mini",
            "--codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    json.loads(capsys.readouterr().out)
    assert captured["command"][:9] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.4-mini",
        "-c",
        'model_reasoning_effort="low"',
        "-C",
        str(workspace),
        "--skip-git-repo-check",
    ]



def test_codex_supervisor_runner_launch_can_use_tmux_backend(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "launch",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--prompt",
            "继续实现 supervisor",
            "--backend",
            "tmux",
            "--tmux-session",
            "isotope-lane-a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["managed"]["backend"] == "tmux"
    assert payload["managed"]["tmux_session"] == "isotope-lane-a"
    assert payload["managed"]["pid"] == 0
    assert calls[0][:7] == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        "isotope-lane-a",
        "-c",
        str(workspace),
    ]
    assert "codex --cd " + str(workspace) + " --no-alt-screen" in calls[0][7]
    assert "继续实现 supervisor" in calls[0][7]
    assert "SUPERVISOR_STATUS" in calls[0][7]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]



def test_codex_supervisor_runner_resume_exec_records_managed_codex(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 23456

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
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "resume",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--session-id",
            "019e35a2-e442-75e2-84ab-3761a685a736",
            "--prompt",
            "继续推进 supervisor 前端测试",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["managed"]["name"] == "lane-a"
    assert payload["managed"]["backend"] == "codex_exec_resume"
    assert payload["managed"]["pid"] == 23456
    assert payload["managed"]["resume_session_id"] == (
        "019e35a2-e442-75e2-84ab-3761a685a736"
    )
    assert payload["managed"]["resume_last"] is False
    assert captured["command"][:6] == [
        "codex",
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "resume",
    ]
    assert captured["command"][6] == "019e35a2-e442-75e2-84ab-3761a685a736"
    assert captured["command"][7].startswith("继续推进 supervisor 前端测试")
    assert "SUPERVISOR_STATUS" in captured["command"][7]
    assert captured["cwd"] == str(workspace)
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["start_new_session"] is True

    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    records = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [payload["managed"]]



def test_codex_supervisor_runner_resume_can_override_codex_worker_options(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 23458

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
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "resume",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--session-id",
            "019e35a2-e442-75e2-84ab-3761a685a736",
            "--prompt",
            "低成本恢复",
            "--codex-model",
            "gpt-5.4-mini",
            "--codex-config",
            'model_reasoning_effort="low"',
            "--json",
        ]
    )

    assert exit_code == 0
    json.loads(capsys.readouterr().out)
    assert captured["command"][:10] == [
        "codex",
        "exec",
        "-m",
        "gpt-5.4-mini",
        "-c",
        'model_reasoning_effort="low"',
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "resume",
    ]



def test_codex_supervisor_runner_resume_exec_last_uses_last_flag(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    captured: dict[str, object] = {}

    class StubProcess:
        pid = 23457

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
        captured["stdin"] = stdin
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["start_new_session"] = start_new_session
        return StubProcess()

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.Popen", stub_popen)

    exit_code = supervisor_main(
        [
            "resume",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "latest",
            "--last",
            "--prompt",
            "请汇报当前状态",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["managed"]["backend"] == "codex_exec_resume"
    assert payload["managed"]["resume_session_id"] is None
    assert payload["managed"]["resume_last"] is True
    assert captured["command"][:7] == [
        "codex",
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "resume",
        "--last",
    ]
    assert captured["command"][7].startswith("请汇报当前状态")



def test_codex_supervisor_runner_adopt_registers_existing_tmux_session(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "adopt",
            "--codex-home",
            str(codex_home),
            "--cwd",
            str(workspace),
            "--name",
            "lane-a",
            "--tmux-session",
            "isotope-lane-a",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["managed"]["name"] == "lane-a"
    assert payload["managed"]["status"] == "adopted"
    assert payload["managed"]["backend"] == "tmux"
    assert payload["managed"]["tmux_session"] == "isotope-lane-a"
    assert payload["managed"]["prompt"] == "接管已有 Codex 会话"
    assert calls[0] == ["tmux", "has-session", "-t", "isotope-lane-a"]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]

    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    records = [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records == [payload["managed"]]



def test_codex_supervisor_runner_repair_hooks_installs_for_existing_tmux_records(
    tmp_path,
    capsys,
    monkeypatch,
):
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        ["repair-hooks", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "status": "ok",
        "repairs": [
            {
                "name": "lane-a",
                "tmux_session": "isotope-lane-a",
                "status": "installed",
                "message": None,
            }
        ],
    }
    assert calls[0] == ["tmux", "has-session", "-t", "isotope-lane-a"]
    assert calls[1][:4] == ["tmux", "set-hook", "-t", "isotope-lane-a"]
    assert calls[1][4] == "alert-bell"
    assert "bell_events.jsonl" in calls[1][5]
    assert "lane-a" in calls[1][5]



def test_codex_supervisor_runner_send_text_to_tmux_managed_session(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": "继续实现 supervisor",
                "command": ["tmux", "new-session", "-d", "-s", "isotope-lane-a"],
                "pid": 0,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "launched",
                "backend": "tmux",
                "tmux_session": "isotope-lane-a",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
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

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", stub_run)

    exit_code = supervisor_main(
        [
            "send",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-a",
            "--text",
            "继续",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "managed": {
            "name": "lane-a",
            "record_id": "managed-001",
            "tmux_session": "isotope-lane-a",
        },
        "status": "ok",
        "text": "继续",
    }
    assert calls == _tmux_send_calls("继续")



def test_codex_supervisor_runner_send_rejects_non_tmux_managed_session(
    tmp_path,
    capsys,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "record_id": "managed-001",
                "name": "lane-a",
                "cwd": str(workspace),
                "prompt": "继续实现 supervisor",
                "command": ["codex", "--cd", str(workspace), "--no-alt-screen", "继续"],
                "pid": 12345,
                "started_at": "2026-05-16T11:59:30+00:00",
                "log_path": str(codex_home / "supervisor" / "logs" / "managed-001.log"),
                "status": "launched",
                "backend": "process",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = supervisor_main(
        [
            "send",
            "--codex-home",
            str(codex_home),
            "--name",
            "lane-a",
            "--text",
            "继续",
            "--json",
        ]
    )

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "codex_supervisor_runner_error"
    assert "tmux" in payload["error"]["message"]


