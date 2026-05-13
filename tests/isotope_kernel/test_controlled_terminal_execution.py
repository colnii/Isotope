from __future__ import annotations

import json

import pytest

from isotope_kernel import action_registry, server


ACTION_EVENT_TYPES = {
    "action.proposed",
    "action.decided",
    "action.started",
    "action.completed",
    "action.failed",
    "artifact.created",
    "run.completed",
}


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="controlled terminal execution")
    return api, run["run_id"]


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _terminal_intent(argv: list[str], **overrides):
    intent = {
        "action": "call_tool",
        "tool": "terminal_exec",
        "argv": argv,
        "summary": "terminal command",
    }
    intent.update(overrides)
    return intent


def _artifact_content(api: server.InProcessServer, result: dict) -> dict:
    raw = api.artifact_store.get_content(result["artifact_ref"])
    return json.loads(raw)


def _approved_body() -> dict:
    return {
        "resolution": "approved",
        "reason": "operator approved terminal command",
        "resolver": "human_reviewer",
    }


def _terminal_registry(
    *,
    allowed_commands: list[str],
    approval_required_commands: list[str],
) -> action_registry.ActionTypeRegistry:
    return action_registry.ActionTypeRegistry(
        entries=[
            {
                "action_type": "call_tool",
                "tool_name": "terminal_exec",
                "payload_requirements": {"required": ["argv"]},
                "required_capabilities": {
                    "tools": ["terminal_exec"],
                    "workspace": {"mode": "shared_ro"},
                    "budget": {"seconds": 5},
                    "terminal": {
                        "shell": False,
                        "argv_policy": "allowlist",
                        "allowed_commands": allowed_commands,
                        "approval_required_commands": approval_required_commands,
                        "max_output_bytes": 4096,
                    },
                },
                "default_workspace_mode": "shared_ro",
                "result_kind": "terminal_output",
                "enabled": True,
            }
        ]
    )


def _new_run_with_registry(tmp_path, registry: action_registry.ActionTypeRegistry):
    api = server.InProcessServer(tmp_path, registry=registry)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="approval gated terminal execution")
    return api, run["run_id"]


def test_default_registry_exposes_terminal_exec_as_controlled_tool():
    registry = action_registry.ActionTypeRegistry.default()

    assert "terminal_exec" in registry.tool_names()
    entry = registry.get_tool("terminal_exec")
    assert entry.action_type == "call_tool"
    assert entry.payload_requirements == {"required": ["argv"]}
    assert entry.required_capabilities["tools"] == ["terminal_exec"]
    assert entry.required_capabilities["workspace"] == {"mode": "shared_ro"}
    assert entry.required_capabilities["terminal"]["shell"] is False
    assert entry.required_capabilities["terminal"]["argv_policy"] == "allowlist"


@pytest.mark.parametrize("bad_argv", ["printf hello", "", None, ["printf", 123], []])
def test_terminal_exec_requires_structured_argv_without_action_side_effects(tmp_path, bad_argv):
    api, run_id = _new_run(tmp_path)
    before = _event_types(api, run_id)

    with pytest.raises(ValueError, match="argv"):
        api.submit_action(
            run_id,
            {
                "action": "call_tool",
                "tool": "terminal_exec",
                "argv": bad_argv,
            },
        )

    assert _event_types(api, run_id) == before
    assert api.artifact_store.list_artifacts(run_id) == []


