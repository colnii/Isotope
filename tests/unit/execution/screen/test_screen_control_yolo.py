from __future__ import annotations

import json

import isotope.runtime.in_process as server


class StubScreenBackend:
    def __init__(self, result: dict):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _new_run(tmp_path, backend):
    api = server.InProcessServer(
        tmp_path,
        screen_backend=backend,
        screen_backend_config={
            "backend_id": "stub_screen",
            "backend_version": "0.1",
        },
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="screen yolo control")
    return api, run["run_id"]


def _control_intent() -> dict:
    return {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": {
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        "target_allowlist": {"allowed_title_contains": ["sample"]},
        "mode": "interactive",
        "execution_mode": "execute",
        "approval_mode": "yolo",
        "actions": [{"type": "click", "button": "left", "x": 1, "y": 2}],
        "summary": "control screen with temporary yolo permission",
    }


def _event_types(api, run_id):
    return [event.event_type for event in api.get_events(run_id)]


def test_screen_control_yolo_executes_without_pending_approval(tmp_path):
    backend = StubScreenBackend(
        {
            "backend_session_id": "screen_backend_001",
            "status": "completed",
            "started_at": "2026-05-24T00:00:00Z",
            "finished_at": "2026-05-24T00:00:01Z",
            "summary": "screen control completed",
            "output_artifacts": [
                {
                    "artifact_type": "screen_control_result",
                    "summary": "screen control completed",
                    "content": json.dumps({"action_count": 1, "executed": True}, sort_keys=True),
                }
            ],
            "reason_code": "screen_control_completed",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }
    )
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _control_intent())

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    assert backend.calls[0].operation == "control"
    assert backend.calls[0].actions[0].type == "click"
    assert "approval.requested" not in _event_types(api, run_id)
