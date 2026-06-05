import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-tick-policy-trace"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-tick-policy-trace",
    "tick_policy_trace_ok: true",
    "ready_continue_ok: true",
    "user_pause_stop_reason: user_paused",
    "budget_stop_reason: tick_budget_exhausted",
    "approval_stop_reason: awaiting_approval",
    "completed_stop_reason: completed",
    "model_status: not_used",
    "scheduler_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "tick_policy_trace_ok",
    "tick_policies",
    "ready_continue_ok",
    "user_pause_stop_reason",
    "budget_stop_reason",
    "approval_stop_reason",
    "completed_stop_reason",
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


def test_tick_policy_trace_plain_cli_prints_stop_reason_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_tick_policy_trace_json_reports_continue_and_stop_reasons():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["tick_policy_trace_ok"] is True
    assert data["ready_continue_ok"] is True
    assert data["user_pause_stop_reason"] == "user_paused"
    assert data["budget_stop_reason"] == "tick_budget_exhausted"
    assert data["approval_stop_reason"] == "awaiting_approval"
    assert data["completed_stop_reason"] == "completed"
    assert data["app_friction"] == []
    assert data["app_friction_count"] == 0
    assert [policy["case_id"] for policy in data["tick_policies"]] == [
        "ready_continue",
        "user_pause",
        "budget_exhausted",
        "awaiting_approval",
        "completed",
    ]


def test_tick_policy_trace_keeps_queued_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"


def test_tick_policy_trace_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_tick_policy_trace_mode_shows_policy_handoff():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-tick-policy-trace" in result.stdout
    assert "ready_continue should_continue=true" in result.stdout
    assert "user_pause stop reason: user_paused" in result.stdout
    assert "budget_exhausted stop reason: tick_budget_exhausted" in result.stdout
    assert "awaiting_approval stop reason: awaiting_approval" in result.stdout
    assert "completed stop reason: completed" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