def test_terminal_exec_runs_allowlisted_argv_and_stores_output_as_artifact(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        _terminal_intent(["printf", "isotope-terminal"]),
    )

    assert result["status"] == "completed"
    assert _event_types(api, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
    artifact_event = next(
        event for event in api.get_events(run_id) if event.event_type == "artifact.created"
    )
    assert artifact_event.payload["artifact"]["artifact_type"] == "terminal_output"
    assert "isotope-terminal" not in repr(artifact_event.payload)

    content = _artifact_content(api, result)
    assert content["argv"] == ["printf", "isotope-terminal"]
    assert content["exit_code"] == 0
    assert content["stdout"] == "isotope-terminal"
    assert content["stderr"] == ""
    assert content["truncated"] is False
    assert content["shell"] is False


def test_terminal_exec_projects_safe_action_summary_and_artifact_ref(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        _terminal_intent(["printf", "read-model-secret"]),
    )

    action = result["run_state"].actions[result["execution_id"]]
    assert action["requested_action_summary"] == {
        "action_type": "call_tool",
        "tool": "terminal_exec",
        "terminal_command": "printf",
        "argv_count": 2,
    }
    assert action["artifact_refs"] == [result["artifact_ref"].to_dict()]
    assert "read-model-secret" not in repr(action)


def test_terminal_exec_policy_denies_shell_and_does_not_start_execution(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        _terminal_intent(["bash", "-lc", "printf forbidden"]),
    )

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["terminal_command_not_allowed"]
    assert not any(event_type in {"action.started", "action.failed"} for event_type in _event_types(api, run_id))
    assert api.artifact_store.list_artifacts(run_id) == []


def test_terminal_exec_timeout_uses_structured_action_failed_error(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        _terminal_intent(["sleep", "1"], budget={"seconds": 0}),
    )

    assert result["status"] == "failed"
    failed = next(event for event in api.get_events(run_id) if event.event_type == "action.failed")
    assert failed.payload["error_reason_code"] == "terminal_timeout"
    assert failed.payload["structured_error"]["reason_code"] == "terminal_timeout"
    assert failed.payload["structured_error"]["details"]["timeout_seconds"] == 0
    assert "artifact.created" not in _event_types(api, run_id)
    assert "run.completed" not in _event_types(api, run_id)
    assert api.artifact_store.list_artifacts(run_id) == []


def test_terminal_exec_caps_output_inside_artifact_content(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        _terminal_intent(["printf", "x" * 5000]),
    )

    content = _artifact_content(api, result)
    assert result["status"] == "completed"
    assert len(content["stdout"]) < 5000
    assert content["truncated"] is True
    assert content["max_output_bytes"] == 4096


def test_terminal_exec_nonzero_exit_fails_without_artifact_side_effect(tmp_path):
    api, run_id = _new_run(tmp_path)

    result = api.submit_action(
        run_id,
        _terminal_intent(["false"]),
    )

    assert result["status"] == "failed"
    failed = next(event for event in api.get_events(run_id) if event.event_type == "action.failed")
    assert failed.payload["error_reason_code"] == "terminal_exit_nonzero"
    assert failed.payload["structured_error"]["details"]["exit_code"] == 1
    assert not any(event_type == "artifact.created" for event_type in _event_types(api, run_id))
    assert api.artifact_store.list_artifacts(run_id) == []


def test_terminal_exec_approval_required_command_denies_without_approval(tmp_path):
    registry = _terminal_registry(
        allowed_commands=["pwd"],
        approval_required_commands=["printf"],
    )
    api, run_id = _new_run_with_registry(tmp_path, registry)

    result = api.submit_action(
        run_id,
        _terminal_intent(["printf", "needs-approval"]),
    )

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["terminal_approval_required"]
    assert "action.started" not in _event_types(api, run_id)
    assert api.artifact_store.list_artifacts(run_id) == []


def test_terminal_exec_approval_required_command_takes_precedence_over_allowlist(tmp_path):
    registry = _terminal_registry(
        allowed_commands=["printf"],
        approval_required_commands=["printf"],
    )
    api, run_id = _new_run_with_registry(tmp_path, registry)

    result = api.submit_action(
        run_id,
        _terminal_intent(["printf", "overlap"]),
    )

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["terminal_approval_required"]
    assert "action.started" not in _event_types(api, run_id)
    assert api.artifact_store.list_artifacts(run_id) == []


def test_terminal_exec_approval_required_command_runs_after_approval(tmp_path):
    registry = _terminal_registry(
        allowed_commands=["pwd"],
        approval_required_commands=["printf"],
    )
    api, run_id = _new_run_with_registry(tmp_path, registry)

    pending = api.submit_action(
        run_id,
        _terminal_intent(["printf", "approved-terminal"]),
        requires_approval=True,
    )
    before_resolution = _event_types(api, run_id)

    assert pending["status"] == "pending_user_approval"
    assert pending["approval_id"]
    assert "action.started" not in before_resolution
    assert api.artifact_store.list_artifacts(run_id) == []

    result = api.resolve_approval(pending["approval_id"], _approved_body())

    assert result["status"] == "completed"
    content = _artifact_content(api, result)
    assert content["argv"] == ["printf", "approved-terminal"]
    assert content["stdout"] == "approved-terminal"
    assert _event_types(api, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "approval.requested",
        "approval.resolved",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
