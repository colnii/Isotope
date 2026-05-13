from __future__ import annotations

import json
import os

import pytest

from isotope_kernel import codex_server, server


class FakeCompletedProcess:
    def __init__(self, *, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RecordingProcessRunner:
    def __init__(self, result: FakeCompletedProcess) -> None:
        self.result = result
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": dict(kwargs)})
        return self.result


def _create_run(api: server.InProcessServer) -> str:
    session = api.create_session()
    run = api.create_run(session["session_id"], "run explicit codex cli task")
    return run["run_id"]


def _codex_intent() -> dict:
    return {
        "action": "delegate_agent_task",
        "tool": "codex_task",
        "prompt": "Inspect this repository and reply with the next safe step.",
        "summary": "explicit codex cli server wiring smoke",
    }


def _approved_body() -> dict:
    return {
        "resolution": "approved",
        "reason": "allow explicit codex cli server wiring smoke",
        "resolver": "reviewer",
    }


def test_default_server_still_keeps_codex_task_deferred(tmp_path):
    api = server.InProcessServer(tmp_path)
    run_id = _create_run(api)
    before_events = api.event_store.list_events(run_id)

    with pytest.raises(ValueError, match="deferred tool codex_task is not callable"):
        api.submit_action(run_id, _codex_intent(), requires_approval=True)

    after_events = api.event_store.list_events(run_id)
    assert [(event.event_id, event.event_type) for event in after_events] == [
        (event.event_id, event.event_type) for event in before_events
    ]


def test_codex_cli_server_requires_approval_before_process_call(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess(stdout='{"event":"task_complete"}\n'))
    api = codex_server.create_codex_cli_server(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
        ),
        process_runner=runner,
    )
    run_id = _create_run(api)

    result = api.submit_action(run_id, _codex_intent())

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["codex_task_approval_required"]
    assert runner.calls == []


def test_codex_cli_server_runs_approved_codex_task_through_cli_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET_ENV_SHOULD_NOT_BE_INHERITED")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete","message":"ok"}\n')
    )
    api = codex_server.create_codex_cli_server(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            executable="/opt/codex/bin/codex",
            codex_home=str(tmp_path / "codex-home"),
            timeout_seconds=17,
            max_output_bytes=4096,
        ),
        process_runner=runner,
    )
    run_id = _create_run(api)

    pending = api.submit_action(run_id, _codex_intent(), requires_approval=True)
    assert pending["status"] == "pending_user_approval"
    assert runner.calls == []

    result = api.resolve_approval(pending["approval_id"], _approved_body())

    assert result["status"] == "completed"
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["argv"] == [
        "/opt/codex/bin/codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--color",
        "never",
        "--sandbox",
        "read-only",
        "--cd",
        str((tmp_path / "workspace").resolve()),
        "--ephemeral",
        "--skip-git-repo-check",
        "-",
    ]
    assert call["kwargs"]["input"] == _codex_intent()["prompt"]
    assert call["kwargs"]["cwd"] == str((tmp_path / "workspace").resolve())
    assert call["kwargs"]["timeout"] == 17
    assert call["kwargs"]["shell"] is False
    assert call["kwargs"]["env"]["CODEX_HOME"] == str((tmp_path / "codex-home").resolve())
    assert call["kwargs"]["env"]["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert "OPENAI_API_KEY" not in call["kwargs"]["env"]

    action = result["run_state"].actions[result["execution_id"]]
    assert action["codex_task"] == {
        "adapter_id": "codex_cli",
        "adapter_version": "server-wiring.v0.1",
        "protocol_version": "codex-task-adapter.v0.1",
        "mode": "agent_cli_task",
        "status": "completed",
        "reason_code": "codex_cli_completed",
    }
    assert _codex_intent()["prompt"] not in repr(action)
    assert "task_complete" not in repr(action)

    transcript = json.loads(api.artifact_store.get_content(result["artifact_ref"]))
    assert transcript["stdout"] == '{"event":"task_complete","message":"ok"}\n'
    assert transcript["shell"] is False
    assert transcript["stdin_prompt_bytes"] == len(_codex_intent()["prompt"].encode("utf-8"))


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_CODEX_SERVER_SMOKE") != "1",
    reason="live Codex server wiring smoke is opt-in",
)
def test_live_codex_cli_server_wiring_runs_approved_task(tmp_path):
    api = codex_server.create_codex_cli_server(
        tmp_path,
        config=codex_server.CodexCliServerConfig(
            workspace_root=str(tmp_path / "workspace"),
            timeout_seconds=45,
        ),
    )
    run_id = _create_run(api)

    pending = api.submit_action(
        run_id,
        {
            "action": "delegate_agent_task",
            "tool": "codex_task",
            "prompt": "Reply exactly ISOTOPE_SERVER_CODEX_SMOKE_OK. Do not modify files.",
            "summary": "explicit server-level live Codex smoke",
        },
        requires_approval=True,
    )
    result = api.resolve_approval(pending["approval_id"], _approved_body())

    assert result["status"] == "completed"
    content = api.artifact_store.get_content(result["artifact_ref"])
    assert content
    assert "exit_code" in content
