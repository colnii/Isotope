from __future__ import annotations

import json
import subprocess

import pytest

from isotope import codex_cli, codex_task, models


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


def _proposal() -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_codex_cli",
        run_id="run_codex_cli",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="delegate_agent_task",
        payload={
            "tool": "codex_task",
            "prompt": "Inspect the repo and summarize the next safe step.",
            "summary": "delegate repository inspection to Codex CLI",
        },
        requested_capabilities={
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 8},
        },
        registry_id="default",
        registry_version="v0.2",
    )


def _decision(proposal: models.ActionProposal) -> models.PolicyDecision:
    return models.PolicyDecision(
        decision_id="dec_codex_cli",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 8},
            "codex_task": {"adapter_required": True},
        },
        reason_codes=[],
        policy_profile_id="default",
        policy_version="v0.2",
    )


def _request(tmp_path, *, workspace_mode: str = "shared_ro") -> codex_task.CodexTaskRequest:
    proposal = _proposal()
    return codex_task.build_codex_task_request(
        proposal=proposal,
        decision=_decision(proposal),
        execution_id="exec_codex_cli",
        workspace_binding={
            "workspace_id": "workspace_codex_cli",
            "mode": workspace_mode,
            "root_ref": "workspace://run_codex_cli/shared_ro",
        },
        basis_event_ids=["evt_started"],
    )


def test_codex_cli_backend_invokes_codex_exec_with_stdin_and_isotope_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET_ENV_SHOULD_NOT_BE_INHERITED")
    workspace_root = tmp_path / "workspace"
    codex_home = tmp_path / "codex-home"
    runner = RecordingProcessRunner(
        FakeCompletedProcess(stdout='{"event":"task_complete"}\n', stderr="diagnostic\n")
    )
    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(workspace_root),
            codex_home=str(codex_home),
            sandbox="read-only",
            approval_policy="never",
            max_output_bytes=4096,
        ),
        process_runner=runner,
    )

    result = backend.run(_request(tmp_path))

    assert result.status == "completed"
    assert result.reason_code == "codex_cli_completed"
    assert len(result.output_artifacts) == 1
    transcript = json.loads(result.output_artifacts[0].content)
    assert transcript["exit_code"] == 0
    assert transcript["stdout"] == '{"event":"task_complete"}\n'
    assert transcript["stderr"] == "diagnostic\n"
    assert transcript["shell"] is False
    assert "Inspect the repo" not in result.summary
    assert "Inspect the repo" not in result.output_artifacts[0].content

    call = runner.calls[0]
    argv = call["argv"]
    assert argv == [
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
        str(workspace_root.resolve()),
        "--ephemeral",
        "-",
    ]
    assert "Inspect the repo and summarize the next safe step." not in argv
    kwargs = call["kwargs"]
    assert kwargs["input"] == "Inspect the repo and summarize the next safe step."
    assert kwargs["cwd"] == str(workspace_root.resolve())
    assert kwargs["timeout"] == 8
    assert kwargs["shell"] is False
    assert kwargs["text"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False
    assert kwargs["env"]["CODEX_HOME"] == str(codex_home.resolve())
    assert kwargs["env"]["LANG"] == "C.UTF-8"
    assert "OPENAI_API_KEY" not in kwargs["env"]


def test_codex_cli_backend_can_skip_git_repo_check_for_temp_workspace(tmp_path):
    workspace_root = tmp_path / "workspace"
    runner = RecordingProcessRunner(FakeCompletedProcess())
    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(workspace_root),
            skip_git_repo_check=True,
        ),
        process_runner=runner,
    )

    backend.run(_request(tmp_path))

    assert "--skip-git-repo-check" in runner.calls[0]["argv"]


def test_codex_cli_backend_can_inherit_proxy_env_without_sensitive_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:7890")
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET_ENV_SHOULD_NOT_BE_INHERITED")
    runner = RecordingProcessRunner(FakeCompletedProcess())
    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(tmp_path),
            inherit_proxy_env=True,
        ),
        process_runner=runner,
    )

    backend.run(_request(tmp_path))

    env = runner.calls[0]["kwargs"]["env"]
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert env["http_proxy"] == "http://127.0.0.1:7890"
    assert env["NO_PROXY"] == "localhost,127.0.0.1"
    assert "OPENAI_API_KEY" not in env


def test_codex_cli_backend_requires_discovered_executable(tmp_path):
    with pytest.raises(codex_task.CodexTaskNotConfiguredError) as exc_info:
        codex_cli.CodexCliBackend(
            codex_cli.CodexCliBackendConfig(
                executable="codex",
                workspace_root=str(tmp_path),
            ),
            executable_resolver=lambda _name: None,
            process_runner=RecordingProcessRunner(FakeCompletedProcess()),
        )

    assert exc_info.value.error_reason_code == "codex_task_adapter_not_configured"
    assert exc_info.value.structured_details["executable"] == "codex"


def test_codex_cli_backend_rejects_unsafe_codex_sandbox(tmp_path):
    with pytest.raises(ValueError, match="read-only"):
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(tmp_path),
            sandbox="danger-full-access",
        )


def test_codex_cli_backend_requires_shared_read_only_workspace(tmp_path):
    runner = RecordingProcessRunner(FakeCompletedProcess())
    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(tmp_path),
        ),
        process_runner=runner,
    )

    with pytest.raises(codex_task.CodexTaskProtocolError) as exc_info:
        backend.run(_request(tmp_path, workspace_mode="workspace_write"))

    assert exc_info.value.error_reason_code == "codex_cli_workspace_not_granted"
    assert runner.calls == []


def test_codex_cli_backend_maps_nonzero_exit_to_failed_result_without_prompt_leak(tmp_path):
    runner = RecordingProcessRunner(
        FakeCompletedProcess(
            returncode=2,
            stdout="partial codex output",
            stderr="model failed",
        )
    )
    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(tmp_path),
        ),
        process_runner=runner,
    )

    result = backend.run(_request(tmp_path))

    assert result.status == "failed"
    assert result.reason_code == "codex_cli_exit_nonzero"
    assert result.retryable is False
    assert result.resource_usage["exit_code"] == 2
    assert "Inspect the repo" not in result.summary
    assert "Inspect the repo" not in repr(result)


def test_codex_cli_backend_maps_timeout_to_timeout_result(tmp_path):
    def timeout_runner(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["codex", "exec"], timeout=8, output="partial")

    backend = codex_cli.CodexCliBackend(
        codex_cli.CodexCliBackendConfig(
            executable="/opt/codex/bin/codex",
            workspace_root=str(tmp_path),
        ),
        process_runner=timeout_runner,
    )

    result = backend.run(_request(tmp_path))

    assert result.status == "timeout"
    assert result.reason_code == "codex_cli_timeout"
    assert result.retryable is True
    assert result.resource_usage["timeout_seconds"] == 8
