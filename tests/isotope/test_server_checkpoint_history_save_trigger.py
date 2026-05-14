import pytest

from isotope import checkpoint_store, event_store, events, projector, server


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
}


def _event(event_id, event_type, payload):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-04-28T00:00:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _agent_created():
    return _event("evt_002", "agent.created", {"agent_id": "agent_supervisor"})


def _proposed():
    return _event(
        "evt_003",
        "action.proposed",
        {
            "proposal_id": "prop_001",
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _decided():
    return _event(
        "evt_004",
        "action.decided",
        {
            "decision_id": "dec_001",
            "proposal_id": "prop_001",
            "outcome": "approved",
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _started():
    return _event(
        "evt_005",
        "action.started",
        {
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
        },
    )


def _artifact_created():
    return _event(
        "evt_006",
        "artifact.created",
        {
            "artifact": {
                "ref": ARTIFACT_REF,
                "artifact_type": "text",
                "summary": "hello artifact",
                "provenance": {"execution_id": "exec_001", "proposal_id": "prop_001", "decision_id": "dec_001"},
            }
        },
    )


def _completed():
    return _event(
        "evt_007",
        "action.completed",
        {
            "execution_id": "exec_001",
            "status": "completed",
            "artifact_refs": [ARTIFACT_REF],
        },
    )


def _run_completed():
    return _event("evt_008", "run.completed", {"status": "completed"})


def _happy_path_events():
    return [
        _run_created(),
        _agent_created(),
        _proposed(),
        _decided(),
        _started(),
        _artifact_created(),
        _completed(),
        _run_completed(),
    ]


def _write_events(store, canonical_events):
    for event in canonical_events:
        store.append(event)


def _event_log_text(root, run_id="run_001"):
    return (root / "runs" / run_id / "events.jsonl").read_text(encoding="utf-8")


def _checkpoint_dir(root, run_id="run_001"):
    return root / "runs" / run_id / "checkpoints"


def _history_candidate_files(root, run_id="run_001"):
    checkpoint_dir = _checkpoint_dir(root, run_id)
    if not checkpoint_dir.exists():
        return []
    return sorted(path for path in checkpoint_dir.glob("*.json") if path.name != "latest.json")


def _latest_checkpoint_path(root, run_id="run_001"):
    return root / "runs" / run_id / "checkpoints" / "latest.json"


def _server_with_events(root, checkpoints=None):
    api = server.InProcessServer(root, checkpoint_store=checkpoints)
    _write_events(api.event_store, _happy_path_events())
    return api


def test_server_exposes_explicit_checkpoint_history_save_trigger(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert hasattr(api, "save_checkpoint_history_for_run")


def test_save_checkpoint_history_for_run_requires_checkpoint_store(tmp_path):
    api = _server_with_events(tmp_path)

    result = api.save_checkpoint_history_for_run("run_001")

    assert result["status"] == "not_enabled"
    assert result["capability"] == "checkpoint_history"
    assert result["error"]["code"] == "not_enabled"
    assert _history_candidate_files(tmp_path) == []
    assert not _latest_checkpoint_path(tmp_path).exists()


def test_save_checkpoint_history_for_run_delegates_to_projector_history_save(
    tmp_path,
    monkeypatch,
):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = _server_with_events(tmp_path, checkpoints)
    calls = []

    def recording_save_checkpoint_history(self, run_id, event_store_arg, checkpoint_store_arg, *args, **kwargs):
        calls.append((run_id, event_store_arg, checkpoint_store_arg))
        return {
            "run_id": run_id,
            "basis_event_id": "evt_008",
            "state": {"must_not_be_returned": True},
        }

    monkeypatch.setattr(projector.RunProjector, "save_checkpoint_history", recording_save_checkpoint_history)

    result = api.save_checkpoint_history_for_run("run_001")

    assert calls == [("run_001", api.event_store, checkpoints)]
    assert result == {
        "status": "saved",
        "run_id": "run_001",
        "basis_event_id": "evt_008",
        "checkpoint_kind": "history",
    }


def test_save_checkpoint_history_for_run_does_not_call_checkpoint_store_directly(
    tmp_path,
    monkeypatch,
):
    class DirectWriteForbiddenCheckpointStore:
        def save_checkpoint_history(self, run_id, checkpoint):
            raise AssertionError("server must delegate history save to projector")

    api = _server_with_events(tmp_path, DirectWriteForbiddenCheckpointStore())

    def fake_projector_history_save(self, run_id, event_store_arg, checkpoint_store_arg, *args, **kwargs):
        return {"run_id": run_id, "basis_event_id": "evt_008", "state": {"opaque": True}}

    monkeypatch.setattr(projector.RunProjector, "save_checkpoint_history", fake_projector_history_save)

    result = api.save_checkpoint_history_for_run("run_001")

    assert result["status"] == "saved"
    assert result["checkpoint_kind"] == "history"


def test_save_checkpoint_history_for_run_does_not_call_latest_projector_save(
    tmp_path,
    monkeypatch,
):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = _server_with_events(tmp_path, checkpoints)

    def fail_latest_save(self, run_id, event_store_arg, checkpoint_store_arg, *args, **kwargs):
        raise AssertionError("history save trigger must not call latest save")

    def fake_projector_history_save(self, run_id, event_store_arg, checkpoint_store_arg, *args, **kwargs):
        return {"run_id": run_id, "basis_event_id": "evt_008", "state": {"opaque": True}}

    monkeypatch.setattr(projector.RunProjector, "save_checkpoint", fail_latest_save)
    monkeypatch.setattr(projector.RunProjector, "save_checkpoint_history", fake_projector_history_save)

    result = api.save_checkpoint_history_for_run("run_001")

    assert result["basis_event_id"] == "evt_008"
    assert not _latest_checkpoint_path(tmp_path).exists()


def test_save_checkpoint_history_for_run_saves_history_without_latest(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = _server_with_events(tmp_path, checkpoints)

    result = api.save_checkpoint_history_for_run("run_001")

    candidates = checkpoints.load_checkpoint_candidates("run_001")
    assert result == {
        "status": "saved",
        "run_id": "run_001",
        "basis_event_id": "evt_008",
        "checkpoint_kind": "history",
    }
    assert "state" not in result
    assert [candidate["basis_event_id"] for candidate in candidates] == ["evt_008"]
    assert _history_candidate_files(tmp_path)
    assert not _latest_checkpoint_path(tmp_path).exists()


def test_save_checkpoint_history_for_run_does_not_modify_event_log(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = _server_with_events(tmp_path, checkpoints)
    before = _event_log_text(tmp_path)

    api.save_checkpoint_history_for_run("run_001")

    assert _event_log_text(tmp_path) == before


def test_save_checkpoint_history_for_run_empty_event_log_fails_without_writing_history(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)

    with pytest.raises(ValueError, match="cannot create checkpoint from empty events"):
        api.save_checkpoint_history_for_run("run_001")

    assert _history_candidate_files(tmp_path) == []
    assert not _latest_checkpoint_path(tmp_path).exists()


def test_save_checkpoint_history_for_run_lifecycle_invalid_event_log_fails_without_writing_history(
    tmp_path,
):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    _write_events(
        api.event_store,
        [
            _run_created(),
            _event(
                "evt_002",
                "action.completed",
                {
                    "execution_id": "exec_001",
                    "status": "completed",
                    "artifact_refs": [ARTIFACT_REF],
                },
            ),
        ],
    )

    with pytest.raises(ValueError, match="action.completed before action.started"):
        api.save_checkpoint_history_for_run("run_001")

    assert _history_candidate_files(tmp_path) == []
    assert not _latest_checkpoint_path(tmp_path).exists()


def test_save_checkpoint_history_for_run_malformed_event_stream_fails_without_writing_history(
    tmp_path,
):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = server.InProcessServer(tmp_path, checkpoint_store=checkpoints)
    _write_events(api.event_store, [_run_created(), _proposed(), _event("evt_004", "action.decided", {})])

    with pytest.raises(ValueError, match="action.decided missing required field"):
        api.save_checkpoint_history_for_run("run_001")

    assert _history_candidate_files(tmp_path) == []
    assert not _latest_checkpoint_path(tmp_path).exists()


def test_save_checkpoint_for_run_remains_latest_only_and_does_not_write_history_candidate(tmp_path):
    checkpoints = checkpoint_store.FileCheckpointStore(tmp_path)
    api = _server_with_events(tmp_path, checkpoints)

    result = api.save_checkpoint_for_run("run_001")

    assert result == {"status": "saved", "run_id": "run_001", "basis_event_id": "evt_008"}
    assert checkpoints.load_latest_checkpoint("run_001")["basis_event_id"] == "evt_008"
    assert _history_candidate_files(tmp_path) == []


def test_create_checkpoint_remains_not_enabled(tmp_path):
    api = _server_with_events(tmp_path)

    result = api.create_checkpoint("run_001")

    assert result["status"] == "not_enabled"
    assert result["capability"] == "checkpoint"
    assert result["error"]["code"] == "not_enabled"
