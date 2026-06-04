import pytest

import isotope.platform.state.checkpoint_store as checkpoint_store
import isotope.platform.events.events as events
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server


def _completed_run(root):
    api = server.InProcessServer(root)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="produce a hello artifact")
    api.submit_input(run["run_id"], "hello")
    return api, run["run_id"]


def test_get_run_state_default_uses_checkpoint_store(tmp_path, monkeypatch):
    api, run_id = _completed_run(tmp_path)
    calls = []
    original_rebuild_with_checkpoint = projector.RunProjector.rebuild_with_checkpoint

    def spy_rebuild_with_checkpoint(self, run_id_arg, event_store, checkpoint_store_arg, *args, **kwargs):
        calls.append((run_id_arg, checkpoint_store_arg))
        return original_rebuild_with_checkpoint(self, run_id_arg, event_store, checkpoint_store_arg, *args, **kwargs)

    monkeypatch.setattr(projector.RunProjector, "rebuild_with_checkpoint", spy_rebuild_with_checkpoint)

    state = api.get_run_state(run_id)

    assert calls == [(run_id, api.checkpoint_store)]
    assert state.status == "completed"
    assert state.artifacts[0]["summary"] == "hello artifact"


def test_get_run_state_with_checkpoint_store_matches_full_rebuild(tmp_path, monkeypatch):
    writer, run_id = _completed_run(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    projector.RunProjector().save_checkpoint(run_id, writer.event_store, checkpoints)
    calls = []
    original_rebuild_with_checkpoint = projector.RunProjector.rebuild_with_checkpoint

    def spy_rebuild_with_checkpoint(self, run_id_arg, event_store, checkpoint_store_arg, *args, **kwargs):
        calls.append((run_id_arg, checkpoint_store_arg))
        return original_rebuild_with_checkpoint(self, run_id_arg, event_store, checkpoint_store_arg, *args, **kwargs)

    monkeypatch.setattr(projector.RunProjector, "rebuild_with_checkpoint", spy_rebuild_with_checkpoint)
    reader = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)

    state = reader.get_run_state(run_id)

    assert calls == [(run_id, checkpoints)]
    assert state == projector.RunProjector().rebuild(run_id, writer.event_store)


def test_server_does_not_return_tampered_checkpoint_state(tmp_path):
    writer, run_id = _completed_run(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    checkpoint = projector.RunProjector().create_checkpoint(run_id, writer.event_store.list_events(run_id))
    checkpoint.pop("integrity")
    checkpoint["state"]["current_agent"] = "agent_tampered"
    checkpoint["state"]["actions"]["exec_tampered"] = {"execution_id": "exec_tampered", "status": "completed"}
    checkpoints.save_checkpoint(run_id, checkpoint)
    reader = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)

    state = reader.get_run_state(run_id)

    assert state.current_agent == "agent_supervisor"
    assert "exec_tampered" not in state.actions
    assert state == projector.RunProjector().rebuild(run_id, writer.event_store)


def test_server_get_run_state_does_not_create_checkpoint(tmp_path):
    writer, run_id = _completed_run(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    reader = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)

    state = reader.get_run_state(run_id)

    assert state == projector.RunProjector().rebuild(run_id, writer.event_store)
    assert not checkpoints.checkpoint_path(run_id).exists()


def test_lifecycle_invalid_event_log_still_fails_with_checkpoint_store(tmp_path):
    writer, run_id = _completed_run(tmp_path)
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    projector.RunProjector().save_checkpoint(run_id, writer.event_store, checkpoints)
    writer.event_store.append(
        events.CanonicalEvent(
            event_id="evt_invalid_after_completed",
            run_id=run_id,
            event_type="action.started",
            payload={
                "execution_id": "exec_invalid",
                "proposal_id": "prop_invalid",
                "decision_id": "dec_invalid",
            },
            created_at="2026-04-27T00:00:01Z",
        )
    )
    reader = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)

    with pytest.raises(ValueError, match="event after run.completed"):
        reader.get_run_state(run_id)


def test_server_create_checkpoint_saves_checkpoint(tmp_path):
    api, run_id = _completed_run(tmp_path)

    result = api.create_checkpoint(run_id)

    assert result["status"] == "saved"
    assert result["run_id"] == run_id
    assert result["basis_event_id"].startswith("evt_")
    assert api.checkpoint_store.checkpoint_path(run_id).exists()
