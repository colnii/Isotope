from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


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


def test_supervisor_research_command_proxies_research_flow(tmp_path):
    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["research"]["query"] == "agent memory retrieval"
    assert payload["research"]["provider"] == "fake"
    assert [artifact["artifact_type"] for artifact in payload["artifacts"]] == [
        "research.raw_transcript",
        "research.report",
    ]


def test_supervisor_research_plain_output_lists_artifacts(tmp_path):
    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
    )

    assert result.returncode == 0, result.stderr
    assert "[Codex Supervisor Research]" in result.stdout
    assert "artifact: research.raw_transcript artifact_001" in result.stdout
    assert "artifact: research.report artifact_002" in result.stdout
