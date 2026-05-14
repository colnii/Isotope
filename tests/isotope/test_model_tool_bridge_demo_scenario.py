import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "model-tool-bridge"

REQUIRED_TEXT_FIELDS = (
    "scenario: model-tool-bridge",
    "run_status: completed",
    "transport: in_process",
    "model_tool_bridge_ok: true",
    "model_tool_name: codex_task",
    "approval_pending_before_execution: true",
    "approval_ok: true",
    "codex_started_after_approval: true",
    "codex_call_count: 1",
    "codex_artifact_type: codex_task_transcript",
    "real_llm_status: not_used",
    "provider_status: not_used",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "model_tool_bridge_ok",
    "model_tool_name",
    "model_tool_result_status",
    "approval_pending_before_execution",
    "approval_ok",
    "codex_started_after_approval",
    "codex_call_count",
    "codex_artifact_ref",
    "codex_artifact_summary",
    "codex_artifact_type",
    "event_count",
    "event_types",
    "replay_ok",
    "checkpoint_ok",
    "model_status",
    "real_llm_status",
    "provider_status",
    "network_listener_status",
    "memory_status",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "prompt",
    "stdout",
    "stderr",
    "stdin",
}

FORBIDDEN_OUTPUT_TEXT = (
    "MODEL_BRIDGE_PROMPT_SHOULD_NOT_LEAK",
    "MODEL_BRIDGE_OUTPUT_SHOULD_NOT_LEAK",
    '"content"',
    "'content'",
)


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


def test_model_tool_bridge_plain_cli_prints_short_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_model_tool_bridge_json_cli_exposes_safe_status_without_raw_prompt_or_output():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["run_status"] == "completed"
    assert data["transport"] == "in_process"
    assert data["model_tool_bridge_ok"] is True
    assert data["model_tool_name"] == "codex_task"
    assert data["model_tool_result_status"] == "pending_user_approval"
    assert data["approval_pending_before_execution"] is True
    assert data["approval_ok"] is True
    assert data["codex_started_after_approval"] is True
    assert data["codex_call_count"] == 1
    assert data["codex_artifact_type"] == "codex_task_transcript"
    assert data["model_status"] == "deterministic_decision_only"
    assert data["real_llm_status"] == "not_used"
    assert data["provider_status"] == "not_used"
    assert data["memory_status"] == "boundary_only"
    _assert_no_forbidden_content_keys(data)
    rendered = json.dumps(data, sort_keys=True)
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in rendered


def test_model_tool_bridge_json_uses_structured_artifact_ref():
    data = _run_demo_json("--scenario", SCENARIO)
    ref = data["codex_artifact_ref"]

    assert ref["ref_type"] == "artifact"
    assert ref["scope"] == "run"
    assert ref["run_id"] == data["run_id"]
    assert ref["artifact_id"]
    assert data["codex_artifact_summary"] == "codex cli transcript captured"


def test_model_tool_bridge_trace_shows_model_to_approval_to_codex_path_without_raw_content():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: model-tool-bridge" in result.stdout
    assert "[1]" in result.stdout
    assert "model-facing tool catalog" in result.stdout
    assert "model selected codex_task" in result.stdout
    assert "pending approval" in result.stdout
    assert "approval resolved" in result.stdout
    assert "Codex CLI backend called after approval" in result.stdout
    assert "artifact" in result.stdout.lower()
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_model_tool_bridge_trace_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", SCENARIO, "--json")
    traced_json = _run_demo("--scenario", SCENARIO, "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout
