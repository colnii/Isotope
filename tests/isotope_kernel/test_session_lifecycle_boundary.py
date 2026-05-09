from __future__ import annotations

import json

from isotope_kernel import server


def _event_records(root):
    records = []
    for path in sorted(root.rglob("events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def test_session_creation_is_canonical_event_backed(tmp_path):
    api = server.InProcessServer(tmp_path)

    session = api.create_session()

    session_events = [
        record
        for record in _event_records(tmp_path)
        if record["event_type"] == "session.created"
        and record["payload"].get("session_id") == session["session_id"]
    ]
    assert len(session_events) == 1
    assert session_events[0]["payload"] == {
        "session_id": session["session_id"],
        "status": "active",
    }


def test_session_state_is_replay_truth_not_hidden_server_metadata(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="session lifecycle")

    rebuilt_api = server.InProcessServer(tmp_path)

    assert hasattr(rebuilt_api, "get_session_state")
    session_state = rebuilt_api.get_session_state(session["session_id"])
    assert session_state == {
        "session_id": session["session_id"],
        "status": "active",
        "run_ids": [run["run_id"]],
    }
