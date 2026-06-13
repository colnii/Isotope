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
        [sys.executable, "-m", "isotope.features.screen.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_screen_cli_report_summarizes_control_result_action_types(tmp_path):
    store = ArtifactStore(tmp_path)
    result_artifact = store.create_artifact(
        "run_001",
        execution_id="exec_001",
        artifact_type="screen_control_result",
        summary="screen control result",
        content=json.dumps(
            {
                "action_count": 2,
                "applied_count": 2,
                "executed": True,
                "action_types": ["key_press", "drag"],
            },
            sort_keys=True,
        ),
    )

    result = _run_cli("report", "--root", str(tmp_path), "--run-id", "run_001", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["control_status"] == "completed"
    assert payload["summary"]["control_plan_count"] == 0
    assert payload["summary"]["control_result_count"] == 1
    assert payload["summary"]["approval_required"] is False
    assert payload["summary"]["interferes_with_screen"] is True
    assert payload["summary"]["control_actions"] == [
        {
            "artifact_id": result_artifact.artifact_id,
            "action_count": 2,
            "executed": True,
            "action_types": ["key_press", "drag"],
        }
    ]
