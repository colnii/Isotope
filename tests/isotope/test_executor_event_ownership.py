import isotope.runtime.action_compiler as action_compiler
import isotope.workspace.artifacts as artifact_store
import isotope.platform.state.event_store as event_store
import isotope.execution.executor as executor
import isotope.platform.schemas.models as models
import isotope.runtime.in_process as server
import isotope.workspace as workspace
from isotope.platform.events.events import CanonicalEvent


def _proposal(text="hello"):
    return action_compiler.ActionCompiler().compile(
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": text,
            "requested_tools": ["write_artifact_tool"],
            "workspace_mode": "shared_ro",
            "budget": {"seconds": 30},
        },
        {
            "run_id": "run_001",
            "agent_id": "agent_supervisor",
            "thread_id": "thread_main",
        },
    )


def _decision(proposal):
    return models.PolicyDecision(
        decision_id="dec_001",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
        reason_codes=[],
    )


def _runner(tmp_path):
    return executor.Executor(
        event_store=event_store.FileEventStore(tmp_path),
        artifact_store=artifact_store.ArtifactStore(tmp_path),
        workspace_manager=workspace.WorkspaceManager(),
    )


def _event_types(store, run_id="run_001"):
    return [event.event_type for event in store.list_events(run_id)]


def test_executor_execute_appends_action_started(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)

    result = runner.execute(decision, proposal)

    events = runner.event_store.list_events(proposal.run_id)
    started = [event for event in events if event.event_type == "action.started"]
    assert len(started) == 1
    assert started[0].payload["execution_id"] == result.execution_id
    assert started[0].payload["proposal_id"] == proposal.proposal_id
    assert started[0].payload["decision_id"] == decision.decision_id


def test_executor_appends_started_before_artifact_side_effect(tmp_path, monkeypatch):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)
    original_create = runner.artifact_store.create_artifact

    def assert_started_before_create(*args, **kwargs):
        events = runner.event_store.list_events(proposal.run_id)
        assert any(
            event.event_type == "action.started"
            and event.payload["proposal_id"] == proposal.proposal_id
            and event.payload["decision_id"] == decision.decision_id
            for event in events
        )
        return original_create(*args, **kwargs)

    monkeypatch.setattr(runner.artifact_store, "create_artifact", assert_started_before_create)

    runner.execute(decision, proposal)


def test_executor_success_appends_artifact_created_and_action_completed(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)

    runner.execute(decision, proposal)

    assert "artifact.created" in _event_types(runner.event_store)
    assert "action.completed" in _event_types(runner.event_store)


def test_executor_success_event_order_is_started_artifact_created_completed(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)

    runner.execute(decision, proposal)

    owned_events = [
        event.event_type
        for event in runner.event_store.list_events(proposal.run_id)
        if event.event_type in {"action.started", "artifact.created", "action.completed"}
    ]
    assert owned_events == ["action.started", "artifact.created", "action.completed"]


def test_executor_artifact_created_payload_has_ref_summary_type_and_execution_provenance(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)

    result = runner.execute(decision, proposal)

    artifact_events = [
        event for event in runner.event_store.list_events(proposal.run_id)
        if event.event_type == "artifact.created"
    ]
    assert len(artifact_events) == 1
    artifact = artifact_events[0].payload["artifact"]
    assert artifact["ref"]["ref_type"] == "artifact"
    assert artifact["ref"]["scope"] == "run"
    assert artifact["ref"]["run_id"] == proposal.run_id
    assert artifact["ref"]["artifact_id"]
    assert artifact["summary"] == "hello artifact"
    assert artifact["artifact_type"] == "text"
    assert artifact["provenance"]["execution_id"] == result.execution_id


def test_executor_action_completed_payload_has_execution_status_and_artifact_refs(tmp_path):
    proposal = _proposal()
    decision = _decision(proposal)
    runner = _runner(tmp_path)

    result = runner.execute(decision, proposal)

    completed_events = [
        event for event in runner.event_store.list_events(proposal.run_id)
        if event.event_type == "action.completed"
    ]
    assert len(completed_events) == 1
    payload = completed_events[0].payload
    assert payload["execution_id"] == result.execution_id
    assert payload["status"] == "completed"
    assert payload["artifact_refs"][0]["ref_type"] == "artifact"


def test_server_happy_path_does_not_duplicate_executor_owned_success_events(tmp_path, monkeypatch):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], "test run")

    def executor_owned_success(decision, proposal):
        execution = models.ActionExecution(
            execution_id="exec_owned",
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            action_type=proposal.action_type,
            status="completed",
            effective_grants_snapshot=decision.grants,
        )
        api.event_store.append(
            CanonicalEvent(
                event_id="evt_owned_started",
                run_id=proposal.run_id,
                event_type="action.started",
                payload={
                    "execution_id": execution.execution_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                },
                created_at="2026-04-27T00:00:00Z",
            )
        )
        artifact = api.artifact_store.create_artifact(
            run_id=proposal.run_id,
            execution_id=execution.execution_id,
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            artifact_type="text",
            summary="hello artifact",
            content=str(proposal.payload.get("text", "")),
        )
        api.event_store.append(
            CanonicalEvent(
                event_id="evt_owned_artifact",
                run_id=proposal.run_id,
                event_type="artifact.created",
                payload={
                    "artifact": {
                        "ref": artifact.ref.to_dict(),
                        "artifact_type": artifact.artifact_type,
                        "summary": artifact.summary,
                        "provenance": dict(artifact.provenance),
                    }
                },
                created_at="2026-04-27T00:00:01Z",
            )
        )
        api.event_store.append(
            CanonicalEvent(
                event_id="evt_owned_completed",
                run_id=proposal.run_id,
                event_type="action.completed",
                payload={
                    "execution_id": execution.execution_id,
                    "status": execution.status,
                    "artifact_refs": [artifact.ref.to_dict()],
                },
                created_at="2026-04-27T00:00:02Z",
            )
        )
        return execution

    monkeypatch.setattr(api.executor, "execute", executor_owned_success)

    api.submit_input(run["run_id"], "hello")

    event_types = _event_types(api.event_store, run["run_id"])
    assert event_types.count("action.started") == 1
    assert event_types.count("artifact.created") == 1
    assert event_types.count("action.completed") == 1
    assert event_types.count("run.completed") == 1
