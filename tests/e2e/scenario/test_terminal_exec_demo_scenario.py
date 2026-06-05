import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "terminal-exec"

REQUIRED_TEXT_FIELDS = (
    "scenario: terminal-exec",
    "run_status: completed",
    "transport: in_process",
    "terminal_exec_ok: true",
    "terminal_command: printf",
    "terminal_artifact_type: terminal_output",
    "terminal_output_verified: true",
    "replay_ok: true",
    "checkpoint_ok: true",
    "interactive_shell_status: not_used",
    "memory_status: active",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "terminal_exec_ok",
    "terminal_command",
    "terminal_output_artifact_ref",
    "terminal_artifact_summary",
    "terminal_artifact_type",
    "terminal_output_verified",
    "event_count",
    "event_types",
    "replay_ok",
    "checkpoint_ok",
    "interactive_shell_status",
    "network_listener_status",
    "model_status",
    "memory_status",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "stdout",
    "stderr",
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


def test_terminal_exec_plain_cli_prints_short_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "terminal-demo-output" not in result.stdout


def test_terminal_exec_json_cli_exposes_required_status_fields_without_raw_output():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["run_status"] == "completed"
    assert data["transport"] == "in_process"
    assert data["terminal_exec_ok"] is True
    assert data["terminal_command"] == "printf"
    assert data["terminal_artifact_type"] == "terminal_output"
    assert data["terminal_output_verified"] is True
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["memory_status"] == "active"
    _assert_no_forbidden_content_keys(data)
    assert "terminal-demo-output" not in json.dumps(data, sort_keys=True)


def test_terminal_exec_json_uses_structured_artifact_ref():
    data = _run_demo_json("--scenario", SCENARIO)
    ref = data["terminal_output_artifact_ref"]

    assert ref["ref_type"] == "artifact"
    assert ref["scope"] == "run"
    assert ref["run_id"] == data["run_id"]
    assert ref["artifact_id"]
    assert data["terminal_artifact_summary"] == "terminal command completed: printf"


def test_terminal_exec_keeps_queued_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["interactive_shell_status"] == "not_used"
    assert data["network_listener_status"] == "not_used"
    assert data["model_status"] == "not_used"
    assert data["memory_status"] == "active"


def test_terminal_exec_trace_shows_controlled_runtime_without_raw_output():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: terminal-exec" in result.stdout
    assert "[1]" in result.stdout
    assert "terminal_exec" in result.stdout
    assert "policy" in result.stdout.lower()
    assert "artifact" in result.stdout.lower()
    assert "terminal-demo-output" not in result.stdout
