import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "agent-loop-friction"

REQUIRED_TEXT_FIELDS = (
    "scenario: agent-loop-friction",
    "agent_loop_friction_ok: true",
    "private_append_required: false",
    "app_friction_count: 0",
    "replay_ok: true",
    "checkpoint_ok: true",
    "model_status: not_used",
    "scheduler_status: not_used",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "agent_loop_friction_ok",
    "loop_steps",
    "resolved_app_surfaces",
    "app_friction",
    "private_append_required",
    "replay_ok",
    "checkpoint_ok",
    "model_status",
    "scheduler_status",
    "provider_status",
    "memory_status",
    "next_development_step",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
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


def test_agent_loop_friction_plain_cli_prints_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "real llm" not in result.stdout.lower()


def test_agent_loop_friction_json_reports_no_core_gap_for_current_public_helpers():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["agent_loop_friction_ok"] is True
    assert data["private_append_required"] is False
    assert data["app_friction"] == []
    assert len(data["loop_steps"]) >= 5
    assert "submit_action" in data["resolved_app_surfaces"]
    assert "submit_worker_handoff" in data["resolved_app_surfaces"]
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True


def test_agent_loop_friction_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["transport"] == "in_process"
    assert data["model_status"] == "not_used"
    assert data["scheduler_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"


def test_agent_loop_friction_json_excludes_full_artifact_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_agent_loop_friction_trace_shows_loop_steps_and_next_step():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: agent-loop-friction" in result.stdout
    assert "plan deterministic next action" in result.stdout
    assert "handoff worker result" in result.stdout
    assert "next development step" in result.stdout
    assert "raw artifact content" not in result.stdout.lower()
