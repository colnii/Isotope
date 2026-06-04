from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_KEYS = {
    "artifact_content",
    "content",
    "full_content",
    "full_text",
    "raw_artifact_content",
    "raw_content",
    "text",
}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.tasks.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _assert_public_metadata(value: Any) -> None:
    if isinstance(value, dict):
        assert FORBIDDEN_KEYS.isdisjoint(value)
        for nested in value.values():
            _assert_public_metadata(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_metadata(nested)


def test_task_cli_runs_one_task_as_json(tmp_path):
    result = _run_cli(
        "run",
        "--root",
        str(tmp_path),
        "--goal",
        "collect useful notes",
        "--message",
        "first note",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    task = payload["task"]
    assert task["task_id"].startswith("task_")
    assert task["goal"] == "collect useful notes"
    assert task["status"] == "completed"
    assert task["turn_count"] == 1
    assert task["result_ref"]["ref_type"] == "artifact"
    _assert_public_metadata(payload)


def test_task_cli_gets_and_lists_task_summaries_as_json(tmp_path):
    run_result = _run_cli(
        "run",
        "--root",
        str(tmp_path),
        "--goal",
        "collect useful notes",
        "--message",
        "first note",
        "--json",
    )

    assert run_result.returncode == 0, run_result.stderr
    task = json.loads(run_result.stdout)["task"]
    task_id = task["task_id"]

    get_result = _run_cli("get", "--root", str(tmp_path), "--task-id", task_id, "--json")
    list_result = _run_cli("list", "--root", str(tmp_path), "--json")

    assert get_result.returncode == 0, get_result.stderr
    assert json.loads(get_result.stdout) == {"status": "ok", "task": task}
    assert list_result.returncode == 0, list_result.stderr
    assert json.loads(list_result.stdout) == {"status": "ok", "tasks": [task]}
    _assert_public_metadata(json.loads(get_result.stdout))
    _assert_public_metadata(json.loads(list_result.stdout))


def test_task_cli_requires_message_for_run(tmp_path):
    result = _run_cli(
        "run",
        "--root",
        str(tmp_path),
        "--goal",
        "collect useful notes",
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "task_runner_error",
            "message": "run requires --message",
        },
    }


def test_task_cli_requires_task_id_for_get(tmp_path):
    result = _run_cli("get", "--root", str(tmp_path), "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "task_runner_error",
            "message": "get requires --task-id",
        },
    }
