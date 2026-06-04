import pytest

import isotope.platform.state.checkpoint_store as checkpoint_store
import isotope.platform.events.events as events
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server


def _completed_run(root, checkpoints=None):
    api = server.InProcessServer(root, checkpoint_store=checkpoints)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="produce a hello artifact")
    api.submit_input(run["run_id"], "hello")
    return api, run["run_id"]


def _event(event_id, run_id, event_type, payload):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
        created_at="2026-04-27T00:00:00Z",
    )


def test_save_checkpoint_for_run_uses_default_checkpoint_store(tmp_path):
    api, run_id = _completed_run(tmp_path)

    result = api.save_checkpoint_for_run(run_id)
    loaded = api.checkpoint_store.load_latest_checkpoint(run_id)

    assert result == {"status": "saved", "run_id": run_id, "basis_event_id": loaded["basis_event_id"]}
    assert api.checkpoint_store.checkpoint_path(run_id).exists()


def test_save_checkpoint_for_run_saves_checkpoint_via_projector_boundary(tmp_path, monkeypatch):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api, run_id = _completed_run(tmp_path, checkpoints)
    calls = []
    original_save_checkpoint = projector.RunProjector.save_checkpoint

    def spy_save_checkpoint(self, run_id_arg, event_store, checkpoint_store_arg, *args, **kwargs):
        calls.append((run_id_arg, event_store, checkpoint_store_arg))
        return original_save_checkpoint(self, run_id_arg, event_store, checkpoint_store_arg, *args, **kwargs)

    monkeypatch.setattr(projector.RunProjector, "save_checkpoint", spy_save_checkpoint)

    result = api.save_checkpoint_for_run(run_id)
    loaded = checkpoints.load_latest_checkpoint(run_id)

    assert calls == [(run_id, api.event_store, checkpoints)]
    assert result == {"status": "saved", "run_id": run_id, "basis_event_id": loaded["basis_event_id"]}
    assert checkpoints.checkpoint_path(run_id).exists()
    assert loaded["run_id"] == run_id


def test_saved_checkpoint_can_power_server_get_run_state(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api, run_id = _completed_run(tmp_path, checkpoints)
    api.save_checkpoint_for_run(run_id)

    state = api.get_run_state(run_id)

    assert state == projector.RunProjector().rebuild(run_id, api.event_store)


def test_save_checkpoint_for_run_does_not_modify_event_log(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api, run_id = _completed_run(tmp_path, checkpoints)
    before = [event.event_id for event in api.event_store.list_events(run_id)]

    api.save_checkpoint_for_run(run_id)

    after = [event.event_id for event in api.event_store.list_events(run_id)]
    assert after == before


def test_save_checkpoint_for_run_empty_event_log_fails_without_writing_checkpoint(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    run_id = "run_empty"

    with pytest.raises(ValueError, match="unknown run_id"):
        api.save_checkpoint_for_run(run_id)

    assert not checkpoints.checkpoint_path(run_id).exists()


def test_save_checkpoint_for_run_lifecycle_invalid_event_log_fails_without_writing_checkpoint(tmp_path):
    run_id = "run_bad"
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    api.event_store.append(_event("evt_001", run_id, "run.created", {"run_id": run_id}))
    api.event_store.append(
        _event(
            "evt_002",
            run_id,
            "action.completed",
            {
                "execution_id": "exec_missing",
                "status": "completed",
                "artifact_refs": [],
            },
        )
    )

    with pytest.raises(ValueError, match="action.completed before action.started"):
        api.save_checkpoint_for_run(run_id)

    assert not checkpoints.checkpoint_path(run_id).exists()


def test_create_checkpoint_saves_checkpoint(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api, run_id = _completed_run(tmp_path, checkpoints)

    result = api.create_checkpoint(run_id)

    loaded = checkpoints.load_latest_checkpoint(run_id)
    assert result == {"status": "saved", "run_id": run_id, "basis_event_id": loaded["basis_event_id"]}
