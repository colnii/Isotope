from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from isotope.features.files.flow import FileFlow
from isotope.features.projects.flow import ProjectFlow
from isotope.features.tasks.flow import TaskFlow


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.ask.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_workbench_ask_cli_outputs_json_answer(tmp_path):
    ProjectFlow.in_process(tmp_path).create_project(
        name="portfolio demo",
        summary="autumn recruiting workspace",
    )
    TaskFlow.in_process(tmp_path).create_task(
        goal="build portfolio story",
        first_message="private note",
    )
    FileFlow.in_process(tmp_path).create_text_file(
        name="portfolio.md",
        summary="portfolio notes",
        content="PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK",
    )

    result = _run_cli(
        "ask",
        "--root",
        str(tmp_path),
        "--question",
        "下一步做什么？",
        "--mock-answer",
        "先整理作品集故事线。",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["answer"]["answer"] == "先整理作品集故事线。"
    assert payload["answer"]["provider"] == "mock"
    assert payload["answer"]["context"]["counts"] == {
        "projects": 1,
        "tasks": 1,
        "files": 1,
        "search_results": 3,
    }
    _assert_no_private_content(payload)


def test_workbench_ask_cli_plain_output_is_short(tmp_path):
    result = _run_cli(
        "ask",
        "--root",
        str(tmp_path),
        "--question",
        "有什么内容？",
        "--mock-answer",
        "当前工作台为空。",
    )

    assert result.returncode == 0, result.stderr
    assert "answer: 当前工作台为空。" in result.stdout
    assert "provider: mock/mock-workbench-ask" in result.stdout
    assert "context: projects=0 tasks=0 files=0 search_results=0" in result.stdout


def _assert_no_private_content(value: Any) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_private_content(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_private_content(nested)
    elif isinstance(value, str):
        assert "PRIVATE_FILE_CONTENT_SHOULD_NOT_LEAK" not in value
