import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from isotope.interfaces.http import create_http_app
from isotope.runtime.in_process import InProcessServer


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
DEMO_SOURCE = SRC_ROOT / "isotope" / "demo.py"
SCENARIO = "external-snapshot-review"

REQUIRED_TEXT_FIELDS = (
    "scenario: external-snapshot-review",
    "snapshot_imported_ok: true",
    "external_observation_count:",
    "conflict_diagnostics_count:",
    "native_state_preserved: true",
    "replay_ok: true",
    "checkpoint_ok: true",
    "provider_status: boundary_only",
    "memory_status: boundary_only",
)

REQUIRED_JSON_FIELDS = {
    "scenario",
    "run_status",
    "snapshot_imported_ok",
    "external_observation_count",
    "conflict_diagnostics_count",
    "native_state_preserved",
    "replay_ok",
    "checkpoint_ok",
    "provider_status",
    "http_external_ingestion_route_status",
    "memory_status",
}

FORBIDDEN_CONTENT_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "provider_body",
    "raw_artifact_content",
    "raw_content",
    "raw_external_content",
    "raw_provider_body",
}

FORBIDDEN_NETWORK_IMPORT_PREFIXES = (
    "fastapi",
    "flask",
    "http.client",
    "http.server",
    "httpx",
    "requests",
    "socket",
    "urllib",
    "uvicorn",
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


def test_external_snapshot_review_plain_cli_prints_boundary_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    for field in REQUIRED_TEXT_FIELDS:
        assert field in result.stdout
    assert "raw external content" not in result.stdout.lower()
    assert "full artifact content" not in result.stdout.lower()


def test_external_snapshot_review_json_cli_exposes_required_status_fields():
    data = _run_demo_json("--scenario", SCENARIO)

    assert REQUIRED_JSON_FIELDS.issubset(data)
    assert data["scenario"] == SCENARIO
    assert data["snapshot_imported_ok"] is True
    assert data["external_observation_count"] >= 2
    assert data["conflict_diagnostics_count"] >= 1
    assert data["native_state_preserved"] is True
    assert data["replay_ok"] is True
    assert data["checkpoint_ok"] is True
    assert data["provider_status"] == "boundary_only"
    assert data["http_external_ingestion_route_status"] == "not_enabled"
    assert data["memory_status"] == "boundary_only"


def test_external_snapshot_review_json_excludes_raw_external_and_full_artifact_content():
    data = _run_demo_json("--scenario", SCENARIO)

    _assert_no_forbidden_content_keys(data)


def test_external_snapshot_review_trace_shows_steps_without_raw_content():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: external-snapshot-review" in result.stdout
    assert "snapshot.imported" in result.stdout
    assert "conflict diagnostics" in result.stdout
    assert "native state preserved" in result.stdout
    assert "raw external content" not in result.stdout.lower()
    assert "full artifact content" not in result.stdout.lower()


def test_external_snapshot_review_keeps_deferred_integrations_disabled():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["provider_status"] == "boundary_only"
    assert data["http_external_ingestion_route_status"] == "not_enabled"
    assert data.get("network_listener_status", "not_used") == "not_used"
    assert data.get("model_status", "not_used") == "not_used"
    assert data.get("memory_query_status", "not_enabled") == "not_enabled"
    assert data.get("memory_storage_status", "not_enabled") == "not_enabled"


def test_external_snapshot_review_demo_source_does_not_import_provider_or_network_listener_dependencies():
    imports = _imported_modules(DEMO_SOURCE)

    assert not any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for module in imports
        for forbidden in FORBIDDEN_NETWORK_IMPORT_PREFIXES
    )


def test_http_external_ingestion_route_remains_not_enabled(tmp_path):
    app = create_http_app(tmp_path)

    response = app.request("POST", "/external-ingestion", json={"source_system": "example_provider"})

    assert response.status_code == 501
    assert response.json()["status"] == "not_enabled"
    assert response.json()["error"]["capability"] == "external_ingestion"


def test_server_external_ingestion_public_api_remains_not_enabled(tmp_path):
    server = InProcessServer(tmp_path)

    result = server.ingest_external_input({"source_system": "example_provider"})

    assert result["status"] == "not_enabled"
    assert result["capability"] == "external_ingestion"
    assert result["error"]["code"] == "not_enabled"
