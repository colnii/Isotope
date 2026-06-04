from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "memory-query-smoke"

FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
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


def test_memory_query_smoke_plain_cli_shows_write_query_recall_closure():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    assert "scenario: memory-query-smoke" in result.stdout
    assert "memory_write_status: saved" in result.stdout
    assert "memory_query_status: ok" in result.stdout
    assert "query_result_count: 1" in result.stdout
    assert "recalled_record_id: mem_demo_query" in result.stdout
    assert "content_policy: memory_record_refs_expandable" in result.stdout
    assert "raw memory" not in result.stdout


def test_memory_query_smoke_json_reports_public_metadata_recall():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["scenario"] == SCENARIO
    assert data["memory_query_smoke_ok"] is True
    assert data["memory_write_status"] == "saved"
    assert data["memory_query_status"] == "ok"
    assert data["query_result_count"] == 1
    assert data["recalled_record"]["record_id"] == "mem_demo_query"
    assert data["recalled_record"]["source_refs"] == [
        {"ref_type": "artifact", "artifact_id": "artifact_demo_query"}
    ]
    assert data["recalled_record"]["provenance"]["run_id"] == "run_demo_query"
    assert data["content_policy"] == "memory_record_refs_expandable"
    _assert_no_forbidden_content_keys(data)
    assert "raw memory" not in json.dumps(data)
