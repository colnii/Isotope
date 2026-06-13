import importlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from isotope.capabilities.catalog import Capability, CapabilityCatalog
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)
from isotope.platform.schemas.memory import MemoryRecord
from isotope.workspace.artifacts import ArtifactStore


FORBIDDEN_RESULT_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "transcript",
}


def _runner_module():
    return importlib.import_module("isotope.capabilities.runner")


def _runner(*, catalog=None):
    return _runner_module().CapabilityRunner(
        catalog=catalog or CapabilityCatalog.default()
    )


def _ids(entries):
    return [entry["capability_id"] for entry in entries]


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


def _write_memory_record(memory_dir, record):
    from dataclasses import asdict
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )


def _capability(capability_id, shelf, **overrides):
    data = {
        "capability_id": capability_id,
        "title": capability_id.replace(".", " ").title(),
        "description": f"{capability_id} capability metadata.",
        "maturity": "v0.2",
        "shelf": shelf,
        "domain_tags": tuple(capability_id.split(".")),
        "input_contract": {"type": "object"},
        "output_contract": {"type": "object"},
        "safety_boundaries": ("public_metadata_manifest_only",),
        "default_enabled": True,
        "required_env": (),
        "network_required": False,
        "provider": None,
        "model": None,
    }
    data.update(overrides)
    return Capability(**data)

def test_runner_discovers_screen_report_from_default_catalog():
    runner = _runner()

    assert "screen.report" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="screen report")

    assert "screen.report" in _ids(search["capabilities"])
    description = runner.describe_capability("screen.report")
    assert description["input_contract"]["required"] == ["root", "run_id"]
    assert "screen_artifact_projection" in description["safety_boundaries"]
    assert "public_result_metadata" in description["safety_boundaries"]



def test_screen_report_manifest_uses_projection_language():
    description = _runner().describe_capability("screen.report")
    manifest_text = json.dumps(description, ensure_ascii=False)
    forbidden_terms = [
        "read" + "_snapshot",
        "只读" + "扫描",
        "不" + "执行",
    ]

    assert "screen_artifact_projection" in description["safety_boundaries"]
    for term in forbidden_terms:
        assert term not in manifest_text



def test_runner_discovers_screen_observe_from_default_catalog():
    runner = _runner()

    assert "screen.observe" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="screen observe")

    assert "screen.observe" in _ids(search["capabilities"])
    description = runner.describe_capability("screen.observe")
    assert description["input_contract"]["required"] == ["target_selector"]
    assert "policy_gated_screen_observe" in description["safety_boundaries"]
    assert "screen_report_artifact" in description["safety_boundaries"]
    assert "no_screenshot_content_in_events" in description["safety_boundaries"]
    assert "screenshot_content_for_model_observation" in description["safety_boundaries"]


def test_runner_discovers_screen_control_from_default_catalog():
    runner = _runner()

    assert "screen.control" in _ids(runner.list_capabilities())
    search = runner.search_capabilities(query="screen control")

    assert "screen.control" in _ids(search["capabilities"])
    description = runner.describe_capability("screen.control")
    assert description["input_contract"]["required"] == [
        "target_selector",
        "execution_mode",
        "actions",
    ]
    assert "policy_gated_screen_control" in description["safety_boundaries"]
    assert "approval_required_for_execute" in description["safety_boundaries"]
    assert "target_allowlist_supported" in description["safety_boundaries"]



