import pytest

from isotope_kernel import events, projector


ARTIFACT_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
}


def _event(event_id: str, event_type: str, payload: dict):
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-05-02T00:00:{event_id[-2:]}Z",
    )


def _run_created():
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _proposal(event_id="evt_002", proposal_id="prop_001"):
    return _event(
        event_id,
        "action.proposed",
        {
            "proposal_id": proposal_id,
            "agent_id": "agent_supervisor",
            "action_type": "call_tool",
        },
    )


def _decision(event_id="evt_003", proposal_id="prop_001", decision_id="dec_001"):
    return _event(
        event_id,
        "action.decided",
        {
            "decision_id": decision_id,
            "proposal_id": proposal_id,
            "outcome": "approved",
        },
    )


def _started():
    return _event(
        "evt_004",
        "action.started",
        {
            "execution_id": "exec_001",
            "proposal_id": "prop_001",
            "decision_id": "dec_001",
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


def _superseded(**overrides):
    payload = {
        "supersession_id": "supersede_001",
        "old_proposal_id": "prop_001",
        "new_proposal_id": "prop_replacement_001",
        "reason": "replacement action has narrower workspace grants",
        "basis_event_id": "evt_004",
    }
    payload.update(overrides)
    return _event("evt_005", "action.superseded", payload)


def _started_action_events():
    return [_run_created(), _proposal(), _decision(), _started()]


def _without(mapping: dict, key: str) -> dict:
    result = dict(mapping)
    result.pop(key)
    return result


def test_supersede_links_old_and_replacement_proposals():
    state = projector.RunProjector().project(
        [*_started_action_events(), _superseded(), _proposal("evt_006", "prop_replacement_001")]
    )

    assert hasattr(state, "action_supersessions")
    assert state.action_supersessions["supersede_001"] == {
        "supersession_id": "supersede_001",
        "old_proposal_id": "prop_001",
        "new_proposal_id": "prop_replacement_001",
        "status": "created",
        "basis_event_id": "evt_004",
    }
    assert state.actions["exec_001"]["status"] == "superseded"


def test_superseded_action_cannot_complete_after_replacement():
    with pytest.raises(ValueError, match="action.completed after action.superseded"):
        projector.RunProjector().project([*_started_action_events(), _superseded(), _completed()])


def test_replacement_proposal_still_requires_policy_before_execution():
    with pytest.raises(ValueError, match="action.started before approved decision"):
        projector.RunProjector().project(
            [
                *_started_action_events(),
                _superseded(),
                _proposal("evt_006", "prop_replacement_001"),
                _event(
                    "evt_007",
                    "action.started",
                    {
                        "execution_id": "exec_replacement_001",
                        "proposal_id": "prop_replacement_001",
                        "decision_id": "dec_replacement_001",
                    },
                ),
            ]
        )


def test_supersede_checkpoint_state_contains_lineage():
    checkpoint = projector.RunProjector().create_checkpoint(
        "run_001",
        [*_started_action_events(), _superseded(), _proposal("evt_006", "prop_replacement_001")],
    )

    assert "action_supersessions" in checkpoint["state"]
    assert checkpoint["state"]["action_supersessions"]["supersede_001"]["new_proposal_id"] == "prop_replacement_001"


def test_malformed_supersede_event_fails_fast():
    payload = _without(_superseded().payload, "supersession_id")

    with pytest.raises(ValueError, match="action.superseded missing required field: supersession_id"):
        projector.RunProjector().project([*_started_action_events(), _event("evt_005", "action.superseded", payload)])
