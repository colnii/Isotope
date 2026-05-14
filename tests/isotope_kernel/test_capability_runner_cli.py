from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

FORBIDDEN_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "trace",
    "transcript",
}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope_kernel.capability_runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _assert_low_sensitive(value: Any) -> None:
    for mapping in _walk(value):
        assert FORBIDDEN_KEYS.isdisjoint(mapping)


def test_capability_runner_cli_lists_capabilities_as_json():
    result = _run_cli("list", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    capability_ids = [item["capability_id"] for item in payload["capabilities"]]
    assert capability_ids == [
        "approval.tool.runner",
        "artifact.review",
        "external.snapshot.review",
    ]
    _assert_low_sensitive(payload)


def test_capability_runner_cli_describes_capability_as_json():
    result = _run_cli("describe", "artifact.review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["capability"]["capability_id"] == "artifact.review"
    assert payload["capability"]["shelf"] == "product_candidate"
    _assert_low_sensitive(payload)


def test_capability_runner_cli_reports_status_as_json():
    result = _run_cli("status", "external.snapshot.review", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["capability_status"]["capability_id"] == "external.snapshot.review"
    assert payload["capability_status"]["ready"] is True
    assert payload["capability_status"]["status"] == "ready"
    _assert_low_sensitive(payload)


def test_capability_runner_cli_runs_allowlisted_capability_as_json(tmp_path):
    result = _run_cli("run", "artifact.review", "--root", str(tmp_path), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    run = payload["run"]
    assert run["capability_id"] == "artifact.review"
    assert run["status"] == "completed"
    assert run["scenario"] == "artifact-review"
    assert run["replay_ok"] is True
    assert run["checkpoint_ok"] is True
    _assert_low_sensitive(payload)


def test_capability_runner_cli_unknown_capability_fails_controlled_json(tmp_path):
    result = _run_cli("run", "unknown.capability", "--root", str(tmp_path), "--json")

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "error",
        "error": {
            "code": "capability_runner_error",
            "message": "unknown capability: unknown.capability",
        },
    }
    assert not list(tmp_path.rglob("*"))
