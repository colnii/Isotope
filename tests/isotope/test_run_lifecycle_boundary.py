from __future__ import annotations

import pytest

from isotope import events, projector, server


RUN_ID = "run_lifecycle_001"
SESSION_ID = "session_lifecycle_001"


def _event(event_id: str, event_type: str, payload: dict) -> events.CanonicalEvent:
    return events.CanonicalEvent(
        event_id=event_id,
        run_id=RUN_ID,
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-10T00:00:{event_id[-2:]}Z",
    )


def test_run_created_projects_session_goal_and_lifecycle_basis():
    state = projector.RunProjector().project(
        [
            _event(
                "evt_001",
                "run.created",
                {
                    "run_id": RUN_ID,
                    "session_id": SESSION_ID,
                    "goal": "prove lifecycle projection",
                },
            )
        ]
    )

    assert state.run_id == RUN_ID
    assert state.session_id == SESSION_ID
    assert state.goal == "prove lifecycle projection"
    assert state.created_event_id == "evt_001"
    assert state.status == "running"


def test_malformed_run_created_without_session_id_fails_fast():
    with pytest.raises(ValueError, match="run.created.*session_id"):
        projector.RunProjector().project(
            [
                _event(
                    "evt_001",
                    "run.created",
                    {
                        "run_id": RUN_ID,
                        "goal": "missing session",
                    },
                )
            ]
        )


def test_completed_run_rejects_ordinary_new_input(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="terminal input")
    api.submit_input(run["run_id"], "first")
    events_before = api.get_events(run["run_id"])

    with pytest.raises(ValueError, match="run.completed|terminal|completed"):
        api.submit_input(run["run_id"], "second")

    events_after = api.get_events(run["run_id"])
    assert [event.event_id for event in events_after] == [event.event_id for event in events_before]
    assert [event.event_type for event in events_after] == [event.event_type for event in events_before]
    assert projector.RunProjector().rebuild(run["run_id"], api.event_store).status == "completed"
