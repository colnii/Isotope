import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from isotope.interfaces.http import create_http_app


FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _request(app, method: str, path: str, json_body: Any = None):
    return app.request(method, path, json=json_body)


def _status_code(response) -> int:
    if isinstance(response, Mapping):
        return int(response["status_code"])
    return int(response.status_code)


def _body(response) -> dict[str, Any]:
    if isinstance(response, Mapping):
        body = response.get("json", response.get("body"))
    elif callable(getattr(response, "json", None)):
        body = response.json()
    else:
        body = getattr(response, "body", None)
    assert isinstance(body, dict)
    return body


def _event_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("runs/*/events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                assert isinstance(record, dict)
                records.append(record)
    return records


def _artifact_files(root: Path) -> list[Path]:
    return sorted(root.glob("runs/*/artifacts/*.json"))


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _create_run(app, goal: str = "agent loop run control") -> tuple[str, dict[str, Any]]:
    session = app.server.create_session()
    return session["session_id"], app.server.create_run(session["session_id"], goal=goal)


def test_http_agent_loop_control_returns_product_read_model(tmp_path):
    app = create_http_app(tmp_path)
    session_id, run = _create_run(app, goal="review a draft")

    response = _request(app, "GET", f"/runs/{run['run_id']}/agent-loop-control")

    assert _status_code(response) == 200
    body = _body(response)
    assert body["run_id"] == run["run_id"]
    assert body["session_id"] == session_id
    assert body["goal"] == "review a draft"
    assert body["status"] == "running"
    assert body["phase"] == "ready"
    assert body["waiting_on"] == []
    assert body["next_actions"] == [
        "query_memory",
        "create_source_artifact",
        "record_turn_memory",
        "promote_run_memory",
        "submit_worker_handoff",
        "submit_approval_gated_action",
        "call_capability",
    ]
    assert body["integration_slots"] == [
        "real_llm_provider",
        "scheduler",
        "real_worker_runtime",
    ]
    assert body["progress"] == {
        "actions_total": 0,
        "actions_completed": 0,
        "actions_pending_approval": 0,
        "artifacts_total": 0,
        "memory_records_total": 0,
        "workers_total": 0,
        "workspaces_total": 0,
    }
    _assert_no_forbidden_content_keys(body)


def test_http_agent_loop_control_shows_pending_approval_without_side_effects(tmp_path):
    app = create_http_app(tmp_path)
    _session_id, run = _create_run(app, goal="ask before tool use")
    result = app.server.submit_tool_request(
        run["run_id"],
        tool="write_artifact_tool",
        text="hello",
        requires_approval=True,
    )
    before_events = _event_records(tmp_path)
    before_artifacts = _artifact_files(tmp_path)
    approval_id = result["approval_id"]

    response = _request(app, "GET", f"/runs/{run['run_id']}/agent-loop-control")

    assert _status_code(response) == 200
    body = _body(response)
    assert body["status"] == "pending_user_approval"
    assert body["phase"] == "awaiting_approval"
    assert body["waiting_on"] == [
        {
            "kind": "approval",
            "approval_id": approval_id,
            "status": "pending",
            "reason_codes": ["approval_required"],
            "requested_action_summary": {"action_type": "call_tool"},
        }
    ]
    assert body["next_actions"] == ["get_approval", "resolve_approval"]
    assert body["approvals"] == {"pending_count": 1, "pending_ids": [approval_id]}
    assert body["blocked_reason_codes"] == ["approval_required"]
    assert body["progress"]["actions_pending_approval"] == 1
    assert _event_records(tmp_path) == before_events
    assert _artifact_files(tmp_path) == before_artifacts


def test_http_agent_loop_control_returns_404_for_unknown_run(tmp_path):
    app = create_http_app(tmp_path)

    response = _request(app, "GET", "/runs/run_missing/agent-loop-control")

    assert _status_code(response) == 404
    body = _body(response)
    assert body["status"] == "not_found"
    assert body["error"]["code"] == "not_found"


def test_http_agent_loop_control_is_supported_in_route_inventory(tmp_path):
    app = create_http_app(tmp_path)

    inventory = app.list_routes()

    assert {
        "method": "GET",
        "path": "/runs/{run_id}/agent-loop-control",
        "status": "supported",
    } in inventory["routes"]
