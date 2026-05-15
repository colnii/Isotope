import isotope.runtime.action_compiler as action_compiler
import isotope.platform.state.event_store as event_store
import isotope.platform.events.events as events
import isotope.execution.executor as executor
import isotope.policy as policy


def test_compact_intent_must_compile_to_action_proposal_before_policy():
    assert hasattr(action_compiler, "ActionCompiler")
    assert hasattr(policy, "PolicyEngine")

    compiler = action_compiler.ActionCompiler()
    proposal = compiler.compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "hello",
            "requested_tools": ["write_artifact_tool", "extra_tool"],
        },
        {
            "run_id": "run_001",
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )

    assert proposal.action_type == "call_tool"
    assert proposal.proposal_id
    assert proposal.run_id == "run_001"


def test_proposal_and_decision_are_written_before_execution_started(tmp_path):
    assert hasattr(events, "CanonicalEvent")
    assert hasattr(event_store, "FileEventStore")
    assert hasattr(executor, "Executor")

    store = event_store.FileEventStore(tmp_path)
    store.append(
        events.CanonicalEvent(
            event_id="evt_001",
            run_id="run_001",
            event_type="action.proposed",
            payload={"proposal_id": "prop_001"},
            created_at="2026-04-27T00:00:00Z",
        )
    )
    store.append(
        events.CanonicalEvent(
            event_id="evt_002",
            run_id="run_001",
            event_type="action.decided",
            payload={"decision_id": "dec_001", "proposal_id": "prop_001"},
            created_at="2026-04-27T00:00:01Z",
        )
    )
    store.append(
        events.CanonicalEvent(
            event_id="evt_003",
            run_id="run_001",
            event_type="action.started",
            payload={"execution_id": "exec_001", "decision_id": "dec_001"},
            created_at="2026-04-27T00:00:02Z",
        )
    )

    event_types = [event.event_type for event in store.list_events("run_001")]
    assert event_types.index("action.proposed") < event_types.index("action.decided")
    assert event_types.index("action.decided") < event_types.index("action.started")
