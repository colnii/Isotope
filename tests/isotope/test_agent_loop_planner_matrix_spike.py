import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-planner-matrix"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-planner-matrix",
    "planner_matrix_ok: true",
    "fixture_count: 3",
    "happy_path_ok: true",
    "blocked_deferred_ok: true",
    "malformed_fail_closed_ok: true",
    "kernel_friction_count: 0",
    "model_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "transport",
    "planner_matrix_ok",
    "fixture_count",
    "fixtures",
    "kernel_friction",
    "kernel_friction_count",
    "app_deferred_friction",
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


def _fixture(data: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    for fixture in data["fixtures"]:
        if fixture["fixture_id"] == fixture_id:
            return fixture
    raise AssertionError(f"missing fixture {fixture_id}")


def test_planner_matrix_plain_cli_prints_fixture_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_planner_matrix_json_reports_happy_blocked_and_malformed_paths():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["planner_matrix_ok"] is True
    assert data["fixture_count"] == 3
    assert data["kernel_friction"] == []
    assert data["kernel_friction_count"] == 0

    happy = _fixture(data, "happy_path")
    assert happy["status"] == "ok"
    assert happy["kernel_friction"] == []
    assert happy["private_append_required"] is False
    assert happy["replay_ok"] is True
    assert happy["checkpoint_ok"] is True

    blocked = _fixture(data, "blocked_deferred_capability")
    assert blocked["status"] == "blocked_deferred"
    assert blocked["blocked_capability"] in {"real_llm_plan", "memory_query"}
    assert blocked["kernel_friction"] == []
    assert blocked["app_deferred_friction"]

    malformed = _fixture(data, "malformed_symbolic_action")
    assert malformed["status"] == "failed_closed"
    assert malformed["unknown_action"] == "unknown_symbolic_action"
    assert malformed["partial_events_appended"] is False
    assert malformed["kernel_friction"] == []


def test_planner_matrix_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"


def test_planner_matrix_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_planner_matrix_trace_shows_all_fixture_paths_and_next_step():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-planner-matrix" in result.stdout
    assert "happy_path" in result.stdout
    assert "blocked_deferred_capability" in result.stdout
    assert "malformed_symbolic_action" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
