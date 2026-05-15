from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "workbench"

FORBIDDEN_CONTENT_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
    "text",
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
        assert FORBIDDEN_CONTENT_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def test_workbench_demo_plain_cli_prints_home_summary():
    result = _run_demo("--scenario", SCENARIO)

    assert result.returncode == 0, result.stderr
    assert "scenario: workbench" in result.stdout
    assert "workbench_ok: true" in result.stdout
    assert "project_count: 1" in result.stdout
    assert "task_count: 1" in result.stdout
    assert "file_count: 1" in result.stdout
    assert "search_result_count: 1" in result.stdout


def test_workbench_demo_json_exposes_low_sensitive_home_view_only():
    data = _run_demo_json("--scenario", SCENARIO)

    assert data["scenario"] == SCENARIO
    assert data["workbench_ok"] is True
    assert data["project_count"] == 1
    assert data["task_count"] == 1
    assert data["file_count"] == 1
    assert data["search_result_count"] == 1
    assert data["search_result_types"] == ["task"]
    assert data["workbench_counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 1,
    }
    _assert_no_forbidden_content_keys(data)


def test_workbench_demo_trace_shows_product_flow_without_raw_content():
    result = _run_demo("--scenario", SCENARIO, "--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: workbench" in result.stdout
    assert "[1]" in result.stdout
    assert "创建 project/task/file 摘要" in result.stdout
    assert "POST /workbench" in result.stdout
    assert "search_results=1" in result.stdout
    assert "private task note" not in result.stdout
    assert "private file content" not in result.stdout


def test_workbench_demo_trace_does_not_change_json_output_contract():
    plain_json = _run_demo("--scenario", SCENARIO, "--json")
    traced_json = _run_demo("--scenario", SCENARIO, "--trace", "--json")

    assert plain_json.returncode == 0, plain_json.stderr
    assert traced_json.returncode == 0, traced_json.stderr
    assert json.loads(traced_json.stdout) == json.loads(plain_json.stdout)
    assert "[1]" not in traced_json.stdout
