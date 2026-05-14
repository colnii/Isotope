from __future__ import annotations

from typing import Any

import pytest

from isotope import http_api, server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="cancel runtime integration")
    return api, run["run_id"]


def _tool_intent(text: str = "cancel target output") -> dict[str, Any]:
    return {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": text,
    }


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _submit_pending_approval_action(tmp_path):
    api, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent(), requires_approval=True)
    assert result["status"] == "pending_user_approval"
    return api, run_id, result


def _submit_completed_action(tmp_path):
    api, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent("completed output"))
    assert result["status"] == "completed"
    return api, run_id, result


def _submit_failed_action(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)

    def fail_create_artifact(*args: Any, **kwargs: Any):
        raise RuntimeError("deterministic tool failure")

    monkeypatch.setattr(api.artifact_store, "create_artifact", fail_create_artifact)
    result = api.submit_action(run_id, _tool_intent("will fail"))
    assert result["status"] == "failed"
    return api, run_id, result


def test_request_cancel_helper_exists_on_in_process_server(tmp_path):
    api, _run_id = _new_run(tmp_path)

    assert hasattr(api, "request_cancel")


def test_request_cancel_pending_approval_appends_logical_cancel_request(tmp_path):
    api, run_id, pending = _submit_pending_approval_action(tmp_path)
    before_events = list(api.get_events(run_id))

    result = api.request_cancel(
        run_id,
        basis_proposal_id=pending["proposal_id"],
        reason="user changed their mind",
        requested_by="agent_supervisor",
    )

    after_events = list(api.get_events(run_id))
    event_types = _event_types(api, run_id)
    assert len(after_events) == len(before_events) + 1
    assert "action.cancel_requested" in event_types
    assert "action.cancelled" not in event_types
    assert result["status"] == "cancel_requested"
    assert result["cancel_id"].startswith("cancel_")
    assert result["basis_proposal_id"] == pending["proposal_id"]
    assert result["logical_only"] is True
    assert result["process_kill"] is False
    assert api.get_run_state(run_id).status == "pending_user_approval"


def test_request_cancel_completed_action_is_rejected_without_removing_history(tmp_path):
    api, run_id, completed = _submit_completed_action(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="completed|terminal|cancel"):
        api.request_cancel(
            run_id,
            basis_execution_id=completed["execution_id"],
            reason="too late",
            requested_by="agent_supervisor",
        )

    assert api.get_events(run_id) == before_events
    assert "artifact.created" in _event_types(api, run_id)
    assert api.get_run_state(run_id).actions[completed["execution_id"]]["status"] == "completed"


def test_request_cancel_failed_action_is_rejected_without_partial_cancellation(tmp_path, monkeypatch):
    api, run_id, failed = _submit_failed_action(tmp_path, monkeypatch)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="failed|terminal|cancel"):
        api.request_cancel(
            run_id,
            basis_execution_id=failed["execution_id"],
            reason="too late",
            requested_by="agent_supervisor",
        )

    assert api.get_events(run_id) == before_events
    assert api.get_run_state(run_id).action_cancellations == {}
    assert api.get_run_state(run_id).actions[failed["execution_id"]]["status"] == "failed"


def test_cancel_runtime_surface_does_not_add_process_kill_timeout_or_product_http_route(tmp_path):
    api, _run_id = _new_run(tmp_path)
    app = http_api.HttpApiApp(tmp_path / "http")
    route_paths = [path for _method, path in app.routes()]

    assert not hasattr(api, "kill_process")
    assert not hasattr(api, "process_manager")
    assert not hasattr(api, "timeout_engine")
    assert not hasattr(api, "tool_cancellation_hooks")
    assert all("cancel" not in path for path in route_paths)
