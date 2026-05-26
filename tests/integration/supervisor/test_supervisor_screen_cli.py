from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from isotope.workspace.artifacts import ArtifactStore


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.supervisor.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_supervisor_screen_report_proxies_screen_artifact_report_json(tmp_path):
    store = ArtifactStore(tmp_path)
    store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_control_plan",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 1,
                "executed": False,
                "planned_actions": ["restore_window"],
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("screen", "report", "--root", str(tmp_path), "--run-id", "run_001", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["run_id"] == "run_001"
    assert payload["summary"]["control_status"] == "planned"
    assert payload["summary"]["approval_required"] is True
    assert payload["summary"]["control_actions"][0]["action_types"] == ["restore_window"]


def test_supervisor_screen_report_plain_output_reuses_screen_plain_report(tmp_path):
    store = ArtifactStore(tmp_path)
    store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_control_plan",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 1,
                "executed": False,
                "planned_actions": ["restore_window"],
                "private_note": "raw control payload should not print",
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("screen", "report", "--root", str(tmp_path), "--run-id", "run_001")

    assert result.returncode == 0, result.stderr
    assert "control: planned" in result.stdout
    assert "approval: required" in result.stdout
    assert "action: restore_window count=1 executed=false" in result.stdout
    assert "raw control payload" not in result.stdout


def test_supervisor_screen_inspect_proxies_screen_artifact_json(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_metadata",
        summary="screen metadata captured",
        content=json.dumps({"target": {"app": "notepad.exe"}}, sort_keys=True),
    )

    result = _run_cli(
        "screen",
        "inspect",
        "--root",
        str(tmp_path),
        "--run-id",
        "run_001",
        "--artifact-id",
        artifact.artifact_id,
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["artifact"]["artifact_type"] == "screen_metadata"
    assert payload["artifact"]["ref"] == artifact.ref.to_dict()
    assert payload["content"]["target"]["app"] == "notepad.exe"
