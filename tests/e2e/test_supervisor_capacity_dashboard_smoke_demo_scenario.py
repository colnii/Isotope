from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "supervisor-capacity-dashboard-smoke"

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "model_prompt",
    "model_response",
    "raw",
    "raw_artifact_content",
    "raw_content",
    "step_result",
    "tick_result",
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


def test_supervisor_capacity_dashboard_smoke_json_links_execution_memory_and_dashboard():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["scenario"] == SCENARIO
    assert data["capacity_dashboard_smoke_ok"] is True
    assert data["executed"]["kind"] == "call_capacity"
    execution_summary = data["executed"]["agent_loop_summary"]
    memory_summary = data["memory_record"]["agent_loop_summary"]
    dashboard_summary = data["dashboard_recent_capacity_summary"]["agent_loop_summary"]
    assert execution_summary == memory_summary == dashboard_summary
    assert dashboard_summary["agent_loop_tick_status"] == "executed"
    assert dashboard_summary["agent_loop_planner_selected_step"] == "call_capability"
    assert dashboard_summary["agent_loop_artifact_id"].startswith("artifact_")
    assert data["dashboard_recent_capacity_summary"]["capacity_id"] == "artifact.review"
    assert data["dashboard_capacity_calls_total"] == 1
    assert data["app_friction"] == []
    assert data["provider_status"] == "fixture_only"
    assert data["model_status"] == "not_used"
    _assert_no_forbidden_content_keys(data)


def test_supervisor_capacity_dashboard_smoke_plain_cli_prints_dashboard_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    assert "scenario: supervisor-capacity-dashboard-smoke" in result.stdout
    assert "capacity_dashboard_smoke_ok: true" in result.stdout
    assert "capacity_id: artifact.review" in result.stdout
    assert "dashboard_tick_status: executed" in result.stdout
    assert "dashboard_selected_step: call_capability" in result.stdout
    assert "dashboard_capacity_calls_total: 1" in result.stdout