def test_screen_report_plan_stops_when_required_inputs_are_missing():
    plan = _runner().plan_capability_run(
        "screen.report",
        inputs={"root": "/tmp/isotope-runtime"},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_projection"
    assert plan["missing_inputs"] == ["run_id"]
    assert plan["scenario"] is None



def test_screen_observe_plan_stops_when_target_selector_is_missing(tmp_path):
    plan = _runner().plan_capability_run(
        "screen.observe",
        inputs={"root": str(tmp_path)},
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["target_selector"]
    assert plan["scenario"] is None


def test_screen_control_plan_stops_when_actions_are_missing(tmp_path):
    plan = _runner().plan_capability_run(
        "screen.control",
        inputs={
            "root": str(tmp_path),
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "execution_mode": "dry_run",
        },
    )

    assert plan["can_launch"] is False
    assert plan["status"] == "missing_inputs"
    assert plan["runner_kind"] == "deterministic_local"
    assert plan["missing_inputs"] == ["actions"]
    assert plan["scenario"] is None



def test_screen_report_capability_runs_existing_public_metadata_report(tmp_path):
    store = ArtifactStore(tmp_path)
    store.create_artifact(
        "run_screen",
        execution_id="exec_screen",
        artifact_type="screen_control_plan",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 1,
                "executed": False,
                "planned_actions": ["restore_window"],
                "private_note": "raw screen control payload must not leak",
            },
            sort_keys=True,
        ),
    )

    result = _runner().run_capability(
        "screen.report",
        inputs={
            "root": str(tmp_path),
            "run_id": "run_screen",
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "screen.report"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_projection"
    screen_report = result["screen_report"]
    assert screen_report["status"] == "ok"
    assert screen_report["summary"]["control_status"] == "planned"
    assert screen_report["summary"]["approval_required"] is True
    assert screen_report["summary"]["control_actions"][0]["action_types"] == [
        "restore_window"
    ]
    assert "raw screen control payload" not in json.dumps(result, sort_keys=True)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_screen_control_capability_runs_dry_run_plan_and_reports_artifacts(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

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
                        "artifact_type": "screen_control_plan",
                        "summary": "screen control result",
                        "content": json.dumps(
                            {
                                "action_count": 1,
                                "executed": False,
                                "planned_actions": ["click"],
                                "private_note": "raw screen control payload must not leak",
                            },
                            sort_keys=True,
                        ),
                    },
                ],
                "reason_code": "screen_control_completed",
                "retryable": False,
                "resource_usage": {"window_count": 1},
            }

    backend = StubScreenBackend()
    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        lambda: backend,
        raising=False,
    )

    result = _runner().run_capability(
        "screen.control",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "target_allowlist": {"allowed_apps": ["notepad.exe"]},
            "execution_mode": "dry_run",
            "actions": [{"type": "click", "button": "left", "x": 10, "y": 20}],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "screen.control"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert result["screen_control"]["status"] == "completed"
    assert result["screen_control"]["run_id"] == result["screen_report"]["run_id"]
    assert backend.calls[0].tool_name == "screen_control"
    assert backend.calls[0].execution_mode == "dry_run"
    assert backend.calls[0].actions[0].to_dict() == {
        "type": "click",
        "x": 10,
        "y": 20,
        "button": "left",
    }
    screen_report = result["screen_report"]
    assert screen_report["summary"]["control_status"] == "planned"
    assert screen_report["summary"]["approval_required"] is True
    assert screen_report["summary"]["control_actions"][0]["action_types"] == ["click"]
    assert "raw screen control payload" not in json.dumps(result, sort_keys=True)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


def test_screen_control_execute_capability_returns_pending_approval_without_backend_call(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

    class StubScreenBackend:
        def __init__(self):
            self.calls = []

        def run(self, request):
            self.calls.append(request)
            raise AssertionError("screen execute must not call backend before approval")

    backend = StubScreenBackend()
    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        lambda: backend,
        raising=False,
    )

    result = _runner().run_capability(
        "screen.control",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "target_allowlist": {"allowed_apps": ["notepad.exe"]},
            "execution_mode": "execute",
            "actions": [{"type": "restore_window"}],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "screen.control"
    assert result["status"] == "pending_user_approval"
    assert result["runner_kind"] == "deterministic_local"
    assert result["screen_control"]["status"] == "pending_user_approval"
    assert result["screen_control"]["approval_id"]
    assert result["screen_control"]["execution_id"] is None
    assert result["screen_report"]["summary"]["control_status"] == "none"
    assert backend.calls == []
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



def test_screen_observe_capability_runs_policy_gated_observe_and_reports_artifacts(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

    class StubScreenBackend:
        def __init__(self):
            self.calls = []

        def run(self, request):
            self.calls.append(request)
            return {
                "backend_session_id": "stub_screen_001",
                "status": "captured",
                "started_at": "2026-05-24T00:00:00Z",
                "finished_at": "2026-05-24T00:00:01Z",
                "summary": "screen observe captured",
                "output_artifacts": [
                    {
                        "artifact_type": "screen_metadata",
                        "summary": "screen metadata captured",
                        "content": json.dumps(
                            {
                                "matched_count": 1,
                                "selected_window_id": "window_001",
                                "selection_reason": "first_match",
                                "target": {
                                    "window_id": "window_001",
                                    "title": "Notes",
                                    "app": "notepad.exe",
                                    "is_minimized": False,
                                },
                            },
                            sort_keys=True,
                        ),
                    },
                    {
                        "artifact_type": "screen_screenshot",
                        "summary": "screen screenshot captured",
                        "content": "raw screenshot bytes must not leak",
                    },
                ],
                "reason_code": "screen_observe_captured",
                "retryable": False,
                "resource_usage": {"window_count": 1},
            }

    backend = StubScreenBackend()
    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        lambda: backend,
        raising=False,
    )

    result = _runner().run_capability(
        "screen.observe",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "target_allowlist": {"allowed_apps": ["notepad.exe"]},
            "capture": ["metadata", "screenshot"],
        },
    )

    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "screen.observe"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert result["screen_observe"]["status"] == "completed"
    assert result["screen_observe"]["run_id"] == result["screen_report"]["run_id"]
    assert backend.calls[0].tool_name == "screen_observe"
    assert backend.calls[0].capture == ["metadata", "screenshot"]
    screen_report = result["screen_report"]
    assert screen_report["summary"]["observe_status"] == "captured"
    assert screen_report["summary"]["screenshot_available"] is True
    assert screen_report["summary"]["matched_count"] == 1
    assert screen_report["summary"]["selected_window_id"] == "window_001"
    assert "raw screenshot bytes" not in json.dumps(result, sort_keys=True)
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)



