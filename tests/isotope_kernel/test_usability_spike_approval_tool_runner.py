import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DEMO_SOURCE = SRC_ROOT / "isotope_kernel" / "demo.py"
SCENARIO = "approval-tool-runner"

REQUIRED_TEXT_FIELDS = (
    "scenario: approval-tool-runner",
    "run_status: completed",
    "transport: in_process",
    "approval_tool_runner_ok: true",
    "approval_pending_before_resume: true",
    "approval_ok: true",
    "workspace_binding_ok: true",
    "artifact_handoff_ok: true",
    "replay_ok: true",
    "checkpoint_ok: true",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "transport",
    "approval_tool_runner_ok",
    "approval_pending_before_resume",
    "approval_ok",
    "workspace_binding_ok",
    "artifact_handoff_ok",
    "replay_ok",
    "checkpoint_ok",
    "memory_status",
    "http_full_content_route_status",
    "filesystem_mutation_status",
    "model_status",
    "api_friction",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "workspace_file_content",
}

FORBIDDEN_NETWORK_IMPORT_PREFIXES = (
    "socket",
    "http.server",
    "http.client",
    "httpx",
    "requests",
    "urllib",
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


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_approval_tool_runner_plain_cli_prints_short_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "artifact content:" not in result.stdout.lower()


def test_approval_tool_runner_json_cli_exposes_required_status_fields():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["run_status"] == "completed"
    assert data["transport"] == "in_process"
    assert data["approval_tool_runner_ok"] is True
    assert data["approval_pending_before_resume"] is True
    assert data["approval_ok"] is True
    assert data["workspace_binding_ok"] is True
    assert data["artifact_handoff_ok"] is True
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["memory_status"] == "boundary_only"


def test_approval_tool_runner_keeps_forbidden_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["http_full_content_route_status"] in {"not_enabled", "deferred"}
    assert data["filesystem_mutation_status"] == "not_used"
    assert data["model_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"


def test_approval_tool_runner_json_does_not_expose_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_approval_tool_runner_records_api_friction_without_productizing_it():
    data = _run_demo_json("--scenario", SCENARIO)

    assert isinstance(data["api_friction"], list)
    assert data["api_friction"]
    serialized = json.dumps(data["api_friction"], sort_keys=True)
    assert "approval" in serialized or "workspace" in serialized


def test_approval_tool_runner_demo_source_does_not_import_network_listener_dependencies():
    imports = _imported_modules(DEMO_SOURCE)

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imports
        for forbidden in FORBIDDEN_NETWORK_IMPORT_PREFIXES
    )
