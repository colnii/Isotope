import pytest

import isotope.platform.registry.actions as action_registry
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
import isotope.memory as memory
import isotope.platform.schemas.models as models
import isotope.workspace as workspace


_NO_MEMORY_SERVICE = object()


class RecordingMemoryService:
    def __init__(self):
        self.calls = []

    def write_record(self, record, execution=None, grants=None):
        self.calls.append(
            {
                "record": record,
                "execution": execution,
                "grants": grants,
            }
        )
        raise PermissionError("memory_write not enabled")


def _memory_registry() -> action_registry.ActionTypeRegistry:
    return action_registry.ActionTypeRegistry(
        entries=[
            {
                "action_type": "write_memory",
                "tool_name": "write_memory",
                "payload_requirements": {
                    "required": ["content", "source_refs", "provenance"],
                },
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


def _memory_proposal() -> models.ActionProposal:
    return models.ActionProposal(
        proposal_id="prop_memory_001",
        run_id="run_001",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="write_memory",
        payload={
            "tool": "write_memory",
            "content": {
                "kind": "fact",
                "text": "Learner prefers worked examples.",
            },
            "summary": "Learner prefers worked examples.",
            "source_refs": [
                {
                    "ref_type": "artifact",
                    "artifact_id": "artifact_001",
                    "uri": "artifact://run_001/artifact_001",
                }
            ],
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


def _decision(
    proposal: models.ActionProposal,
    *,
    granted_tools: list[str] | None = None,
) -> models.PolicyDecision:
    if granted_tools is None:
        granted_tools = ["write_memory"]
    return models.PolicyDecision(
        decision_id="dec_memory_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": granted_tools,
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=[],
    )


def _runner(
    tmp_path,
    *,
    memory_service=_NO_MEMORY_SERVICE,
    registry: action_registry.ActionTypeRegistry | None = None,
) -> executor.Executor:
    kwargs = {}
    if memory_service is not _NO_MEMORY_SERVICE:
        kwargs["memory_service"] = memory_service
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=registry if registry is not None else _memory_registry(),
        **kwargs,
    )


def _event_types(runner: executor.Executor, run_id: str = "run_001") -> list[str]:
    return [event.event_type for event in runner.event_store.list_events(run_id)]


def _single_event_payload(runner: executor.Executor, event_type: str) -> dict:
    matches = [
        event.payload
        for event in runner.event_store.list_events("run_001")
        if event.event_type == event_type
    ]
    assert len(matches) == 1
    return matches[0]


def _record_value(record, key: str):
    if hasattr(record, key):
        return getattr(record, key)
    return record[key]


def test_executor_accepts_explicit_memory_service(tmp_path):
    runner = _runner(
        tmp_path,
        memory_service=memory.NotEnabledMemoryService(),
    )

    assert isinstance(runner, executor.Executor)


def test_authorized_write_memory_enters_not_enabled_memory_handler_boundary(tmp_path):
    proposal = _memory_proposal()
    runner = _runner(
        tmp_path,
        memory_service=memory.NotEnabledMemoryService(),
    )

    with pytest.raises(PermissionError, match="memory_write not enabled"):
        runner.execute(_decision(proposal), proposal)

    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_memory_handler_passes_record_execution_and_grants_to_memory_service(tmp_path):
    proposal = _memory_proposal()
    decision = _decision(proposal)
    memory_service = RecordingMemoryService()
    runner = _runner(tmp_path, memory_service=memory_service)

    with pytest.raises(PermissionError, match="memory_write not enabled"):
        runner.execute(decision, proposal)

    assert len(memory_service.calls) == 1
    call = memory_service.calls[0]
    record = call["record"]
    started_payload = _single_event_payload(runner, "action.started")
    runtime_execution_id = started_payload["execution_id"]

    assert _record_value(record, "content") == proposal.payload["content"]
    assert _record_value(record, "source_refs") == proposal.payload["source_refs"]
    assert _record_value(record, "provenance")["run_id"] == proposal.run_id
    assert _record_value(record, "provenance")["action_type"] == "write_memory"
    assert _record_value(record, "provenance")["execution_id"] == runtime_execution_id
    assert call["execution"] is not None
    assert call["execution"].execution_id == runtime_execution_id
    assert call["grants"] == decision.grants


def test_missing_memory_grant_does_not_call_memory_service(tmp_path):
    proposal = _memory_proposal()
    decision = _decision(proposal, granted_tools=[])
    memory_service = RecordingMemoryService()
    runner = _runner(tmp_path, memory_service=memory_service)

    with pytest.raises(PermissionError, match="not granted"):
        runner.execute(decision, proposal)

    assert memory_service.calls == []
    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_memory_failure_does_not_create_artifact_or_memory_success_event(tmp_path):
    proposal = _memory_proposal()
    runner = _runner(tmp_path, memory_service=RecordingMemoryService())

    with pytest.raises(PermissionError, match="memory_write not enabled"):
        runner.execute(_decision(proposal), proposal)

    event_types = _event_types(runner)
    assert event_types == ["action.started", "action.failed"]
    assert "artifact.created" not in event_types
    assert "action.completed" not in event_types
    assert "memory.record_created" not in event_types
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_current_unsupported_write_memory_path_has_no_artifact_side_effect(tmp_path):
    proposal = _memory_proposal()
    runner = _runner(tmp_path)

    with pytest.raises(PermissionError, match="unsupported handler"):
        runner.execute(_decision(proposal), proposal)

    assert _event_types(runner) == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []
