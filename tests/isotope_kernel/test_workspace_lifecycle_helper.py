from __future__ import annotations

import json
from typing import Any

from isotope_kernel.checkpoint_store import FileCheckpointStore
from isotope_kernel.projector import RunProjector
from isotope_kernel.server import InProcessServer


def _new_run(tmp_path):
    api = InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="workspace lifecycle helper")
    return api, run["run_id"]


def _decision(api: InProcessServer, run_id: str):
    result = api.submit_tool_request(
        run_id,
        tool="write_artifact_tool",
        text="workspace lifecycle basis",
        requires_approval=True,
    )
    return result["decision"], result


def _workspace_events(api: InProcessServer, run_id: str, event_type: str):
    return [event for event in api.get_events(run_id) if event.event_type == event_type]


def _assert_no_content(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    assert "workspace file body" not in serialized
    assert "full_content" not in serialized
    assert '"content"' not in serialized


def test_create_workspace_lease_helper_appends_canonical_event_and_returns_read_model(tmp_path):
    api, run_id = _new_run(tmp_path)
    decision, request = _decision(api, run_id)
    before_events = list(api.get_events(run_id))

    lease = api.create_workspace_lease(
        run_id,
        decision,
        created_by={"proposal_id": request["proposal_id"]},
        bound_to={"agent_id": "agent_supervisor"},
    )

    after_events = list(api.get_events(run_id))
    lease_events = _workspace_events(api, run_id, "workspace.lease_created")
    assert len(after_events) == len(before_events) + 1
    assert len(lease_events) == 1
    event = lease_events[0]
    assert event.payload["workspace_id"] == "workspace_shared_ro"
    assert event.payload["run_id"] == run_id
    assert event.payload["mode"] == "shared_ro"
    assert event.payload["lease_status"] == "created"
    assert event.payload["granted_by"] == {"decision_id": decision.decision_id}
    assert event.payload["created_by"] == {"proposal_id": request["proposal_id"]}
    assert event.payload["provenance"]["grant_basis"]["workspace"] == {"mode": "shared_ro"}
    assert lease == api.get_run_state(run_id).workspaces["workspace_shared_ro"]
    assert lease["basis_event_id"] == event.event_id


def test_workspace_artifact_capture_helper_links_existing_artifact_ref_without_content(tmp_path):
    api, run_id = _new_run(tmp_path)
    decision, request = _decision(api, run_id)
    api.create_workspace_lease(
        run_id,
        decision,
        created_by={"proposal_id": request["proposal_id"]},
    )
    source = api.create_source_artifact(
        run_id,
        summary="captured workspace summary",
        content="workspace file body must stay in artifact storage",
    )
    artifact_record = api.get_artifact_record(source["artifact_ref"])
    before_events = list(api.get_events(run_id))

    capture = api.capture_workspace_artifact(
        run_id,
        workspace_id="workspace_shared_ro",
        artifact_ref=source["artifact_ref"],
        captured_by={"execution_id": source["execution_id"]},
    )

    after_events = list(api.get_events(run_id))
    capture_events = _workspace_events(api, run_id, "workspace.artifact_captured")
    assert len(after_events) == len(before_events) + 1
    assert len(capture_events) == 1
    event = capture_events[0]
    assert event.payload["artifact_ref"] == source["artifact_ref"].to_dict()
    assert event.payload["captured_by"] == {"execution_id": source["execution_id"]}
    assert event.payload["provenance"]["artifact_event_id"] == artifact_record["basis_event_id"]
    assert event.payload["provenance"]["basis_event_id"] == artifact_record["basis_event_id"]
    assert capture["workspace"]["artifact_refs"] == [source["artifact_ref"].to_dict()]
    assert capture["basis_event_id"] == event.event_id
    _assert_no_content(capture)


def test_release_workspace_helper_uses_latest_workspace_basis_and_checkpoint_rebuild(tmp_path):
    checkpoints = FileCheckpointStore(tmp_path)
    api = InProcessServer(tmp_path, checkpoint_store=checkpoints)
    session = api.create_session()
    run_id = api.create_run(session["session_id"], goal="workspace release helper")["run_id"]
    decision, request = _decision(api, run_id)
    lease = api.create_workspace_lease(
        run_id,
        decision,
        created_by={"proposal_id": request["proposal_id"]},
    )
    source = api.create_source_artifact(run_id, summary="summary", content="workspace file body")
    capture = api.capture_workspace_artifact(
        run_id,
        workspace_id=lease["workspace_id"],
        artifact_ref=source["artifact_ref"],
        captured_by={"execution_id": source["execution_id"]},
    )
    before_events = list(api.get_events(run_id))

    release = api.release_workspace(
        run_id,
        workspace_id=lease["workspace_id"],
        released_by={"agent_id": "agent_supervisor"},
        reason="finished deterministic workspace lifecycle",
    )

    release_events = _workspace_events(api, run_id, "workspace.released")
    assert len(api.get_events(run_id)) == len(before_events) + 1
    assert len(release_events) == 1
    event = release_events[0]
    assert event.payload["basis_event_id"] == capture["basis_event_id"]
    assert release["workspace"]["lease_status"] == "released"
    assert release["workspace"]["release_reason"] == "finished deterministic workspace lifecycle"
    api.save_checkpoint_for_run(run_id)
    direct = RunProjector().rebuild(run_id, api.event_store)
    restored = RunProjector().rebuild_with_checkpoint(run_id, api.event_store, checkpoints)
    assert restored.workspaces == direct.workspaces
