from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "supervisor-capacity-handoff-trace"

REQUIRED_TEXT_FIELDS = (
    "scenario: supervisor-capacity-handoff-trace",
    "capacity_handoff_trace_ok: true",
    "supervisor_action_kind: call_capacity",
    "capacity_id: artifact.review",
    "planner_selected_step: call_capability",
    "tick_status: executed",
    "tick_after_stop_reason: tick_budget_exhausted",
    "persisted_policy_phase: ready",
    "model_status: not_used",
    "scheduler_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "capacity_handoff_trace_ok",
    "supervisor_action",
    "capacity_decision",
    "planner_output",
    "tick_result",
    "persisted_run_policy",
    "app_friction",
    "app_friction_count",
    "model_status",
    "scheduler_status",
    "provider_status",
    "next_development_step",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "model_prompt",
    "model_response",
    "raw_artifact_content",
    "raw_content",
}


def _run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.demo", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _run_demo_json(*args: str) -> dict[str, Any]:
    result = _run_demo(*args, "--json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_supervisor_capacity_handoff_plain_cli_prints_tick_result():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_supervisor_capacity_handoff_json_reports_action_to_tick_chain():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["capacity_handoff_trace_ok"] is True
    assert data["supervisor_action"] == {
        "kind": "call_capacity",
        "capacity_id": "artifact.review",
    }
    assert data["capacity_decision"]["next_action"] == "call_capacity"
    assert data["capacity_decision"]["can_execute_agent_loop"] is True
    assert data["planner_output"] == {
        "planner_run_id": "supervisor_capacity:artifact.review",
        "selected_step": "call_capability",
        "capability_id": "artifact.review",
    }
    assert data["tick_result"]["tick_status"] == "executed"
    assert data["tick_result"]["planner_status"] == "accepted"
    assert data["tick_result"]["selected_step"] == "call_capability"
    assert data["tick_result"]["step_status"] == "completed"
    assert data["tick_result"]["after_policy"]["must_stop_reason"] == "tick_budget_exhausted"
    assert data["persisted_run_policy"]["phase"] == "ready"
    assert data["persisted_run_policy"]["must_stop_reason"] is None
    assert data["app_friction"] == []
    assert data["app_friction_count"] == 0


def test_supervisor_capacity_handoff_keeps_queued_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "fixture_only"
    assert data.get("network_listener_status", "not_used") == "not_used"


def test_supervisor_capacity_handoff_json_excludes_raw_model_and_artifact_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_supervisor_capacity_handoff_trace_shows_human_readable_chain():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: supervisor-capacity-handoff-trace" in result.stdout
    assert "supervisor action: call_capacity artifact.review" in result.stdout
    assert "capacity decision: call_capacity" in result.stdout
    assert "planner output summary: call_capability" in result.stdout
    assert "tick result: executed" in result.stdout
    assert "persisted run policy phase: ready" in result.stdout
    assert "real llm" not in result.stdout.lower()
