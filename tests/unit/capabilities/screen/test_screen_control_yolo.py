from __future__ import annotations

import json

from isotope.capabilities.catalog import CapabilityCatalog
from isotope.capabilities.runner import CapabilityRunner


class StubScreenBackend:
    def __init__(self):
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return {
            "backend_session_id": "stub_screen_control_001",
            "status": "completed",
            "started_at": "2026-05-24T00:00:00Z",
            "finished_at": "2026-05-24T00:00:01Z",
            "summary": "screen control completed",
            "output_artifacts": [
                {
                    "artifact_type": "screen_control_result",
                    "summary": "screen control completed",
                    "content": json.dumps(
                        {"action_count": 1, "executed": True},
                        sort_keys=True,
                    ),
                }
            ],
            "reason_code": "screen_control_completed",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }


def test_screen_control_capability_yolo_executes_with_allowlisted_target(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

    backend = StubScreenBackend()
    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        lambda: backend,
        raising=False,
    )

    result = CapabilityRunner(catalog=CapabilityCatalog.default()).run_capability(
        "screen.control",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"title_contains": "sample"},
            },
            "target_allowlist": {"allowed_title_contains": ["sample"]},
            "execution_mode": "execute",
            "approval_mode": "yolo",
            "actions": [{"type": "click", "button": "left", "x": 10, "y": 20}],
        },
    )

    assert result["status"] == "completed"
    assert result["screen_control"]["status"] == "completed"
    assert result["screen_control"]["approval_id"] is None
    assert len(backend.calls) == 1
    assert backend.calls[0].execution_mode == "execute"
    assert backend.calls[0].actions[0].type == "click"


def test_screen_control_yolo_approval_mode_is_hidden_from_public_manifest():
    catalog = CapabilityCatalog.default()

    public_manifest = catalog.get_manifest()
    public_screen_control = next(
        capability
        for capability in public_manifest["capabilities"]
        if capability["capability_id"] == "screen.control"
    )
    private_screen_control = catalog.describe_capability("screen.control")

    assert "approval_mode" not in public_screen_control["input_contract"]["properties"]
    assert private_screen_control["input_contract"]["properties"]["approval_mode"] == {
        "type": "string",
        "enum": ["single_approval", "yolo"],
        "x-system-input": True,
        "description": (
            "System-only smoke-test approval mode. yolo requires an explicit target_allowlist."
        ),
    }
