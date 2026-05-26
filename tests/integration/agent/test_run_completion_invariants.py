import pytest

import isotope.platform.events.events as events
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server


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


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _proposed(event_id="evt_002", proposal_id="prop_001"):
    return _event(
        event_id,
        "action.proposed",
        {
            "proposal_id": proposal_id,
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
            "registry_id": "default",
            "registry_version": "v0.2",
        },
    )


def _decided(event_id="evt_003", proposal_id="prop_001", decision_id="dec_001", outcome="approved"):
    return _event(
        event_id,
        "action.decided",
        {
            "decision_id": decision_id,
            "proposal_id": proposal_id,
            "outcome": outcome,
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _started(event_id="evt_004", proposal_id="prop_001", decision_id="dec_001", execution_id="exec_001"):
    return _event(
        event_id,
        "action.started",
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
        },
    )


def _artifact_created(
    event_id="evt_005",
    execution_id="exec_001",
    artifact_id="artifact_001",
    proposal_id="prop_001",
    decision_id="dec_001",
):
    return _event(
        event_id,
        "artifact.created",
        {
            "artifact": {
                "ref": {
                    **ARTIFACT_REF,
                    "artifact_id": artifact_id,
                },
                "artifact_type": "text",
                "summary": "hello artifact",
                "provenance": {
                    "execution_id": execution_id,
                    "proposal_id": proposal_id,
                    "decision_id": decision_id,
                },
            }
        },
    )


def _completed(event_id="evt_006", execution_id="exec_001"):
    return _event(
        event_id,
        "action.completed",
        {
            "execution_id": execution_id,
            "status": "completed",
            "artifact_refs": [ARTIFACT_REF],
        },
    )


def _failed(event_id="evt_007", proposal_id="prop_001", decision_id="dec_001", execution_id="exec_001"):
    return _event(
        event_id,
        "action.failed",
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "status": "failed",
            "error": "tool failed",
            "error_reason_code": "tool_execution_failed",
            "structured_error": {
                "reason_code": "tool_execution_failed",
                "message": "tool failed",
            },
        },
    )


def _approval_requested(event_id="evt_008", proposal_id="prop_001", decision_id="dec_001"):
    return _event(
        event_id,
        "approval.requested",
        {
            "approval_id": "approval_001",
            "run_id": "run_001",
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "action_type": "call_tool",
        },
    )


def _run_completed(event_id="evt_009"):
    return _event(event_id, "run.completed", {"status": "completed"})


def _happy_path_events():
    return [
        _run_created(),
        _proposed(),
        _decided(),
        _started(),
        _artifact_created(),
        _completed(),
        _run_completed(),
    ]


def test_run_completed_rejects_run_without_completed_execution():
    with pytest.raises(ValueError, match="run.completed requires a completed execution"):
        projector.RunProjector().project([_run_created(), _run_completed()])


def test_run_completed_rejects_running_action():
    with pytest.raises(ValueError, match="run.completed while executions are still running"):
        projector.RunProjector().project([_run_created(), _proposed(), _decided(), _started(), _run_completed()])


def test_run_completed_rejects_failed_action():
    with pytest.raises(ValueError, match="run.completed after failed execution"):
        projector.RunProjector().project(
            [_run_created(), _proposed(), _decided(), _started(), _failed(), _run_completed()]
        )


def test_run_completed_rejects_pending_approval():
    with pytest.raises(ValueError, match="run.completed while approval is pending"):
        projector.RunProjector().project(
            [
                _run_created(),
                _proposed(),
                _decided(outcome="pending_user_approval"),
                _approval_requested(),
                _run_completed(),
            ]
        )


@pytest.mark.parametrize(
    "events_after_run_completed",
    [
        [_decided("evt_010", proposal_id="prop_002", decision_id="dec_002")],
        [
            _proposed("evt_008", proposal_id="prop_002"),
            _decided("evt_009", proposal_id="prop_002", decision_id="dec_002"),
            _run_completed("evt_010"),
            _started("evt_011", proposal_id="prop_002", decision_id="dec_002", execution_id="exec_002"),
        ],
        [_failed("evt_010", proposal_id="prop_002", decision_id="dec_002", execution_id="exec_002")],
        [_completed("evt_010", execution_id="exec_001")],
        [_artifact_created("evt_010", execution_id="exec_002", artifact_id="artifact_002")],
    ],
)
def test_run_completed_rejects_later_action_or_artifact_events(events_after_run_completed):
    base_events = _happy_path_events()
    if len(events_after_run_completed) > 1:
        base_events = _happy_path_events()[:-1]
    with pytest.raises(ValueError, match="event after run.completed"):
        projector.RunProjector().project([*base_events, *events_after_run_completed])


def test_happy_path_run_completion_still_projects_completed():
    state = projector.RunProjector().project(_happy_path_events())

    assert state.status == "completed"
    assert state.actions["exec_001"]["status"] == "completed"
    assert state.artifacts[0]["summary"] == "hello artifact"


def test_server_happy_path_still_projects_completed(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "produce artifact")

    result = api.submit_input(run["run_id"], "hello")

    assert result["status"] == "completed"
    assert result["run_state"].status == "completed"
    assert [event.event_type for event in api.get_events(run["run_id"])] == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
