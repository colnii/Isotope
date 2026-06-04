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
        [sys.executable, "-m", "isotope.features.files.runner", *args],
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


def test_file_cli_creates_gets_and_lists_file_summaries_as_json(tmp_path):
    created_result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--name",
        "notes.md",
        "--summary",
        "useful notes",
        "--content",
        "private durable file content",
        "--json",
    )

    assert created_result.returncode == 0, created_result.stderr
    created_payload = json.loads(created_result.stdout)
    file_summary = created_payload["file"]
    file_id = file_summary["file_id"]

    get_result = _run_cli("get", "--root", str(tmp_path), "--file-id", file_id, "--json")
    list_result = _run_cli("list", "--root", str(tmp_path), "--json")

    assert created_payload["status"] == "ok"
    assert file_id.startswith("artifact_")
    assert file_summary["name"] == "notes.md"
    assert file_summary["summary"] == "useful notes"
    assert file_summary["artifact_ref"]["ref_type"] == "artifact"
    assert get_result.returncode == 0, get_result.stderr
    assert json.loads(get_result.stdout) == {"status": "ok", "file": file_summary}
    assert list_result.returncode == 0, list_result.stderr
    assert json.loads(list_result.stdout) == {"status": "ok", "files": [file_summary]}
    _assert_public_metadata(created_payload)
    _assert_public_metadata(json.loads(get_result.stdout))
    _assert_public_metadata(json.loads(list_result.stdout))


def test_file_cli_requires_content_for_create(tmp_path):
    result = _run_cli(
        "create",
        "--root",
        str(tmp_path),
        "--name",
        "notes.md",
        "--summary",
        "useful notes",
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "file_runner_error",
            "message": "create requires --content",
        },
    }
