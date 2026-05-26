from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-tick-driver-trace"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-tick-driver-trace",
    "tick_driver_trace_ok: true",
    "executed_tick_status: executed",
    "executed_selected_step: call_capability",
    "executed_before_phase: ready",
    "executed_after_phase: ready",
    "executed_after_ticks_used: 1",
    "budget_stop_reason: tick_budget_exhausted",
    "user_pause_stop_reason: user_paused",
    "model_status: not_used",
    "scheduler_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "tick_driver_trace_ok",
    "executed_tick",
    "stopped_ticks",
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


def test_tick_driver_trace_plain_cli_prints_tick_handoff_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_tick_driver_trace_json_reports_execute_and_stop_paths():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["tick_driver_trace_ok"] is True
    assert data["executed_tick"]["tick_status"] == "executed"
    assert data["executed_tick"]["selected_step"] == "call_capability"
    assert data["executed_tick"]["before_policy"]["phase"] == "ready"
    assert data["executed_tick"]["after_policy"]["phase"] == "ready"
    assert data["executed_tick"]["after_policy"]["tick_budget"]["ticks_used"] == 1
    assert [tick["case_id"] for tick in data["stopped_ticks"]] == [
        "budget_exhausted",
        "user_pause",
    ]
    assert data["stopped_ticks"][0]["stop_reason"] == "tick_budget_exhausted"
    assert data["stopped_ticks"][1]["stop_reason"] == "user_paused"
    assert data["app_friction"] == []
    assert data["app_friction_count"] == 0


def test_tick_driver_trace_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"


def test_tick_driver_trace_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_tick_driver_trace_shows_human_readable_handoff():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-tick-driver-trace" in result.stdout
    assert "before policy phase: ready" in result.stdout
    assert "planner selected step: call_capability" in result.stdout
    assert "after policy phase: ready" in result.stdout
    assert "budget_exhausted stopped without events" in result.stdout
    assert "user_pause stopped without events" in result.stdout
    assert "real llm" not in result.stdout.lower()
