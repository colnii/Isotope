import pytest

import isotope.platform.registry.actions as action_registry
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.execution.executor as executor
import isotope.memory as memory
from isotope.platform.schemas.actions import ActionProposal, PolicyDecision
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server
import isotope.workspace as workspace


OLD_SOURCE_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_old",
    "uri": "artifact://run_001/artifact_old",
}

NEW_SOURCE_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_new",
    "uri": "artifact://run_001/artifact_new",
}


def _event(event_id: str, event_type: str, payload: dict) -> events.CanonicalEvent:
    return events.CanonicalEvent(
        event_id=event_id,
        run_id="run_001",
        event_type=event_type,
        payload=payload,
        created_at=f"2026-04-30T00:00:{event_id[-2:]}Z",
    )


def _run_created() -> events.CanonicalEvent:
    return _event("evt_001", "run.created", {"run_id": "run_001"})


def _action_proposed(event_id: str, proposal_id: str, action_type: str = "write_memory") -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.proposed",
        {
            "proposal_id": proposal_id,
            "agent_id": "agent_supervisor",
            "action_type": action_type,
            "registry_id": "default",
            "registry_version": "v0.2",
            "payload": {"tool": action_type},
        },
    )


def _action_decided(
    event_id: str,
    proposal_id: str,
    decision_id: str,
    outcome: str = "approved",
) -> events.CanonicalEvent:
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


def _action_started(
    event_id: str,
    execution_id: str,
    proposal_id: str,
    decision_id: str,
) -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.started",
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
        },
    )


def _action_completed(event_id: str, execution_id: str) -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.completed",
        {
            "execution_id": execution_id,
            "status": "completed",
            "artifact_refs": [],
        },
    )


def _action_failed(
    event_id: str,
    execution_id: str,
    proposal_id: str,
    decision_id: str,
) -> events.CanonicalEvent:
    return _event(
        event_id,
        "action.failed",
        {
            "execution_id": execution_id,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "status": "failed",
            "error": "memory service unavailable",
            "error_reason_code": "tool_execution_failed",
            "structured_error": {
                "reason_code": "tool_execution_failed",
                "message": "memory service unavailable",
            },
        },
    )


def _completed_execution_events(
    *,
    proposal_id: str,
    decision_id: str,
    execution_id: str,
    start_event_number: int,
    action_type: str = "write_memory",
) -> list[events.CanonicalEvent]:
    return [
        _action_proposed(f"evt_{start_event_number:03d}", proposal_id, action_type),
        _action_decided(f"evt_{start_event_number + 1:03d}", proposal_id, decision_id),
        _action_started(f"evt_{start_event_number + 2:03d}", execution_id, proposal_id, decision_id),
        _action_completed(f"evt_{start_event_number + 3:03d}", execution_id),
    ]


def _memory_record_created(
    event_id: str,
    *,
    record_id: str,
    execution_id: str,
    summary: str,
    source_ref: dict,
    basis_event_id: str,
) -> events.CanonicalEvent:
    return _event(
        event_id,
        "memory.record_created",
        {
            "record_id": record_id,
            "execution_id": execution_id,
            "summary": summary,
            "source_refs": [dict(source_ref)],
            "provenance": {
                "run_id": "run_001",
                "execution_id": execution_id,
                "action_type": "write_memory",
                "basis_event_id": basis_event_id,
            },
            "basis_event_id": basis_event_id,
            "quality": "unverified",
        },
    )


def _created_memory_records_events() -> list[events.CanonicalEvent]:
    return [
        _run_created(),
        *_completed_execution_events(
            proposal_id="prop_memory_old",
            decision_id="dec_memory_old",
            execution_id="exec_memory_old",
            start_event_number=2,
        ),
        _memory_record_created(
            "evt_006",
            record_id="mem_old",
            execution_id="exec_memory_old",
            summary="Original learner preference summary.",
            source_ref=OLD_SOURCE_REF,
            basis_event_id="evt_005",
        ),
        *_completed_execution_events(
            proposal_id="prop_memory_new",
            decision_id="dec_memory_new",
            execution_id="exec_memory_new",
            start_event_number=7,
        ),
        _memory_record_created(
            "evt_011",
            record_id="mem_new",
            execution_id="exec_memory_new",
            summary="Updated learner preference summary.",
            source_ref=NEW_SOURCE_REF,
            basis_event_id="evt_010",
        ),
    ]


