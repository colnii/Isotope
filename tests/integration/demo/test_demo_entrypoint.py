import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
DEMO_SOURCE = SRC_ROOT / "isotope" / "demo" / "__init__.py"

REQUIRED_TEXT_FIELDS = (
    "run_status",
    "artifact_ref",
    "replay_ok",
    "checkpoint_ok",
    "memory_status",
)

REQUIRED_JSON_FIELDS = {
    "session_id",
    "run_id",
    "run_status",
    "artifact_ref",
    "artifact_summary",
    "event_count",
    "replay_ok",
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

FORBIDDEN_IMPORT_PREFIXES = (
    "x_agent",
    "socket",
    "http",
    "httpx",
    "requests",
    "urllib",
    "openai",
    "anthropic",
    "google.generativeai",
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


def _run_demo_json() -> dict[str, Any]:
    result = _run_demo("--json")
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


def _directory_snapshot(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    return sorted(str(child.relative_to(path)) for child in path.rglob("*"))


def _imported_modules(path: Path) -> set[str]:
    assert path.exists(), "src/isotope/demo/__init__.py must exist"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_demo_plain_text_module_entrypoint_runs_successfully():
    result = _run_demo()

    assert result.returncode == 0, result.stderr


def test_demo_plain_text_output_contains_required_summary_fields():
    result = _run_demo()

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout


def test_demo_json_output_is_parseable():
    data = _run_demo_json()

    assert isinstance(data, dict)


def test_demo_json_output_contains_required_fields():
    data = _run_demo_json()

    assert REQUIRED_JSON_FIELDS.issubset(data)


def test_demo_json_output_does_not_expose_full_artifact_or_raw_content():
    data = _run_demo_json()

    _assert_no_forbidden_content_keys(data)


def test_demo_uses_temp_storage_without_repo_root_side_effect_dirs():
    watched_dirs = [REPO_ROOT / name for name in ("runs", "artifacts", "checkpoints")]
    before = {path: _directory_snapshot(path) for path in watched_dirs}

    result = _run_demo("--json")

    after = {path: _directory_snapshot(path) for path in watched_dirs}
    assert result.returncode == 0, result.stderr
    assert after == before


def test_demo_source_does_not_import_x_agent():
    imports = _imported_modules(DEMO_SOURCE)

    assert not any(module == "x_agent" or module.startswith("x_agent.") for module in imports)


def test_demo_source_does_not_import_network_or_real_llm_clients():
    imports = _imported_modules(DEMO_SOURCE)

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imports
        for forbidden in FORBIDDEN_IMPORT_PREFIXES
    )


def test_demo_memory_status_is_active():
    data = _run_demo_json()

    assert data["memory_status"] == "active"


def test_demo_replay_and_checkpoint_verification_are_backed_by_metadata(tmp_path):
    import isotope.demo as demo

    result = demo.run_demo(root_path=tmp_path)

    assert result["event_count"] >= 7
    assert result["replay_ok"] is True
    assert result["checkpoint_ok"] is True
    assert result["artifact_ref"]
    assert result["checkpoint_basis_event_id"]
    assert result["replay_run_status"] == result["run_status"]
    assert result["checkpoint_run_status"] == result["run_status"]
    assert result["checkpoint_artifact_ref"] == result["artifact_ref"]
    _assert_no_forbidden_content_keys(result)
