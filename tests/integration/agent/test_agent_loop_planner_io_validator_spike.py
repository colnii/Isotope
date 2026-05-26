import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-planner-io-validator"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-planner-io-validator",
    "planner_io_validator_ok: true",
    "valid_output_accepted: true",
    "malformed_rejected: true",
    "unknown_action_rejected: true",
    "overpowered_rejected: true",
    "full_content_rejected: true",
    "partial_events_appended: false",
    "app_friction_count: 0",
    "model_status: not_used",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "transport",
    "planner_io_validator_ok",
    "valid_output_accepted",
    "rejected_fixture_count",
    "fixtures",
    "partial_events_appended",
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


def _fixture(data: dict[str, Any], fixture_id: str) -> dict[str, Any]:
    for fixture in data["fixtures"]:
        if fixture["fixture_id"] == fixture_id:
            return fixture
    raise AssertionError(f"missing fixture {fixture_id}")


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_planner_io_validator_plain_cli_prints_gatekeeper_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_planner_io_validator_json_accepts_valid_and_rejects_bad_outputs():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["planner_io_validator_ok"] is True
    assert data["valid_output_accepted"] is True
    assert data["rejected_fixture_count"] == 4
    assert data["app_friction"] == []
    assert data["app_friction_count"] == 0

    malformed = _fixture(data, "malformed_output")
    assert malformed["status"] == "rejected"
    assert malformed["error_code"] == "planner_output_malformed"

    unknown = _fixture(data, "unknown_action")
    assert unknown["status"] == "rejected"
    assert unknown["error_code"] == "unknown_planner_action"

    overpowered = _fixture(data, "overpowered_capability")
    assert overpowered["status"] == "rejected"
    assert overpowered["error_code"] == "planner_capability_not_allowed"

    full_content = _fixture(data, "full_content_without_grant")
    assert full_content["status"] == "rejected"
    assert full_content["error_code"] == "artifact_full_content_not_granted"


def test_planner_io_validator_fails_closed_without_side_effects():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["events_before_validation"] == data["events_after_validation"]
    assert data["artifact_count_before_validation"] == data["artifact_count_after_validation"]
    assert data["partial_events_appended"] is False
    assert data["artifact_created_during_validation"] is False


def test_planner_io_validator_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"


def test_planner_io_validator_json_excludes_model_and_artifact_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_planner_io_validator_trace_shows_gatekeeper_decisions():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-planner-io-validator" in result.stdout
    assert "accept valid planner output" in result.stdout
    assert "reject malformed_output" in result.stdout
    assert "reject unknown_action" in result.stdout
    assert "reject overpowered_capability" in result.stdout
    assert "reject full_content_without_grant" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
