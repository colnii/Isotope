import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DEMO_SOURCE = SRC_ROOT / "isotope" / "demo.py"
ARTIFACT_REVIEW_SOURCE = SRC_ROOT / "isotope" / "demo_artifact_review_scenarios.py"
SCENARIO = "artifact-review"

REQUIRED_TEXT_FIELDS = (
    "scenario: artifact-review",
    "review_ok: true",
    "content_policy_ok: true",
    "controlled_retrieval_ok: true",
    "replay_ok: true",
    "checkpoint_ok: true",
    "http_full_content_route_status: not_enabled",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "review_ok",
    "artifact_ref",
    "review_artifact_ref",
    "content_policy_ok",
    "controlled_retrieval_ok",
    "replay_ok",
    "checkpoint_ok",
    "memory_status",
    "http_full_content_route_status",
    "filesystem_mutation_status",
    "model_status",
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


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_artifact_review_plain_cli_prints_short_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "artifact content:" not in result.stdout.lower()


def test_artifact_review_json_cli_exposes_required_status_fields():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["run_status"] == "completed"
    assert data["review_ok"] is True
    assert data["content_policy_ok"] is True
    assert data["controlled_retrieval_ok"] is True
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["memory_status"] == "boundary_only"


def test_artifact_review_json_uses_structured_refs_without_full_content():
    data = _run_demo_json("--scenario", SCENARIO)

    for field in ("artifact_ref", "review_artifact_ref"):
        ref = data[field]
        assert ref["ref_type"] == "artifact"
        assert ref["scope"] == "run"
        assert ref["run_id"] == data["run_id"]
        assert ref["artifact_id"]
    assert data["artifact_ref"] != data["review_artifact_ref"]
    _assert_no_forbidden_content_keys(data)


def test_artifact_review_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["http_full_content_route_status"] in {"not_enabled", "deferred"}
    assert data["filesystem_mutation_status"] == "not_used"
    assert data["model_status"] == "not_used"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("semantic_retrieval_status", "not_used") == "not_used"
    assert data.get("ranking_status", "not_used") == "not_used"


def test_artifact_review_demo_source_does_not_import_network_listener_dependencies():
    imports = _imported_modules(DEMO_SOURCE)

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imports
        for forbidden in FORBIDDEN_NETWORK_IMPORT_PREFIXES
    )


def test_artifact_review_demo_uses_artifact_record_helper_for_source_provenance():
    source = ARTIFACT_REVIEW_SOURCE.read_text(encoding="utf-8")
    function_source = ast.get_source_segment(
        source,
        next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "_run_artifact_review_spike"
        ),
    )

    assert function_source is not None
    assert "get_artifact_record(" in function_source
    assert "for event in reversed(app.server.get_events(run_id))" not in function_source
    assert "event.payload[\"artifact\"][\"ref\"] == source_artifact.ref.to_dict()" not in function_source
