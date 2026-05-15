from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import isotope.demo as demo
import isotope.platform.schemas.models as models
import isotope.runtime.in_process as server


def _submit_pending_tool_request(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="bind workspace from policy grants")
    result = api.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text="workspace-bound output",
        requires_approval=True,
    )
    assert result["status"] == "pending_user_approval"
    return api, run["run_id"], result


def _decision_from(result: dict[str, Any], *, grants: dict[str, Any]) -> models.PolicyDecision:
    decision = result["decision"]
    return models.PolicyDecision(
        decision_id=decision.decision_id,
        proposal_id=decision.proposal_id,
        outcome=decision.outcome,
        grants=grants,
        reason_codes=list(decision.reason_codes),
    )


def _workspace_events(api: server.InProcessServer, run_id: str):
    return [event for event in api.get_events(run_id) if event.event_type == "workspace.bound"]


def _assert_no_internal_repr(value: Any) -> None:
    if isinstance(value, str):
        assert "object at 0x" not in value
        assert "PolicyDecision(" not in value
        assert "WorkspaceBinding(" not in value
        assert "RunState(" not in value
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_no_internal_repr(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_internal_repr(nested)


def test_bind_workspace_helper_appends_canonical_event_and_returns_projected_summary(tmp_path):
    api, run_id, result = _submit_pending_tool_request(tmp_path)
    decision = result["decision"]
    before_events = list(api.get_events(run_id))

    binding = api.bind_workspace(
        run_id,
        decision,
        bound_to={"agent_id": "agent_supervisor"},
    )

    after_events = list(api.get_events(run_id))
    workspace_events = _workspace_events(api, run_id)
    assert len(after_events) == len(before_events) + 1
    assert len(workspace_events) == 1
    event = workspace_events[0]
    assert event.payload["workspace_id"] == "workspace_shared_ro"
    assert event.payload["run_id"] == run_id
    assert event.payload["mode"] == "shared_ro"
    assert event.payload["bound_to"] == {"agent_id": "agent_supervisor"}
    assert event.payload["lease_status"] == "active"
    assert event.payload["provenance"]["decision_id"] == decision.decision_id
    assert event.payload["provenance"]["grant_basis"]["workspace"] == {"mode": "shared_ro"}

    projected = api.get_run_state(run_id).workspaces["workspace_shared_ro"]
    assert binding == projected
    assert binding["basis_event_id"] == event.event_id
    _assert_no_internal_repr(binding)


def test_bind_workspace_helper_uses_grants_and_refuses_unsupported_mode(tmp_path):
    api, run_id, result = _submit_pending_tool_request(tmp_path)
    decision = _decision_from(result, grants={"workspace": {"mode": "write"}})
    before_events = list(api.get_events(run_id))

    with pytest.raises(PermissionError, match="workspace mode is not supported"):
        api.bind_workspace(run_id, decision)

    assert api.get_events(run_id) == before_events
    assert _workspace_events(api, run_id) == []


def test_bind_workspace_helper_refuses_missing_workspace_grant_without_side_effects(tmp_path):
    api, run_id, result = _submit_pending_tool_request(tmp_path)
    decision = _decision_from(result, grants={"tools": ["write_artifact_tool"]})
    before_events = list(api.get_events(run_id))

    with pytest.raises(PermissionError, match="workspace grant is required"):
        api.bind_workspace(run_id, decision)

    assert api.get_events(run_id) == before_events
    assert api.get_run_state(run_id).workspaces == {}


def test_bind_workspace_helper_does_not_change_native_run_state_or_create_artifact(tmp_path):
    api, run_id, result = _submit_pending_tool_request(tmp_path)
    before_state = api.get_run_state(run_id)

    binding = api.bind_workspace(run_id, result["decision"])

    after_state = api.get_run_state(run_id)
    assert before_state.status == "pending_user_approval"
    assert after_state.status == "pending_user_approval"
    assert after_state.actions == before_state.actions
    assert after_state.artifacts == []
    assert binding["workspace_id"] in after_state.workspaces


def test_bind_workspace_helper_unknown_run_is_controlled_and_has_no_event(tmp_path):
    _api, _run_id, result = _submit_pending_tool_request(tmp_path / "source")
    target = server.InProcessServer(tmp_path / "target")

    with pytest.raises(ValueError, match="unknown run_id"):
        target.bind_workspace("run_missing", result["decision"])


def test_approval_tool_runner_demo_has_no_private_workspace_append_glue(tmp_path):
    source = Path(demo.__file__).read_text(encoding="utf-8")
    assert "_append_workspace_binding_event" not in source
    assert "server._append(" not in source

    result = demo._run_approval_tool_runner_spike(tmp_path)

    assert result["approval_tool_runner_ok"] is True
    assert result["workspace_binding_ok"] is True
    assert "workspace binding currently requires an explicit workspace.bound event in the spike" not in result["api_friction"]
