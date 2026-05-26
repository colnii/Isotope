from __future__ import annotations

from typing import Any

import pytest

import isotope.interfaces.http as http_api
import isotope.runtime.in_process as server


def _new_run(tmp_path):
    api = server.InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="supersede runtime integration")
    return api, run["run_id"]


def _tool_intent(text: str = "supersede target output") -> dict[str, Any]:
    return {
        "action": "call_tool",
        "tool": "write_artifact_tool",
        "text": text,
    }


def _event_types(api: server.InProcessServer, run_id: str) -> list[str]:
    return [event.event_type for event in api.get_events(run_id)]


def _submit_completed_action(tmp_path):
    api, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent("old completed output"))
    assert result["status"] == "completed"
    return api, run_id, result


def _submit_pending_approval_action(tmp_path):
    api, run_id = _new_run(tmp_path)
    result = api.submit_action(run_id, _tool_intent("old pending output"), requires_approval=True)
    assert result["status"] == "pending_user_approval"
    return api, run_id, result


def test_request_supersede_helper_exists_on_in_process_server(tmp_path):
    api, _run_id = _new_run(tmp_path)

    assert hasattr(api, "request_supersede")


def test_request_supersede_requires_replacement_intent_or_proposal_identity(tmp_path):
    api, run_id, pending = _submit_pending_approval_action(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="replacement"):
        api.request_supersede(
            run_id,
            old_proposal_id=pending["proposal_id"],
            reason="replacement is required",
            requested_by="agent_supervisor",
        )

    assert api.get_events(run_id) == before_events
    assert api.get_run_state(run_id).action_supersessions == {}


def test_request_supersede_links_old_action_to_replacement_without_mutating_old_state(tmp_path):
    api, run_id, completed = _submit_completed_action(tmp_path)
    before_events = list(api.get_events(run_id))

    result = api.request_supersede(
        run_id,
        old_proposal_id=completed["proposal_id"],
        old_execution_id=completed["execution_id"],
        replacement_intent=_tool_intent("replacement output"),
        reason="review requested a replacement",
        requested_by="agent_supervisor",
    )

    after_events = list(api.get_events(run_id))
    event_types = _event_types(api, run_id)
    assert len(after_events) > len(before_events)
    assert "action.superseded" in event_types
    assert result["status"] in {"accepted", "created", "completed"}
    assert result["supersession_id"].startswith("supersede_")
    assert result["old_proposal_id"] == completed["proposal_id"]
    assert result["old_execution_id"] == completed["execution_id"]
    assert result["replacement_proposal_id"] != completed["proposal_id"]
    assert result["replacement_execution_id"] != completed["execution_id"]
    assert result["reason_code"] == "superseded_by_replacement"
    assert api.get_run_state(run_id).actions[completed["execution_id"]]["status"] == "completed"


def test_request_supersede_unknown_or_malformed_basis_fails_closed(tmp_path):
    api, run_id = _new_run(tmp_path)
    before_events = list(api.get_events(run_id))

    with pytest.raises(ValueError, match="basis|unknown|proposal"):
        api.request_supersede(
            run_id,
            old_proposal_id="prop_missing",
            replacement_intent=_tool_intent("replacement output"),
            reason="bad basis",
            requested_by="agent_supervisor",
        )

    assert api.get_events(run_id) == before_events
    assert api.get_run_state(run_id).action_supersessions == {}


def test_supersede_runtime_surface_does_not_add_scheduler_concurrency_or_product_http_route(tmp_path):
    api, _run_id = _new_run(tmp_path)
    app = http_api.HttpApiApp(tmp_path / "http")
    route_paths = [path for _method, path in app.routes()]

    assert not hasattr(api, "scheduler")
    assert not hasattr(api, "queue_worker")
    assert not hasattr(api, "process_manager")
    assert not hasattr(api, "concurrency_runtime")
    assert all("supersede" not in path for path in route_paths)
