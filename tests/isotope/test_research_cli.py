from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.research.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_research_cli_search_returns_json(tmp_path):
    result = _run_cli(
        "search",
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
    assert payload["research"]["provider"] == "fake"
    assert payload["research"]["sources"][0]["url"] == "https://example.com/isotope-research"
    assert len(payload["artifact_refs"]) == 2


def test_research_cli_requires_query(tmp_path):
    result = _run_cli("search", "--root", str(tmp_path), "--provider", "fake", "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "research_runner_error"
