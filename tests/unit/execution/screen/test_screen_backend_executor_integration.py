from __future__ import annotations

import json

import isotope.runtime.in_process as server
from isotope.execution.screen import windows_backend


class StubScreenBackend:
    def __init__(self, result: dict):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _backend_result(*, content: str = '{"window_count": 1}'):
    return {
        "backend_session_id": "screen_backend_001",
        "status": "captured",
        "started_at": "2026-05-24T00:00:00Z",
        "finished_at": "2026-05-24T00:00:01Z",
        "summary": "screen observe captured",
        "output_artifacts": [
            {
                "artifact_type": "screen_metadata",
                "summary": "screen metadata captured",
                "content": content,
            }
        ],
        "reason_code": "screen_observe_captured",
        "retryable": False,
        "resource_usage": {"duration_ms": 10},
    }


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
    run = api.create_run(session["session_id"], goal="screen backend integration")
    return api, run["run_id"]


def _observe_intent():
    return {
        "action": "call_tool",
        "tool": "screen_observe",
        "target_selector": {
            "kind": "window",
            "selector": {"app": "notepad.exe"},
        },
        "mode": "non_intrusive",
        "capture": ["metadata"],
        "summary": "observe screen",
    }


def _control_intent(*, execution_mode: str = "dry_run"):
    return {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": {
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        "mode": "interactive",
        "execution_mode": execution_mode,
        "actions": [{"type": "click", "button": "left", "x": 1, "y": 2}],
        "summary": "control screen",
    }


def _event_types(api, run_id):
    return [event.event_type for event in api.get_events(run_id)]


def _approved_body():
    return {
        "resolution": "approved",
        "reason": "operator approved screen control",
        "resolver": "human_reviewer",
    }


def test_screen_observe_creates_artifact_without_leaking_content_to_events(tmp_path):
    secret = '{"window_title": "secret title"}'
    backend = StubScreenBackend(_backend_result(content=secret))
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _observe_intent())

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    assert backend.calls[0].tool_name == "screen_observe"
    assert backend.calls[0].operation == "observe"
    assert _event_types(api, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
    assert secret not in repr(api.get_events(run_id))
    assert api.artifact_store.get_content(result["artifact_ref"]) == secret


def test_screen_control_execute_requires_approval_before_backend_call(tmp_path):
    backend = StubScreenBackend(_backend_result(content='{"clicked": true}'))
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _control_intent(execution_mode="execute"))

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["screen_approval_required"]
    assert backend.calls == []
    assert api.artifact_store.list_artifacts(run_id) == []


def test_screen_control_execute_runs_after_approval(tmp_path):
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
                    "content": json.dumps({"action_count": 1}, sort_keys=True),
                }
            ],
            "reason_code": "screen_control_completed",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }
    )
    api, run_id = _new_run(tmp_path, backend)

    pending = api.submit_action(
        run_id,
        _control_intent(execution_mode="execute"),
        requires_approval=True,
    )
    assert pending["status"] == "pending_user_approval"
    assert backend.calls == []

    result = api.resolve_approval(pending["approval_id"], _approved_body())

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    assert backend.calls[0].operation == "control"
    assert backend.calls[0].actions[0].type == "click"


def test_screen_control_backend_request_preserves_double_click_and_drag_actions(tmp_path):
    backend = StubScreenBackend(
        {
            "backend_session_id": "screen_backend_001",
            "status": "completed",
            "started_at": "2026-05-24T00:00:00Z",
            "finished_at": "2026-05-24T00:00:01Z",
            "summary": "screen control completed",
            "output_artifacts": [
                {
                    "artifact_type": "screen_control_plan",
                    "summary": "screen control plan",
                    "content": json.dumps(
                        {
                            "action_count": 2,
                            "executed": False,
                            "planned_actions": ["double_click", "drag"],
                        },
                        sort_keys=True,
                    ),
                }
            ],
            "reason_code": "screen_control_completed",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }
    )
    api, run_id = _new_run(tmp_path, backend)
    intent = _control_intent()
    intent["actions"] = [
        {"type": "double_click", "button": "left", "x": 1, "y": 2},
        {"type": "drag", "button": "left", "x": 1, "y": 2, "to_x": 30, "to_y": 40},
    ]

    result = api.submit_action(run_id, intent)

    assert result["status"] == "completed"
    assert [action.to_dict() for action in backend.calls[0].actions] == [
        {"type": "double_click", "x": 1, "y": 2, "button": "left"},
        {"type": "drag", "x": 1, "y": 2, "button": "left", "to_x": 30, "to_y": 40},
    ]


