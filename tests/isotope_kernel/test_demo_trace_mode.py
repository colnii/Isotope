import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

TRACE_SCENARIOS = (
    "artifact-review",
    "approval-tool-runner",
    "v0.2",
    "agent-loop-friction",
    "agent-loop-planner-friction",
    "agent-loop-planner-matrix",
    "agent-loop-planner-restart-pause",
    "agent-loop-planner-io-validator",
    "agent-loop-planner-validated-runner",
    "terminal-exec",
    "model-tool-bridge",
    "llm-provider-route",
    "llm-tool-result-loop",
    "llm-product-chat-app-entry",
    "llm-terminal-tool-loop",
)

COMMON_TRACE_TERMS = (
    "session",
    "run",
    "action",
    "policy",
    "artifact",
    "replay",
    "checkpoint",
)

FORBIDDEN_TRACE_TEXT = (
    "source artifact durable content",
    "review artifact durable content",
    "approval-gated tool output",
    "MODEL_BRIDGE_PROMPT_SHOULD_NOT_LEAK",
    "MODEL_BRIDGE_OUTPUT_SHOULD_NOT_LEAK",
    "LLM_PROVIDER_DEMO_MESSAGE_SHOULD_NOT_LEAK",
    "LLM_PROVIDER_DEMO_PROMPT_SHOULD_NOT_LEAK",
    "LLM_PROVIDER_DEMO_OUTPUT_SHOULD_NOT_LEAK",
    "LLM_TOOL_RESULT_DEMO_MESSAGE_SHOULD_NOT_LEAK",
    "LLM_TOOL_RESULT_FOLLOWUP_PROMPT_SHOULD_NOT_LEAK",
    "LLM_TOOL_RESULT_DEMO_OUTPUT_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_BLOCKED_MESSAGE_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_READY_MESSAGE_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_FINAL_ANSWER_SHOULD_NOT_LEAK",
    "APP_ENTRY_DEMO_STDOUT_SHOULD_NOT_LEAK",
    "TERMINAL_TOOL_LOOP_MESSAGE_SHOULD_NOT_LEAK",
    "TERMINAL_TOOL_LOOP_STDOUT_SHOULD_NOT_LEAK",
    "TERMINAL_TOOL_LOOP_FINAL_ANSWER_SHOULD_NOT_LEAK",
    "artifact content:",
    '"content"',
    "'content'",
)


def _run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope_kernel.demo", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _trace_output(scenario: str) -> str:
    result = _run_demo("--scenario", scenario, "--trace")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return result.stdout


def test_trace_mode_runs_for_artifact_review():
    output = _trace_output("artifact-review")

    assert "scenario: artifact-review" in output
    assert "[1]" in output
    assert "review artifact" in output


def test_trace_mode_runs_for_approval_tool_runner():
    output = _trace_output("approval-tool-runner")

    assert "scenario: approval-tool-runner" in output
    assert "[1]" in output
    assert "approval" in output


def test_trace_mode_runs_for_v0_2():
    output = _trace_output("v0.2")

    assert "scenario: v0.2" in output
    assert "[1]" in output
    assert "HTTP facade" in output


def test_trace_output_contains_key_runtime_steps_for_each_supported_scenario():
    for scenario in TRACE_SCENARIOS:
        output = _trace_output(scenario).lower()
        for term in COMMON_TRACE_TERMS:
            assert term in output, f"{scenario} trace missing {term}"


def test_trace_output_does_not_expose_artifact_full_content():
    for scenario in TRACE_SCENARIOS:
        output = _trace_output(scenario).lower()
        for forbidden in FORBIDDEN_TRACE_TEXT:
            assert forbidden not in output


def test_trace_mode_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", "artifact-review", "--json")
    traced_json = _run_demo("--scenario", "artifact-review", "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout


def test_invalid_scenario_with_trace_returns_controlled_failure():
    result = _run_demo("--scenario", "unknown", "--trace")

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    assert "Traceback" not in combined_output
    assert "invalid choice" in combined_output
