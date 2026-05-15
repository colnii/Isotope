import pytest

import isotope.platform.registry.actions as action_registry
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.execution.executor as executor
import isotope.memory as memory
import isotope.platform.schemas.models as models
import isotope.platform.state.projector as projector
import isotope.runtime.in_process as server
import isotope.workspace as workspace


MEMORY_SOURCE_REF = {
    "ref_type": "artifact",
    "scope": "run",
    "run_id": "run_001",
    "artifact_id": "artifact_001",
    "uri": "artifact://run_001/artifact_001",
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


def _action_proposed(action_type: str = "write_memory") -> events.CanonicalEvent:
    return _event(
        "evt_002",
        "action.proposed",
        {
            "proposal_id": "prop_memory_001",
            "agent_id": "agent_supervisor",
            "action_type": action_type,
            "registry_id": "default",
            "registry_version": "v0.2",
            "payload": {"tool": action_type},
        },
    )


def _action_decided(outcome: str = "approved") -> events.CanonicalEvent:
    return _event(
        "evt_003",
        "action.decided",
        {
            "decision_id": "dec_memory_001",
            "proposal_id": "prop_memory_001",
            "outcome": outcome,
            "policy_profile_id": "default",
            "policy_version": "v0.2",
        },
    )


def _action_started() -> events.CanonicalEvent:
    return _event(
        "evt_004",
        "action.started",
        {
            "execution_id": "exec_memory_001",
            "proposal_id": "prop_memory_001",
            "decision_id": "dec_memory_001",
        },
    )


def _action_completed() -> events.CanonicalEvent:
    return _event(
        "evt_005",
        "action.completed",
        {
            "execution_id": "exec_memory_001",
            "status": "completed",
            "artifact_refs": [],
        },
    )


def _action_failed() -> events.CanonicalEvent:
    return _event(
        "evt_005",
        "action.failed",
        {
            "execution_id": "exec_memory_001",
            "proposal_id": "prop_memory_001",
            "decision_id": "dec_memory_001",
            "status": "failed",
            "error": "memory service unavailable",
            "error_reason_code": "tool_execution_failed",
            "structured_error": {
                "reason_code": "tool_execution_failed",
                "message": "memory service unavailable",
            },
        },
    )


def _memory_record_created(**overrides) -> events.CanonicalEvent:
    payload = {
        "record_id": "mem_001",
        "execution_id": "exec_memory_001",
        "summary": "Learner prefers worked examples.",
        "source_refs": [dict(MEMORY_SOURCE_REF)],
        "provenance": {
            "run_id": "run_001",
            "execution_id": "exec_memory_001",
            "action_type": "write_memory",
            "basis_event_id": "evt_005",
        },
        "basis_event_id": "evt_005",
        "quality": "unverified",
    }
    payload.update(overrides)
    return _event("evt_006", "memory.record_created", payload)


def _completed_write_memory_events() -> list[events.CanonicalEvent]:
    return [
        _run_created(),
        _action_proposed("write_memory"),
        _action_decided("approved"),
        _action_started(),
        _action_completed(),
    ]


def _without(mapping: dict, key: str) -> dict:
    result = dict(mapping)
    result.pop(key)
    return result


def test_memory_record_created_projects_only_canonical_summary_ref_and_provenance():
    state = projector.RunProjector().project(
        [*_completed_write_memory_events(), _memory_record_created()]
    )

    assert state.memory_records == [
        {
            "record_id": "mem_001",
            "execution_id": "exec_memory_001",
            "summary": "Learner prefers worked examples.",
            "source_refs": [dict(MEMORY_SOURCE_REF)],
            "provenance": {
                "run_id": "run_001",
                "execution_id": "exec_memory_001",
                "action_type": "write_memory",
                "basis_event_id": "evt_005",
            },
            "basis_event_id": "evt_005",
            "quality": "unverified",
        }
    ]
    projected_record = state.memory_records[0]
    for forbidden_field in ("content", "full_content", "artifact_content", "raw_content"):
        assert forbidden_field not in projected_record


def test_memory_record_created_is_not_projected_from_memory_store_without_canonical_event():
    class ExplodingMemoryStore:
        def list_records(self, *args, **kwargs):
            raise AssertionError("projector must not read memory store")

    memory_store = ExplodingMemoryStore()

    state = projector.RunProjector().project(_completed_write_memory_events())

    assert getattr(state, "memory_records", []) == []
    assert memory_store is not None


@pytest.mark.parametrize(
    "field",
    ["record_id", "execution_id", "summary", "source_refs", "provenance", "basis_event_id"],
)
def test_memory_record_created_requires_payload_fields(field):
    payload = _without(_memory_record_created().payload, field)

    with pytest.raises(ValueError, match=f"memory.record_created missing required field: {field}"):
        projector.RunProjector().project(
            [*_completed_write_memory_events(), _event("evt_006", "memory.record_created", payload)]
        )


@pytest.mark.parametrize("field", ["content", "full_content", "artifact_content", "raw_content"])
def test_memory_record_created_rejects_full_content_fields(field):
    with pytest.raises(ValueError, match=f"memory.record_created cannot contain {field}"):
        projector.RunProjector().project(
            [*_completed_write_memory_events(), _memory_record_created(**{field: "raw artifact text"})]
        )


def test_memory_record_created_requires_completed_write_memory_execution():
    with pytest.raises(ValueError, match="completed write_memory execution"):
        projector.RunProjector().project([_run_created(), _memory_record_created()])


@pytest.mark.parametrize(
    "events_before_record, expected_message",
    [
        (
            [_run_created(), _action_proposed("write_memory"), _action_decided("denied")],
            "denied",
        ),
        (
            [
                _run_created(),
                _action_proposed("write_memory"),
                _action_decided("pending_user_approval"),
            ],
            "pending",
        ),
        (
            [
                _run_created(),
                _action_proposed("write_memory"),
                _action_decided("approved"),
                _action_started(),
                _action_failed(),
            ],
            "failed",
        ),
    ],
)
def test_memory_record_created_rejects_non_completed_execution_states(events_before_record, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        projector.RunProjector().project([*events_before_record, _memory_record_created()])


def test_memory_record_created_rejects_completed_non_memory_execution():
    with pytest.raises(ValueError, match="write_memory"):
        projector.RunProjector().project(
            [
                _run_created(),
                _action_proposed("call_tool"),
                _action_decided("approved"),
                _action_started(),
                _action_completed(),
                _memory_record_created(),
            ]
        )


def test_executor_not_enabled_memory_service_still_cannot_create_memory_record_event(tmp_path):
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
    proposal = models.ActionProposal(
        proposal_id="prop_memory_001",
        run_id="run_001",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="write_memory",
        payload={
            "tool": "write_memory",
            "content": {"kind": "fact", "text": "Learner prefers worked examples."},
            "summary": "Learner prefers worked examples.",
            "source_refs": [dict(MEMORY_SOURCE_REF)],
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
    decision = models.PolicyDecision(
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
    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=registry,
        memory_service=memory.NotEnabledMemoryService(),
    )

    with pytest.raises(PermissionError, match="memory_write not enabled"):
        runner.execute(decision, proposal)

    event_types = [event.event_type for event in runner.event_store.list_events("run_001")]
    assert event_types == ["action.started", "action.failed"]
    assert "memory.record_created" not in event_types
    assert "action.completed" not in event_types
    assert runner.artifact_store.list_artifacts("run_001") == []


def test_server_still_has_no_public_direct_memory_write_api(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "write_memory")
    assert not hasattr(api, "create_memory_record")