def _memory_record_superseded(event_id: str = "evt_012", **overrides) -> events.CanonicalEvent:
    payload = {
        "old_record_id": "mem_old",
        "new_record_id": "mem_new",
        "execution_id": "exec_memory_new",
        "reason": "newer evidence supersedes the prior memory summary",
        "provenance": {
            "run_id": "run_001",
            "execution_id": "exec_memory_new",
            "action_type": "write_memory",
            "basis_event_id": "evt_011",
        },
        "basis_event_id": "evt_011",
    }
    payload.update(overrides)
    return _event(event_id, "memory.record_superseded", payload)


def _without(mapping: dict, key: str) -> dict:
    result = dict(mapping)
    result.pop(key)
    return result


def test_memory_record_superseded_marks_old_record_without_overwriting_original():
    state = projector.RunProjector().project(
        [*_created_memory_records_events(), _memory_record_superseded()]
    )

    old_record = state.memory_records[0]
    new_record = state.memory_records[1]

    assert old_record["record_id"] == "mem_old"
    assert old_record["summary"] == "Original learner preference summary."
    assert old_record["source_refs"] == [dict(OLD_SOURCE_REF)]
    assert old_record["provenance"] == {
        "run_id": "run_001",
        "execution_id": "exec_memory_old",
        "action_type": "write_memory",
        "basis_event_id": "evt_005",
    }
    assert old_record["status"] == "superseded"
    assert old_record["superseded_by"] == "mem_new"
    assert old_record["superseded_event_id"] == "evt_012"
    assert old_record["superseded_reason"] == "newer evidence supersedes the prior memory summary"

    assert new_record["record_id"] == "mem_new"
    assert new_record["summary"] == "Updated learner preference summary."


@pytest.mark.parametrize(
    "field",
    ["old_record_id", "new_record_id", "execution_id", "reason", "provenance", "basis_event_id"],
)
def test_memory_record_superseded_requires_payload_fields(field):
    payload = _without(_memory_record_superseded().payload, field)

    with pytest.raises(ValueError, match=f"memory.record_superseded missing required field: {field}"):
        projector.RunProjector().project(
            [*_created_memory_records_events(), _event("evt_012", "memory.record_superseded", payload)]
        )


@pytest.mark.parametrize("field", ["content", "full_content", "artifact_content", "raw_content"])
def test_memory_record_superseded_rejects_full_content_fields(field):
    with pytest.raises(ValueError, match=f"memory.record_superseded cannot contain {field}"):
        projector.RunProjector().project(
            [*_created_memory_records_events(), _memory_record_superseded(**{field: "raw artifact text"})]
        )


def test_memory_record_superseded_rejects_missing_old_record():
    events_before_supersession = [
        event
        for event in _created_memory_records_events()
        if not (event.event_type == "memory.record_created" and event.payload["record_id"] == "mem_old")
    ]

    with pytest.raises(ValueError, match="old_record_id"):
        projector.RunProjector().project([*events_before_supersession, _memory_record_superseded()])


def test_memory_record_superseded_rejects_missing_new_record():
    events_before_supersession = [
        event
        for event in _created_memory_records_events()
        if not (event.event_type == "memory.record_created" and event.payload["record_id"] == "mem_new")
    ]

    with pytest.raises(ValueError, match="new_record_id"):
        projector.RunProjector().project([*events_before_supersession, _memory_record_superseded()])


def test_memory_record_superseded_rejects_self_supersession():
    with pytest.raises(ValueError, match="old_record_id|new_record_id|same"):
        projector.RunProjector().project(
            [*_created_memory_records_events(), _memory_record_superseded(new_record_id="mem_old")]
        )


def test_memory_record_superseded_requires_completed_write_memory_execution():
    with pytest.raises(ValueError, match="completed write_memory execution"):
        projector.RunProjector().project(
            [
                *_created_memory_records_events(),
                _memory_record_superseded(execution_id="exec_memory_missing"),
            ]
        )


