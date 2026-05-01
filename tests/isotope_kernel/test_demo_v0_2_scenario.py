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

V0_1_REQUIRED_TEXT_FIELDS = (
    "run_status",
    "artifact_ref",
    "replay_ok",
    "checkpoint_ok",
    "memory_status",
)

V0_2_REQUIRED_TEXT_FIELDS = (
    "scenario: v0.2",
    "http_api_ok",
    "approval_ok",
    "artifact_content_policy_ok",
    "checkpoint_ok",
    "memory_status: boundary_only",
)

V0_2_REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "http_api_ok",
    "approval_ok",
    "artifact_content_policy_ok",
    "checkpoint_ok",
    "memory_status",
}

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
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


def test_default_v0_1_plain_demo_remains_compatible():
    result = _run_demo()

    assert result.returncode == 0, result.stderr
    for field in V0_1_REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "scenario: v0.2" not in result.stdout


def test_default_v0_1_json_demo_remains_compatible():
    result = _run_demo("--json")

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["run_status"] == "completed"
    assert data["checkpoint_ok"] is True
    assert data["memory_status"] == "boundary_only"
    assert "scenario" not in data
    _assert_no_forbidden_content_keys(data)


def test_v0_2_plain_scenario_runs_and_prints_boundary_summary():
    result = _run_demo("--scenario", "v0.2")

    assert result.returncode == 0, result.stderr
    for field in V0_2_REQUIRED_TEXT_FIELDS:
        assert field in result.stdout


def test_v0_2_json_scenario_is_parseable_and_contains_required_fields():
    data = _run_demo_json("--scenario", "v0.2")

    assert V0_2_REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == "v0.2"
    assert data["run_status"] == "completed"
    assert data["http_api_ok"] is True
    assert data["approval_ok"] is True
    assert data["artifact_content_policy_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["memory_status"] == "boundary_only"


def test_v0_2_json_scenario_does_not_expose_full_artifact_content():
    data = _run_demo_json("--scenario", "v0.2")

    _assert_no_forbidden_content_keys(data)


def test_v0_2_scenario_keeps_http_full_content_route_deferred():
    data = _run_demo_json("--scenario", "v0.2")

    assert data["http_full_content_route_status"] in {"not_enabled", "deferred"}
    assert data.get("http_full_content_route_status") != "supported"


def test_v0_2_scenario_keeps_memory_boundary_only():
    data = _run_demo_json("--scenario", "v0.2")

    assert data["memory_status"] == "boundary_only"
    assert data.get("memory_query_status", "not_enabled") in {"not_enabled", "absent"}
    assert data.get("memory_storage_status", "not_enabled") in {"not_enabled", "absent"}


def test_demo_source_does_not_import_network_listener_dependencies():
    imports = _imported_modules(DEMO_SOURCE)

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imports
        for forbidden in FORBIDDEN_NETWORK_IMPORT_PREFIXES
    )


def test_invalid_scenario_returns_controlled_nonzero_error():
    result = _run_demo("--scenario", "unknown")

    assert result.returncode != 0
    combined_output = result.stdout + result.stderr
    assert "Traceback" not in combined_output
    assert "<" not in combined_output
    assert "object at 0x" not in combined_output
