import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-planner-validated-runner"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-planner-validated-runner",
    "planner_validated_runner_ok: true",
    "validator_gate_passed: true",
    "valid_plan_executed: true",
    "invalid_plan_blocked: true",
    "invalid_plan_partial_events_appended: false",
    "app_friction_count: 0",
    "model_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "planner_validated_runner_ok",
    "validator_gate_passed",
    "valid_plan_executed",
    "invalid_plan_blocked",
    "invalid_plan_error_code",
    "invalid_plan_partial_events_appended",
    "agent_loop_friction_ok",
    "app_friction",
    "app_friction_count",
    "private_append_required",
    "replay_ok",
    "checkpoint_ok",
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


def test_planner_validated_runner_plain_cli_prints_runner_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_planner_validated_runner_json_runs_only_after_validator_accepts():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["planner_validated_runner_ok"] is True
    assert data["validator_gate_passed"] is True
    assert data["valid_plan_executed"] is True
    assert data["agent_loop_friction_ok"] is True
    assert data["private_append_required"] is False
    assert data["app_friction"] == []
    assert data["app_friction_count"] == 0
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True


def test_planner_validated_runner_blocks_invalid_plan_before_execution():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["invalid_plan_blocked"] is True
    assert data["invalid_plan_error_code"] == "planner_capability_not_allowed"
    assert data["invalid_plan_events_before"] == data["invalid_plan_events_after"]
    assert data["invalid_plan_artifacts_before"] == data["invalid_plan_artifacts_after"]
    assert data["invalid_plan_partial_events_appended"] is False
    assert data["invalid_plan_artifact_created"] is False


def test_planner_validated_runner_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"


def test_planner_validated_runner_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_planner_validated_runner_trace_shows_gate_then_run():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-planner-validated-runner" in result.stdout
    assert "validate planner output" in result.stdout
    assert "execute validated step" in result.stdout
    assert "block invalid planner output" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