@pytest.mark.parametrize(
    "execution_events, expected_message",
    [
        (
            [
                _action_proposed("evt_012", "prop_memory_supersede", "write_memory"),
                _action_decided("evt_013", "prop_memory_supersede", "dec_memory_supersede", "denied"),
            ],
            "denied|completed write_memory execution",
        ),
        (
            [
                _action_proposed("evt_012", "prop_memory_supersede", "write_memory"),
                _action_decided(
                    "evt_013",
                    "prop_memory_supersede",
                    "dec_memory_supersede",
                    "pending_user_approval",
                ),
            ],
            "pending|completed write_memory execution",
        ),
        (
            [
                _action_proposed("evt_012", "prop_memory_supersede", "write_memory"),
                _action_decided("evt_013", "prop_memory_supersede", "dec_memory_supersede"),
                _action_started(
                    "evt_014",
                    "exec_memory_supersede",
                    "prop_memory_supersede",
                    "dec_memory_supersede",
                ),
                _action_failed(
                    "evt_015",
                    "exec_memory_supersede",
                    "prop_memory_supersede",
                    "dec_memory_supersede",
                ),
            ],
            "failed|completed write_memory execution",
        ),
    ],
)
def test_memory_record_superseded_rejects_non_completed_execution_states(
    execution_events,
    expected_message,
):
    with pytest.raises(ValueError, match=expected_message):
        projector.RunProjector().project(
            [
                *_created_memory_records_events(),
                *execution_events,
                _memory_record_superseded(
                    event_id="evt_016",
                    execution_id="exec_memory_supersede",
                ),
            ]
        )


def test_memory_record_superseded_rejects_completed_non_memory_execution():
    with pytest.raises(ValueError, match="write_memory"):
        projector.RunProjector().project(
            [
                *_created_memory_records_events(),
                *_completed_execution_events(
                    proposal_id="prop_tool_supersede",
                    decision_id="dec_tool_supersede",
                    execution_id="exec_tool_supersede",
                    start_event_number=12,
                    action_type="call_tool",
                ),
                _memory_record_superseded(
                    event_id="evt_016",
                    execution_id="exec_tool_supersede",
                    basis_event_id="evt_015",
                ),
            ]
        )


def test_executor_local_memory_service_creates_record_without_supersession_event(tmp_path):
    registry = action_registry.ActionTypeRegistry(
        entries=[
            {
                "action_type": "write_memory",
                "tool_name": "write_memory",
                "payload_requirements": {"required": ["content", "source_refs", "provenance"]},
                "required_capabilities": {
                    "tools": ["write_memory"],
                    "workspace": {"mode": "shared_ro"},
                    "budget": {"seconds": 30},
                },
                "default_workspace_mode": "shared_ro",
                "result_kind": "memory_record",
                "enabled": True,
            }
        ]
    )
    proposal = ActionProposal(
        proposal_id="prop_memory_001",
        run_id="run_001",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="write_memory",
        payload={
            "tool": "write_memory",
            "content": {"kind": "fact", "text": "Learner prefers worked examples."},
            "summary": "Learner prefers worked examples.",
            "source_refs": [dict(OLD_SOURCE_REF)],
            "provenance": {
                "run_id": "run_001",
                "execution_id": "source_exec_001",
                "action_type": "write_memory",
            },
        },
        requested_capabilities={
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    )
    decision = PolicyDecision(
        decision_id="dec_memory_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=[],
    )
    memory_store = memory.FileMemoryStore(tmp_path)
    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=registry,
        memory_service=memory.LocalMemoryWriteService(memory_store),
    )

    runner.execute(decision, proposal)

    event_types = [event.event_type for event in runner.event_store.list_events("run_001")]
    assert event_types == ["action.started", "action.completed", "memory.record_created"]
    assert len(memory_store.list_records()) == 1
    assert "memory.record_superseded" not in event_types


def test_server_still_has_no_public_direct_memory_update_or_supersede_api(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "update_memory")
    assert not hasattr(api, "supersede_memory")
    assert not hasattr(api, "supersede_memory_record")
