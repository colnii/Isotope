from __future__ import annotations

from typing import Any

import pytest

from isotope_kernel import http_api, server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="retry runtime integration")
    return api, run["run_id"]


def _tool_intent(text: str = "replacement output") -> dict[str, Any]:
    return {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": text,
    }


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _submit_failed_action(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)

    def fail_create_artifact(*args: Any, **kwargs: Any):
        raise RuntimeError("deterministic tool failure")

    monkeypatch.setattr(api.artifact_store, "create_artifact", fail_create_artifact)
    result = api.submit_action(run_id, _tool_intent("will fail"))
    assert result["status"] == "failed"
    return api, run_id, result


def _submit_completed_action(tmp_path):
    api, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent("completed output"))
    assert result["status"] == "completed"
    return api, run_id, result


def test_request_retry_helper_exists_on_in_process_server(tmp_path):
    api, _run_id = _new_run(tmp_path)

    assert hasattr(api, "request_retry")


def test_request_retry_failed_action_appends_canonical_request_and_replacement_identity(
    tmp_path,
    monkeypatch,
):
    api, run_id, failed = _submit_failed_action(tmp_path, monkeypatch)
    before_events = list(api.get_events(run_id))

    result = api.request_retry(
        run_id,
        basis_execution_id=failed["execution_id"],
        reason="transient failure",
        requested_by="agent_supervisor",
        replacement_intent=_tool_intent("retry output"),
    )

    after_events = list(api.get_events(run_id))
    event_types = _event_types(api, run_id)
    assert len(after_events) > len(before_events)
    assert "action.retry_requested" in event_types
    assert result["status"] in {"accepted", "created", "completed"}
    assert result["retry_id"].startswith("retry_")
    assert result["basis_execution_id"] == failed["execution_id"]
    assert result["basis_proposal_id"] == failed["proposal_id"]
    assert result["replacement_proposal_id"] != failed["proposal_id"]
    assert result["replacement_execution_id"] != failed["execution_id"]
    assert api.get_run_state(run_id).actions[failed["execution_id"]]["status"] == "failed"


def test_request_retry_completed_action_requires_explicit_rerun_and_preserves_old_state(tmp_path):
    api, run_id, completed = _submit_completed_action(tmp_path)

    result = api.request_retry(
        run_id,
        basis_execution_id=completed["execution_id"],
        reason="explicit rerun requested",
        requested_by="agent_supervisor",
        replacement_intent=_tool_intent("rerun output"),
        explicit_rerun=True,
    )

    assert result["status"] in {"accepted", "created", "completed"}
    assert result["basis_execution_id"] == completed["execution_id"]
    assert result["replacement_execution_id"] != completed["execution_id"]
    assert api.get_run_state(run_id).actions[completed["execution_id"]]["status"] == "completed"


def test_request_retry_rejects_unknown_or_malformed_basis_without_partial_events(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="basis|unknown|execution"):
        api.request_retry(
            run_id,
            basis_execution_id="exec_missing",
            reason="bad basis",
            requested_by="agent_supervisor",
            replacement_intent=_tool_intent("should not run"),
        )

    assert api.get_events(run_id) == before_events
    assert api.get_run_state(run_id).action_retries == {}


def test_retry_runtime_surface_does_not_add_scheduler_backoff_or_product_http_route(tmp_path):
    api, _run_id = _new_run(tmp_path)
    app = http_api.HttpApiApp(tmp_path / "http")
    route_paths = [path for _method, path in app.routes()]

    assert not hasattr(api, "scheduler")
    assert not hasattr(api, "retry_backoff_policy")
    assert not hasattr(api, "timeout_engine")
    assert not hasattr(api, "process_manager")
    assert all("retry" not in path for path in route_paths)
