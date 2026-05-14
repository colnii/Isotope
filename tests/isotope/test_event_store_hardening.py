import json

import pytest

from isotope import event_store, events, projector


def _event(
    event_id,
    *,
    run_id="run_001",
    event_type="run.event",
    payload=None,
    created_at="2026-04-27T00:00:00Z",
):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=run_id,
        event_type=event_type,
        payload={} if payload is None else payload,
        created_at=created_at,
    )


def test_list_events_preserves_append_order_for_same_run(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    appended = [
        _event("evt_003", created_at="2026-04-27T00:00:03Z"),
        _event("evt_001", created_at="2026-04-27T00:00:01Z"),
        _event("evt_002", created_at="2026-04-27T00:00:02Z"),
    ]

    for event in appended:
        store.append(event)

    replayed = store.list_events("run_001")

    assert [event.event_id for event in replayed] == ["evt_003", "evt_001", "evt_002"]


def test_projector_rebuild_uses_event_log_order_not_event_id_or_created_at(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(
        _event(
            "evt_003",
            event_type="run.created",
            payload={"run_id": "run_001"},
            created_at="2026-04-27T00:00:03Z",
        )
    )
    store.append(
        _event(
            "evt_002",
            event_type="agent.created",
            payload={"agent_id": "agent_from_middle_append"},
            created_at="2026-04-27T00:00:02Z",
        )
    )
    store.append(
        _event(
            "evt_001",
            event_type="agent.created",
            payload={"agent_id": "agent_from_last_append"},
            created_at="2026-04-27T00:00:01Z",
        )
    )

    state = projector.RunProjector().rebuild("run_001", store)

    assert state.current_agent == "agent_from_last_append"
    assert state.last_event_id == "evt_001"


def test_duplicate_event_id_is_rejected_within_same_run(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    store.append(_event("evt_duplicate"))

    with pytest.raises(ValueError, match="duplicate event_id"):
        store.append(_event("evt_duplicate"))


def test_same_event_id_is_allowed_across_different_runs(tmp_path):
    store = event_store.FileEventStore(tmp_path)

    store.append(_event("evt_shared", run_id="run_001"))
    store.append(_event("evt_shared", run_id="run_002"))

    assert [event.event_id for event in store.list_events("run_001")] == ["evt_shared"]
    assert [event.event_id for event in store.list_events("run_002")] == ["evt_shared"]


def test_append_rejects_non_canonical_event(tmp_path):
    store = event_store.FileEventStore(tmp_path)

    with pytest.raises(TypeError, match="CanonicalEvent"):
        store.append({"event_id": "evt_001", "run_id": "run_001"})


def test_append_rejects_event_run_id_that_does_not_match_target_run(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    event = _event("evt_001", run_id="run_001")

    with pytest.raises(ValueError, match="run_id mismatch"):
        store.append(event, run_id="run_002")

    assert not store.event_path("run_001").exists()
    assert not store.event_path("run_002").exists()


def test_list_events_fails_fast_on_malformed_json_line(tmp_path):
    store = event_store.FileEventStore(tmp_path)
    path = store.event_path("run_001")
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                json.dumps(_event("evt_001").to_dict()),
                "{not-json",
                json.dumps(_event("evt_002").to_dict()),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="malformed JSON"):
        store.list_events("run_001")
