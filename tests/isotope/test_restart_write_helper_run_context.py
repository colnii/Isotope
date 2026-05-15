from __future__ import annotations

from isotope.platform.state.checkpoint_store import FileCheckpointStore
from isotope.runtime.in_process import InProcessServer


def _new_server_with_run(root, checkpoint_root):
    api = InProcessServer(root, checkpoint_store=FileCheckpointStore(checkpoint_root))
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="restart write helper context")
    source = api.create_source_artifact(
        run["run_id"],
        summary="pre-restart source",
        content="pre-restart content",
    )
    return api, run["run_id"], source["artifact_ref"]


def _restart(root, checkpoint_root):
    return InProcessServer(root, checkpoint_store=FileCheckpointStore(checkpoint_root))


def _worker_handoff_intent() -> dict:
    return {
        "parent_agent_id": "agent_supervisor",
        "requested_worker_role": "worker",
        "requested_capabilities": {
            "tools": ["write_artifact_tool"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        },
    }


def test_source_artifact_helper_can_write_after_server_restart(tmp_path):
    root = tmp_path / "server"
    checkpoint_root = tmp_path / "checkpoints"
    _, run_id, pre_restart_ref = _new_server_with_run(root, checkpoint_root)
    restarted = _restart(root, checkpoint_root)

    assert restarted.get_run_state(run_id).run_id == run_id

    result = restarted.create_source_artifact(
        run_id,
        summary="post-restart source",
        content="post-restart content",
        basis_refs=[pre_restart_ref],
        source_refs=[pre_restart_ref],
    )

    expected_refs = [pre_restart_ref.to_dict()]
    assert result["status"] == "completed"
    assert result["artifact_ref"].run_id == run_id
    assert result["artifact_ref"] != pre_restart_ref
    assert result["artifact_summary"] == "post-restart source"
    assert result["basis_refs"] == expected_refs
    assert result["source_refs"] == expected_refs
    assert restarted.get_artifact_record(result["artifact_ref"])["summary"] == "post-restart source"
    assert restarted.get_artifact_record(result["artifact_ref"])["basis_refs"] == expected_refs


def test_worker_handoff_helper_can_write_after_server_restart(tmp_path):
    root = tmp_path / "server"
    checkpoint_root = tmp_path / "checkpoints"
    _, run_id, artifact_ref = _new_server_with_run(root, checkpoint_root)
    restarted = _restart(root, checkpoint_root)

    assert restarted.get_run_state(run_id).run_id == run_id

    result = restarted.submit_worker_handoff(
        run_id,
        delegation_intent=_worker_handoff_intent(),
        artifact_ref=artifact_ref,
        summary="post-restart worker handoff",
    )

    assert result["status"] == "completed"
    assert result["worker_summary"]["result_refs"] == [artifact_ref.to_dict()]
    assert result["private_append_required"] is False


def test_restart_recovered_write_helper_rejects_terminal_run_without_side_effects(tmp_path):
    root = tmp_path / "server"
    checkpoint_root = tmp_path / "checkpoints"
    api = InProcessServer(root, checkpoint_store=FileCheckpointStore(checkpoint_root))
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="terminal restart guard")
    run_id = run["run_id"]
    api.submit_action(
        run_id,
        {
            "action": "call_tool",
            "tool": "write_artifact_tool",
            "text": "terminal",
        },
    )
    restarted = _restart(root, checkpoint_root)
    before_events = list(restarted.get_events(run_id))

    try:
        restarted.create_source_artifact(
            run_id,
            summary="must not write",
            content="must not append",
        )
    except ValueError as exc:
        assert "terminal" in str(exc) or "completed" in str(exc)
    else:
        raise AssertionError("terminal run accepted post-restart write helper")

    assert restarted.get_events(run_id) == before_events
