from isotope_kernel import artifact_store, event_store, events, projector


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
        created_at=f"2026-04-27T00:00:{event_id[-2:]}Z",
    )


def _canonical_events():
    return [
        _event(
            "evt_001",
            "run.created",
            {"run_id": "run_001"},
        ),
        _event(
            "evt_002",
            "agent.created",
            {"agent_id": "agent_supervisor"},
        ),
        _event(
            "evt_003",
            "action.proposed",
            {
                "proposal_id": "prop_001",
                "agent_id": "agent_supervisor",
                "action_type": "call_tool",
            },
        ),
        _event(
            "evt_004",
            "action.decided",
            {
                "decision_id": "dec_001",
                "proposal_id": "prop_001",
                "outcome": "approved",
            },
        ),
        _event(
            "evt_005",
            "action.started",
            {
                "execution_id": "exec_001",
                "proposal_id": "prop_001",
                "decision_id": "dec_001",
            },
        ),
        _event(
            "evt_006",
            "artifact.created",
            {
                "artifact": {
                    "ref": ARTIFACT_REF,
                    "artifact_type": "text",
                    "summary": "hello artifact",
                    "provenance": {"execution_id": "exec_001"},
                }
            },
        ),
        _event(
            "evt_007",
            "action.completed",
            {
                "execution_id": "exec_001",
                "status": "completed",
                "artifact_refs": [ARTIFACT_REF],
            },
        ),
        _event(
            "evt_008",
            "run.completed",
            {"status": "completed"},
        ),
    ]


def test_projector_builds_run_state_only_from_events():
    state = projector.RunProjector().project(_canonical_events())

    assert state.run_id == "run_001"
    assert state.status == "completed"
    assert state.current_agent == "agent_supervisor"
    assert state.actions["exec_001"]["status"] == "completed"
    assert state.artifacts == [
        {
            "ref": ARTIFACT_REF,
            "artifact_type": "text",
            "summary": "hello artifact",
            "provenance": {"execution_id": "exec_001"},
        }
    ]


def test_fresh_projector_rebuilds_equivalent_state_from_file_event_log(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    for event in _canonical_events():
        store.append(event)

    original_state = projector.RunProjector().project(_canonical_events())
    rebuilt_state = projector.RunProjector().rebuild("run_001", store)

    assert rebuilt_state == original_state


def test_projector_does_not_read_artifact_content_for_native_state(tmp_path, monkeypatch):
    def fail_on_content_read(*args, **kwargs):
        raise AssertionError("Projector must not read artifact content")

    monkeypatch.setattr(artifact_store.ArtifactStore, "get_content", fail_on_content_read)

    state = projector.RunProjector().project(_canonical_events())

    assert state.artifacts[0]["summary"] == "hello artifact"
    assert "content" not in state.artifacts[0]


def test_run_state_last_event_id_matches_replayed_event_log(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    for event in _canonical_events():
        store.append(event)

    state = projector.RunProjector().rebuild("run_001", store)

    assert state.last_event_id == "evt_008"
