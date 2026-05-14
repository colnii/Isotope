from __future__ import annotations

import pytest

from isotope import checkpoint_store, event_store, projector
from isotope.errors import KernelPermissionError
from isotope.refs import ResourceRef, make_artifact_ref
from isotope.server import InProcessServer


def _server_with_run(tmp_path):
    api = InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="worker handoff helper")
    return api, run["run_id"]


def _delegation_intent() -> dict:
    return {
        "parent_agent_id": "agent_supervisor",
        "requested_worker_role": "worker",
        "requested_capabilities": {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    }


def _artifact_ref(run_id: str) -> ResourceRef:
    return make_artifact_ref(run_id, "artifact_worker_result_001")


def _source_artifact_ref(api: InProcessServer, run_id: str) -> ResourceRef:
    result = api.create_source_artifact(
        run_id,
        summary="worker result source artifact",
        content="deterministic worker result",
    )
    return result["artifact_ref"]


def _submit_worker_handoff(api: InProcessServer, run_id: str, **overrides):
    payload = {
        "delegation_intent": _delegation_intent(),
        "artifact_ref": _artifact_ref(run_id),
        "summary": "worker produced a deterministic result artifact",
    }
    payload.update(overrides)
    return api.submit_worker_handoff(run_id, **payload)


def _worker_events(api: InProcessServer, run_id: str):
    return [event for event in api.get_events(run_id) if event.event_type.startswith(("delegation.", "worker."))]


def test_worker_handoff_helper_exists_on_in_process_server():
    assert hasattr(InProcessServer, "submit_worker_handoff")


def test_worker_handoff_helper_appends_canonical_events_and_returns_projected_summary(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    artifact_ref = _source_artifact_ref(api, run_id)
    before_events = list(api.get_events(run_id))

    result = _submit_worker_handoff(api, run_id, artifact_ref=artifact_ref)

    after_events = list(api.get_events(run_id))
    assert len(after_events) > len(before_events)
    event_types = [event.event_type for event in after_events]
    assert event_types[-6:] == [
        "delegation.proposed",
        "delegation.decided",
        "worker.created",
        "worker.started",
        "worker.result_handed_off",
        "worker.completed",
    ]
    assert result["status"] == "completed"
    assert result["worker_summary"]["status"] == "completed"
    assert result["worker_summary"]["result_refs"] == [artifact_ref.to_dict()]
    assert result["worker_summary"]["parent_agent_id"] == "agent_supervisor"
    assert result["result_ref"] == artifact_ref.to_dict()
    assert "content" not in result
    assert "full_content" not in result


def test_worker_handoff_helper_uses_policy_semantics_and_rejects_forged_decision_or_grants(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    before_events = list(api.get_events(run_id))
    intent = _delegation_intent()
    intent["decision"] = {
        "decision_id": "forged_decision",
        "outcome": "approved",
        "grants": {
            "tools": ["write_artifact_tool", "admin_tool"],
            "workspace": {"mode": "isolated_rw"},
            "budget": {"seconds": 9999},
        },
    }

    with pytest.raises(ValueError, match="decision|grants|forged|policy"):
        _submit_worker_handoff(api, run_id, delegation_intent=intent)

    assert api.get_events(run_id) == before_events
    assert _worker_events(api, run_id) == []


def test_worker_handoff_helper_rejects_malformed_intent_without_partial_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    before_events = list(api.get_events(run_id))
    bad_intent = _delegation_intent()
    bad_intent.pop("requested_worker_role")

    with pytest.raises(ValueError, match="requested_worker_role|delegation intent"):
        _submit_worker_handoff(api, run_id, delegation_intent=bad_intent)

    assert api.get_events(run_id) == before_events
    assert _worker_events(api, run_id) == []


def test_worker_handoff_helper_rejects_malformed_artifact_ref_without_partial_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    before_events = list(api.get_events(run_id))
    bad_ref = ResourceRef(ref_type="memory", scope="run", run_id=run_id, artifact_id="artifact_worker_result_001")

    with pytest.raises(ValueError, match="artifact ResourceRef|artifact_ref"):
        _submit_worker_handoff(api, run_id, artifact_ref=bad_ref)

    assert api.get_events(run_id) == before_events
    assert _worker_events(api, run_id) == []


def test_worker_handoff_helper_rejects_unknown_artifact_ref_without_partial_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="unknown artifact|artifact.created|not found"):
        _submit_worker_handoff(api, run_id, artifact_ref=_artifact_ref(run_id))

    assert api.get_events(run_id) == before_events
    assert _worker_events(api, run_id) == []


def test_worker_handoff_helper_projects_denied_delegation_audit_without_worker_events(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    artifact_ref = _source_artifact_ref(api, run_id)
    intent = _delegation_intent()
    intent["requested_capabilities"]["tools"] = []
    before_events = list(api.get_events(run_id))

    with pytest.raises(KernelPermissionError) as raised:
        _submit_worker_handoff(api, run_id, artifact_ref=artifact_ref, delegation_intent=intent)

    assert raised.value.code == "worker_handoff_denied"
    assert raised.value.category == "policy"
    assert raised.value.retryable is False

    after_events = list(api.get_events(run_id))
    appended = after_events[len(before_events):]
    assert [event.event_type for event in appended] == [
        "delegation.proposed",
        "delegation.decided",
    ]
    assert appended[1].payload["outcome"] == "denied"
    assert appended[1].payload["reason_codes"] == ["tool_not_requested"]
    assert [event for event in after_events if event.event_type.startswith("worker.")] == []

    state = api.get_run_state(run_id)
    delegation_id = appended[0].payload["delegation_id"]
    assert state.delegations[delegation_id]["status"] == "denied"
    assert state.delegations[delegation_id]["outcome"] == "denied"
    assert state.delegations[delegation_id]["reason_codes"] == ["tool_not_requested"]
    assert state.delegations[delegation_id]["grants"] == {
        "tools": [],
        "workspace": {"mode": "none"},
        "budget": {"seconds": 0},
    }
    assert state.workers == {}


def test_worker_handoff_helper_replay_restores_worker_summary(tmp_path):
    api, run_id = _server_with_run(tmp_path)
    artifact_ref = _source_artifact_ref(api, run_id)
    result = _submit_worker_handoff(api, run_id, artifact_ref=artifact_ref)

    replayed = projector.RunProjector().rebuild(run_id, api.event_store)

    worker_id = result["worker_id"]
    assert replayed.workers[worker_id] == result["worker_summary"]
    assert replayed.workers[worker_id]["result_refs"] == [artifact_ref.to_dict()]


def test_worker_handoff_helper_checkpoint_rebuild_restores_worker_summary(tmp_path):
    api, run_id = _server_with_run(tmp_path / "events")
    result = _submit_worker_handoff(api, run_id, artifact_ref=_source_artifact_ref(api, run_id))
    canonical_events = api.get_events(run_id)
    events_store = event_store.FileEventStore(tmp_path / "replay")
    for event in canonical_events:
        events_store.append(event)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path / "checkpoints")
    checkpoint = projector.RunProjector().create_checkpoint(run_id, canonical_events[:4])
    checkpoints.save_checkpoint(run_id, checkpoint)

    restored = projector.RunProjector().rebuild_with_checkpoint(run_id, events_store, checkpoints)

    assert restored.workers[result["worker_id"]] == result["worker_summary"]


def test_worker_handoff_helper_keeps_app_away_from_private_append(tmp_path):
    api, run_id = _server_with_run(tmp_path)

    result = _submit_worker_handoff(api, run_id, artifact_ref=_source_artifact_ref(api, run_id))

    assert result["private_append_required"] is False
    assert "run.completed" not in [event.event_type for event in api.get_events(run_id)]