def test_screen_observe_capability_reports_backend_failure_without_artifacts(
    tmp_path,
    monkeypatch,
):
    from isotope.capabilities import screen as screen_capability

    class StubScreenBackend:
        def run(self, request):
            return {
                "backend_session_id": "stub_screen_unavailable",
                "status": "failed",
                "started_at": "2026-05-24T00:00:00Z",
                "finished_at": "2026-05-24T00:00:01Z",
                "summary": "Windows screen backend is unavailable",
                "output_artifacts": [],
                "reason_code": "screen_windows_backend_unavailable",
                "retryable": False,
                "resource_usage": {},
            }

    monkeypatch.setattr(
        screen_capability,
        "WindowsScreenBackend",
        StubScreenBackend,
        raising=False,
    )

    result = _runner().run_capability(
        "screen.observe",
        root_path=tmp_path,
        inputs={
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "target_allowlist": {"allowed_apps": ["notepad.exe"]},
            "capture": ["metadata"],
        },
    )

    assert result["status"] == "completed"
    assert result["screen_observe"]["status"] == "failed"
    assert result["screen_observe"]["failure"] == {
        "reason_code": "screen_windows_backend_unavailable",
        "message": "Windows screen backend is unavailable",
    }
    assert result["screen_report"]["summary"]["observe_status"] == "no_screen_artifacts"
    assert result["screen_report"]["summary"]["artifact_count"] == 0
    for mapping in _walk_mapping(result):
        assert FORBIDDEN_RESULT_KEYS.isdisjoint(mapping)


