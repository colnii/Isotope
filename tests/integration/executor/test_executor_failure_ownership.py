import pytest

import isotope.runtime.in_process.action_compiler as action_compiler
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
from isotope.platform.schemas.actions import PolicyDecision
import isotope.runtime.in_process as server
import isotope.workspace as workspace
from isotope.platform.events.events import CanonicalEvent


def _proposal(text="hello"):
    return action_compiler.ActionCompiler().compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": text,
            "requested_tools": ["write_artifact_tool"],
            "workspace_mode": "shared_ro",
            "budget": {"seconds": 30},
        },
        {
            "run_id": "run_001",
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )


def _decision(proposal, grants=None):
    return PolicyDecision(
        decision_id="dec_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants=grants
        or {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=[],
    )


def _runner(tmp_path):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
    )


def _event_types(store, run_id="run_001"):
    return [event.event_type for event in store.list_events(run_id)]


def _events_by_type(store, event_type, run_id="run_001"):
    return [event for event in store.list_events(run_id) if event.event_type == event_type]


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "failure ownership")
    return api, run["run_id"]


def test_artifact_side_effect_failure_appends_started_then_failed_with_same_execution_id(tmp_path, monkeypatch):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)

    def fail_create_artifact(*args, **kwargs):
        raise RuntimeError("artifact write failed")

    monkeypatch.setattr(runner.artifact_store, "create_artifact", fail_create_artifact)

    with pytest.raises(RuntimeError, match="artifact write failed"):
        runner.execute(decision, proposal)

    event_types = _event_types(runner.event_store)
    assert event_types == ["action.started", "action.failed"]

    started = _events_by_type(runner.event_store, "action.started")[0]
    failed = _events_by_type(runner.event_store, "action.failed")[0]
    assert failed.payload["execution_id"] == started.payload["execution_id"]
    assert failed.payload["proposal_id"] == proposal.proposal_id
    assert failed.payload["decision_id"] == decision.decision_id
    assert failed.payload["status"] == "failed"
    assert "artifact write failed" in failed.payload["error"]
    assert "artifact.created" not in event_types
    assert "action.completed" not in event_types


def test_workspace_binding_failure_appends_started_then_failed_and_creates_no_artifact(tmp_path):
    proposal = _proposal()
    decision = _decision(
        proposal,
        grants={
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "isolated_rw"},
            "budget": {"seconds": 30},
        },
    )
    runner = _runner(tmp_path)

    with pytest.raises(PermissionError, match="workspace mode is not supported"):
        runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    assert [event.event_type for event in events] == ["action.started", "action.failed"]
    failed = events[1]
    assert failed.payload["execution_id"] == events[0].payload["execution_id"]
    assert failed.payload["proposal_id"] == proposal.proposal_id
    assert failed.payload["decision_id"] == decision.decision_id
    assert failed.payload["status"] == "failed"
    assert "workspace mode is not supported" in failed.payload["error"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_server_failure_path_does_not_duplicate_executor_owned_failure_events(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)

    def executor_owned_failure(decision, proposal):
        execution_id = "exec_owned_failed"
        api.event_store.append(
            CanonicalEvent(
                event_id="evt_owned_started",
                run_id=proposal.run_id,
                event_type="action.started",
                payload={
                    "execution_id": execution_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                },
                created_at="2026-04-27T00:00:00Z",
            )
        )
        api.event_store.append(
            CanonicalEvent(
                event_id="evt_owned_failed",
                run_id=proposal.run_id,
                event_type="action.failed",
                payload={
                    "execution_id": execution_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                    "status": "failed",
                    "error": "owned failure",
                    "error_reason_code": "tool_execution_failed",
                    "structured_error": {
                        "reason_code": "tool_execution_failed",
                        "message": "owned failure",
                    },
                },
                created_at="2026-04-27T00:00:01Z",
            )
        )
        raise RuntimeError("owned failure")

    monkeypatch.setattr(api.executor, "execute", executor_owned_failure)

    result = api.submit_tool_request(run_id, tool="write_artifact_tool", text="hello")

    event_types = _event_types(api.event_store, run_id)
    assert event_types.count("action.started") == 1
    assert event_types.count("action.failed") == 1
    assert result["execution_id"] == "exec_owned_failed"


def test_failed_action_still_does_not_append_run_completed_and_rebuilds_from_event_log(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)

    def fail_create_artifact(*args, **kwargs):
        raise RuntimeError("deterministic artifact failure")

    monkeypatch.setattr(api.artifact_store, "create_artifact", fail_create_artifact)

    result = api.submit_tool_request(run_id, tool="write_artifact_tool", text="hello")
    fresh_api = server.InProcessServer(tmp_path)
    rebuilt_state = fresh_api.get_run_state(run_id)

    event_types = _event_types(api.event_store, run_id)
    assert result["status"] == "failed"
    assert "run.completed" not in event_types
    assert result["run_state"].status == "failed"
    assert rebuilt_state.status == "failed"
    assert rebuilt_state.actions[result["execution_id"]]["status"] == "failed"
