import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "llm-provider-route"

REQUIRED_TEXT_FIELDS = (
    "scenario: llm-provider-route",
    "transport: in_process",
    "provider_route_ok: true",
    "provider_name: deepseek",
    "provider_model: deepseek-v4-flash",
    "provider_tool_name: codex_task",
    "provider_call_count: 1",
    "route_result_status: pending_user_approval",
    "approval_pending_before_execution: true",
    "codex_started_before_approval: false",
    "codex_call_count: 0",
    "idempotency_replay_ok: true",
    "real_llm_status: fake_provider",
    "network_listener_status: not_used",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "provider_route_ok",
    "provider_name",
    "provider_model",
    "provider_tool_name",
    "provider_call_count",
    "route_result_status",
    "approval_pending_before_execution",
    "codex_started_before_approval",
    "codex_call_count",
    "idempotency_replay_ok",
    "event_count",
    "event_types",
    "replay_ok",
    "checkpoint_ok",
    "real_llm_status",
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
    "messages",
    "stdout",
    "stderr",
    "stdin",
}

FORBIDDEN_OUTPUT_TEXT = (
    "LLM_PROVIDER_DEMO_MESSAGE_SHOULD_NOT_LEAK",
    "LLM_PROVIDER_DEMO_PROMPT_SHOULD_NOT_LEAK",
    "LLM_PROVIDER_DEMO_OUTPUT_SHOULD_NOT_LEAK",
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


def test_llm_provider_route_demo_plain_cli_prints_short_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_provider_route_demo_json_exposes_safe_status_without_raw_prompt_or_messages():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["transport"] == "in_process"
    assert data["provider_route_ok"] is True
    assert data["provider_name"] == "deepseek"
    assert data["provider_model"] == "deepseek-v4-flash"
    assert data["provider_tool_name"] == "codex_task"
    assert data["provider_call_count"] == 1
    assert data["route_result_status"] == "pending_user_approval"
    assert data["approval_pending_before_execution"] is True
    assert data["codex_started_before_approval"] is False
    assert data["codex_call_count"] == 0
    assert data["idempotency_replay_ok"] is True
    assert data["real_llm_status"] == "fake_provider"
    assert data["network_listener_status"] == "not_used"
    assert data["memory_status"] == "boundary_only"
    assert "approval.requested" in data["event_types"]
    assert "action.started" not in data["event_types"]
    assert "artifact.created" not in data["event_types"]
    _assert_no_forbidden_content_keys(data)
    rendered = json.dumps(data, sort_keys=True)
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in rendered


def test_llm_provider_route_demo_trace_shows_provider_to_approval_pause_without_raw_content():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: llm-provider-route" in result.stdout
    assert "[1]" in result.stdout
    assert "provider route" in result.stdout
    assert "codex_task" in result.stdout
    assert "pending approval" in result.stdout
    assert "Codex remains paused" in result.stdout
    assert "no artifact before approval" in result.stdout
    for forbidden in FORBIDDEN_OUTPUT_TEXT:
        assert forbidden not in result.stdout


def test_llm_provider_route_demo_trace_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", SCENARIO, "--json")
    traced_json = _run_demo("--scenario", SCENARIO, "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout
