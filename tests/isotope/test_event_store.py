import json

import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events


def test_event_store_appends_jsonl_events(tmp_path):
    assert hasattr(events, "CanonicalEvent")
    assert hasattr(event_store, "FileEventStore")

    store = event_store.FileEventStore(tmp_path)
    first = events.CanonicalEvent(
        event_id="evt_001",
        run_id="run_001",
        event_type="run.created",
        payload={"status": "running"},
        created_at="2026-04-27T00:00:00Z",
    )
    second = events.CanonicalEvent(
        event_id="evt_002",
        run_id="run_001",
        event_type="action.proposed",
        payload={"proposal_id": "prop_001"},
        created_at="2026-04-27T00:00:01Z",
    )

    store.append(first)
    store.append(second)

    path = store.event_path("run_001")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event_id"] for line in lines] == ["evt_001", "evt_002"]


def test_event_store_has_no_update_or_delete_api(tmp_path):
    assert hasattr(event_store, "FileEventStore")

    store = event_store.FileEventStore(tmp_path)

    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")
    assert not hasattr(store, "remove")
