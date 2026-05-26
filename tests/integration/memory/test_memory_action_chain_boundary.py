import pytest

import isotope.runtime.in_process.action_compiler as action_compiler
import isotope.platform.registry.actions as action_registry
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
from isotope.platform.schemas.actions import ActionProposal, PolicyDecision
import isotope.policy as policy
import isotope.runtime.in_process as server
import isotope.workspace as workspace


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


def _runtime_context() -> dict[str, str]:
    return {
        "run_id": "run_001",
        "agent_id": "agent_supervisor",
        "thread_id": "thread_main",
    }


def _memory_intent(**overrides) -> dict:
    intent = {
        "action": "write_memory",
        "tool": "write_memory",
        "content": {"kind": "fact", "text": "Learner prefers worked examples."},
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
            "execution_id": "exec_001",
        },
        "requested_tools": ["write_memory"],
    }
    intent.update(overrides)
    return intent


def _memory_proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_memory_001",
        run_id="run_001",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="write_memory",
        payload={
            "tool": "write_memory",
            "approval_requested": True,
            "content": {"kind": "fact", "text": "Learner prefers worked examples."},
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
                "execution_id": "exec_001",
            },
        },
        requested_capabilities={
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    )


def _approved_memory_decision(proposal: ActionProposal) -> PolicyDecision:
    return PolicyDecision(
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


def test_write_memory_intent_requires_structured_payload():
    compiler = action_compiler.ActionCompiler(registry=_memory_registry())

    with pytest.raises(ValueError, match="content|source_refs|provenance|payload"):
        compiler.compile(
            {
                "action": "write_memory",
                "tool": "write_memory",
                "text": "raw transcript text is not a memory record",
                "requested_tools": ["write_memory"],
            },
            _runtime_context(),
        )


def test_valid_memory_intent_preserves_structured_payload():
    compiler = action_compiler.ActionCompiler(registry=_memory_registry())

    proposal = compiler.compile(_memory_intent(), _runtime_context())

    assert proposal.action_type == "write_memory"
    assert proposal.payload["tool"] == "write_memory"
    assert proposal.payload["content"] == {
        "kind": "fact",
        "text": "Learner prefers worked examples.",
    }
    assert proposal.payload["summary"] == "Learner prefers worked examples."
    assert proposal.payload["source_refs"] == [
        {
            "ref_type": "artifact",
            "artifact_id": "artifact_001",
            "uri": "artifact://run_001/artifact_001",
        }
    ]
    assert proposal.payload["provenance"] == {
        "run_id": "run_001",
        "execution_id": "exec_001",
    }


def test_policy_accepts_registry_backed_write_memory_action_type():
    decision = policy.PolicyEngine(registry=_memory_registry()).decide(_memory_proposal())

    assert decision.outcome in {"approved", "modified"}
    assert "unsupported_action" not in decision.reason_codes
    assert "memory_approval_required" not in decision.reason_codes
    assert decision.grants["tools"] == ["write_memory"]


def test_executor_without_memory_handler_fails_after_action_started(tmp_path):
    proposal = _memory_proposal()
    runner = executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
        registry=_memory_registry(),
    )

    with pytest.raises(PermissionError, match="unsupported handler|no handler"):
        runner.execute(_approved_memory_decision(proposal), proposal)

    event_types = [
        event.event_type for event in runner.event_store.list_events(proposal.run_id)
    ]
    assert event_types == ["action.started", "action.failed"]
    assert runner.artifact_store.list_artifacts(proposal.run_id) == []


def test_server_does_not_expose_direct_memory_write_api(tmp_path):
    api = server.InProcessServer(tmp_path)

    assert not hasattr(api, "write_memory")


def test_server_approved_write_memory_action_persists_record_and_low_sensitive_event(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="promote structured memory")
    run_id = run["run_id"]

    result = api.submit_action(
        run_id,
        _memory_intent(
            provenance={
                "run_id": run_id,
                "execution_id": "source_exec_001",
                "action_type": "write_memory",
            }
        ),
        requires_approval=True,
        complete_run=False,
    )

    assert result["status"] == "pending_user_approval"
    assert "action.started" not in [
        event.event_type for event in api.get_events(run_id)
    ]

    resolved = api.resolve_approval(
        result["approval_id"],
        {
            "resolution": "approved",
            "reason": "structured source-backed memory promotion approved",
            "resolver": "tester",
        },
    )

    assert resolved["tool_execution_status"] == "completed"
    records = api.memory_store.list_records(scope="run")
    assert len(records) == 1
    record = records[0]
    assert record.content == {
        "kind": "fact",
        "text": "Learner prefers worked examples.",
    }
    assert record.summary == "Learner prefers worked examples."
    assert record.provenance["run_id"] == run_id
    assert record.provenance["action_type"] == "write_memory"
    assert record.provenance["execution_id"].startswith("exec_")

    events = api.get_events(run_id)
    event_types = [event.event_type for event in events]
    assert event_types.index("approval.resolved") < event_types.index("action.started")
    assert event_types.index("action.started") < event_types.index("action.completed")
    assert event_types.index("action.completed") < event_types.index("memory.record_created")
    memory_payload = [
        event.payload for event in events if event.event_type == "memory.record_created"
    ][0]
    assert memory_payload["record_id"] == record.memory_id
    assert memory_payload["execution_id"] == record.provenance["execution_id"]
    assert memory_payload["summary"] == record.summary
    assert memory_payload["source_refs"] == record.source_refs
    assert memory_payload["quality"] == record.quality
    assert "content" not in memory_payload
    assert "raw_content" not in memory_payload

    state = api.get_run_state(run_id)
    assert state.memory_records == [
        {
            "record_id": record.memory_id,
            "execution_id": record.provenance["execution_id"],
            "summary": record.summary,
            "source_refs": record.source_refs,
            "provenance": memory_payload["provenance"],
            "basis_event_id": memory_payload["basis_event_id"],
            "quality": record.quality,
        }
    ]


def test_server_write_memory_action_requires_explicit_approval(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="promote structured memory")
    run_id = run["run_id"]

    result = api.submit_action(
        run_id,
        _memory_intent(
            provenance={
                "run_id": run_id,
                "execution_id": "source_exec_001",
                "action_type": "write_memory",
            }
        ),
        requires_approval=False,
        complete_run=False,
    )

    assert result["status"] == "denied"
    assert "memory_approval_required" in result["decision"].reason_codes
    event_types = [event.event_type for event in api.get_events(run_id)]
    assert "approval.requested" not in event_types
    assert "action.started" not in event_types
    assert api.memory_store.list_records(scope="run") == []