def test_screen_control_backend_request_preserves_keyboard_actions(tmp_path):
    backend = StubScreenBackend(
        {
            "backend_session_id": "screen_backend_001",
            "status": "completed",
            "started_at": "2026-05-24T00:00:00Z",
            "finished_at": "2026-05-24T00:00:01Z",
            "summary": "screen control completed",
            "output_artifacts": [
                {
                    "artifact_type": "screen_control_plan",
                    "summary": "screen control plan",
                    "content": json.dumps(
                        {
                            "action_count": 3,
                            "executed": False,
                            "planned_actions": ["key_down", "key_press", "key_up"],
                        },
                        sort_keys=True,
                    ),
                }
            ],
            "reason_code": "screen_control_completed",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }
    )
    api, run_id = _new_run(tmp_path, backend)
    intent = _control_intent()
    intent["actions"] = [
        {"type": "key_down", "key": "Shift"},
        {"type": "key_press", "key": "A"},
        {"type": "key_up", "key": "Shift"},
    ]

    result = api.submit_action(run_id, intent)

    assert result["status"] == "completed"
    assert [action.to_dict() for action in backend.calls[0].actions] == [
        {"type": "key_down", "key": "Shift"},
        {"type": "key_press", "key": "A"},
        {"type": "key_up", "key": "Shift"},
    ]


def test_windows_backend_script_supports_double_click_and_drag_branches():
    script = windows_backend._POWERSHELL_SCRIPT

    assert '$action.type -eq "double_click"' in script
    assert '$action.type -eq "drag"' in script
    assert "SetCursorPos([int]$action.to_x, [int]$action.to_y)" in script


def test_windows_backend_script_supports_keyboard_down_up_branches():
    script = windows_backend._POWERSHELL_SCRIPT

    assert "function Resolve-KeyCode" in script
    assert '$action.type -eq "key_press"' in script
    assert '$action.type -eq "key_down"' in script
    assert '$action.type -eq "key_up"' in script
    assert "KEYEVENTF_KEYUP" in script
    assert "keybd_event" in script
    assert '"enter" = 0x0D' in script
    assert '"shift" = 0x10' in script
    assert "SendKeys" not in script


def test_screen_restore_window_execute_requires_approval_before_backend_call(tmp_path):
    backend = StubScreenBackend(_backend_result(content='{"restored": true}'))
    api, run_id = _new_run(tmp_path, backend)
    intent = _control_intent(execution_mode="execute")
    intent["actions"] = [{"type": "restore_window"}]

    result = api.submit_action(run_id, intent)

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["screen_approval_required"]
    assert backend.calls == []


def test_backend_reported_widened_grants_are_rejected(tmp_path):
    raw_result = _backend_result()
    raw_result["reported_grants"] = {"tools": ["screen_observe", "screen_control"]}
    backend = StubScreenBackend(raw_result)
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _observe_intent())

    assert result["status"] == "failed"
    failed = next(event for event in api.get_events(run_id) if event.event_type == "action.failed")
    assert failed.payload["error_reason_code"] == "screen_backend_protocol_error"


def test_screen_observe_accepts_metadata_only_fallback_result(tmp_path):
    backend = StubScreenBackend(
        {
            "backend_session_id": "screen_backend_001",
            "status": "metadata_only",
            "started_at": "2026-05-24T00:00:00Z",
            "finished_at": "2026-05-24T00:00:01Z",
            "summary": "screen observe captured metadata only",
            "output_artifacts": [
                {
                    "artifact_type": "screen_metadata",
                    "summary": "screen metadata captured",
                    "content": json.dumps({"target": {"is_minimized": True}}, sort_keys=True),
                },
                {
                    "artifact_type": "screen_diagnostic",
                    "summary": "screen screenshot diagnostic",
                    "content": json.dumps(
                        {
                            "reason_code": "screen_screenshot_unavailable",
                            "recovery": "restore_window_requires_approval",
                        },
                        sort_keys=True,
                    ),
                },
            ],
            "reason_code": "screen_screenshot_unavailable",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }
    )
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(
        run_id,
        {
            **_observe_intent(),
            "capture": ["metadata", "screenshot"],
        },
    )

    assert result["status"] == "completed"
    assert len(api.artifact_store.list_artifacts(run_id)) == 2


def test_windows_backend_request_payload_carries_target_selection_policy(tmp_path):
    backend = StubScreenBackend(_backend_result())
    api, run_id = _new_run(tmp_path, backend)

    api.submit_action(run_id, _observe_intent())

    payload = windows_backend._request_payload(backend.calls[0])
    assert payload["target_selection_policy"] == {
        "allowed_apps": [],
        "allowed_title_contains": [],
        "allow_first_match_execute": False,
    }


def test_windows_backend_script_reports_first_match_metadata_and_guards_execute():
    script = windows_backend._POWERSHELL_SCRIPT

    assert "matched_count" in script
    assert "selected_window_id" in script
    assert "selection_reason" in script
    assert "first_match" in script
    assert "allow_first_match_execute" in script
    assert "screen_target_ambiguous" in script


def test_windows_backend_script_preserves_single_window_match_as_collection():
    script = windows_backend._POWERSHELL_SCRIPT

    assert "$matches = @(Select-MatchingWindows $windows $selector)" in script


def test_windows_backend_script_downgrades_uncapturable_screenshot_to_metadata_only():
    script = windows_backend._POWERSHELL_SCRIPT

    assert "IsIconic" in script
    assert "is_minimized" in script
    assert "metadata_only" in script
    assert "screen_screenshot_unavailable" in script
    assert "restore_window_requires_approval" in script


def test_windows_backend_script_can_restore_window_after_approval():
    script = windows_backend._POWERSHELL_SCRIPT

    assert "ShowWindow" in script
    assert "SW_RESTORE" in script
    assert "restore_window" in script
