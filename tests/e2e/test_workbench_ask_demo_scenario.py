from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCENARIO = "workbench-ask"


def _run_demo(*extra_args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.demo", "--scenario", SCENARIO, *extra_args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_workbench_ask_demo_json_exposes_answer_without_raw_content():
    result = _run_demo("--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["scenario"] == SCENARIO
    assert payload["transport"] == "in_process_http_facade"
    assert payload["answer"] == "建议先把作品集项目拆成一个可展示任务。"
    assert payload["provider"] == "deterministic_test"
    assert payload["post_workbench_ask_status_code"] == 200
    assert payload["context_counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    assert "PRIVATE_WORKBENCH_ASK_CONTENT_SHOULD_NOT_LEAK" not in result.stdout


def test_workbench_ask_demo_trace_is_human_readable():
    result = _run_demo("--trace")

    assert result.returncode == 0, result.stderr
    assert "scenario: workbench-ask" in result.stdout
    assert "question: 秋招作品集下一步做什么？" in result.stdout
    assert "answer: 建议先把作品集项目拆成一个可展示任务。" in result.stdout
    assert "context: projects=1 tasks=1 files=1 search_results=3" in result.stdout
