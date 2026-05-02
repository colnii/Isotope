import json
from typing import Any

from isotope_kernel.demo import run_demo


SCENARIO = "approval-tool-runner"

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "raw_content",
    "raw_artifact_content",
    "workspace_file_content",
}


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_approval_tool_runner_event_order_shows_pause_then_resume(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)
    event_types = data["event_types"]

    assert "approval.requested" in event_types
    assert "approval.resolved" in event_types
    assert "workspace.bound" in event_types
    assert "action.started" in event_types
    assert "artifact.created" in event_types
    assert event_types.index("approval.requested") < event_types.index("approval.resolved")
    assert event_types.index("approval.resolved") < event_types.index("action.started")
    assert event_types.index("workspace.bound") < event_types.index("action.started")


def test_approval_tool_runner_workspace_binding_is_visible_read_model(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)
    binding = data["workspace_binding"]

    assert binding["workspace_id"] == "workspace_shared_ro"
    assert binding["run_id"] == data["run_id"]
    assert binding["mode"] == "shared_ro"
    assert binding["lease_status"] == "active"
    assert binding["bound_to"]["agent_id"] == "agent_supervisor"
    assert binding["provenance"]["grant_basis"]["workspace"]["mode"] == "shared_ro"
    assert binding["basis_event_id"]
    assert data["workspace_binding_ok"] is True


def test_approval_tool_runner_artifact_handoff_uses_structured_ref(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)
    ref = data["artifact_ref"]

    assert ref["ref_type"] == "artifact"
    assert ref["scope"] == "run"
    assert ref["run_id"] == data["run_id"]
    assert ref["artifact_id"]
    assert data["artifact_summary"]
    assert data["artifact_handoff_ok"] is True
    _assert_no_forbidden_content_keys(data)


def test_approval_tool_runner_replay_and_checkpoint_include_workspace_binding(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)

    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["replay_workspaces_ok"] is True
    assert data["checkpoint_workspaces_ok"] is True
    assert "workspace_shared_ro" in data["checkpoint_workspaces"]
    assert "workspace_shared_ro" in data["replay_workspaces"]


def test_approval_tool_runner_state_does_not_depend_on_workspace_file_content(tmp_path):
    data = run_demo(tmp_path, scenario=SCENARIO)
    serialized = json.dumps(data, sort_keys=True)

    assert data["filesystem_mutation_status"] == "not_used"
    assert "workspace_file_content" not in serialized
    assert "real filesystem" not in serialized.lower()
