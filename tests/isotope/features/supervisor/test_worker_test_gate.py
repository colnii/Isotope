from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from isotope.features.supervisor.integration_review import collect_integration_reviews
from isotope.features.supervisor.worker_review import (
    collect_worker_reviews,
    render_worker_review_plain,
)


def test_worker_review_marks_done_worker_test_passed(tmp_path):
    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "pass-12345678"
    cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-pass", name="pass", cwd=cwd)

    payload = collect_worker_reviews(
        codex_home=codex_home,
        run=_fake_worker_review_run(
            cwd,
            pytest_result=(0, "12 passed in 0.34s\n", ""),
        ),
        process_checker=lambda pid: False,
    )

    worker = payload["workers"][0]
    assert worker["test_status"] == "passed"
    assert worker["test_passed"] is True
    assert worker["test_exit_code"] == 0
    assert "12 passed" in worker["test_output_tail"]
    assert payload["automation_candidates"]["review_then_merge"][0]["test_passed"] is True
    assert (
        "12 passed"
        in payload["automation_candidates"]["review_then_merge"][0]["test_output_tail"]
    )
    assert "测试门控：passed / passed=True / exit_code=0" in render_worker_review_plain(
        payload
    )


def test_done_worker_gate_falls_back_to_current_python_when_worktree_venv_missing(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "pass-12345678"
    cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-pass", name="pass", cwd=cwd)
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs):
        commands.append(command)
        _assert_completed_process_kwargs(kwargs)
        if command == [sys.executable, "-m", "pytest", "tests/isotope", "-q"]:
            assert Path(kwargs["cwd"]) == cwd
            assert kwargs["env"]["PYTHONPATH"] == "src"
            return subprocess.CompletedProcess(command, 0, "12 passed\n", "")
        if command[:3] == ["git", "-C", str(cwd)]:
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command}")

    payload = collect_worker_reviews(
        codex_home=codex_home,
        run=fake_run,
        process_checker=lambda pid: False,
    )

    assert payload["workers"][0]["test_passed"] is True
    assert [sys.executable, "-m", "pytest", "tests/isotope", "-q"] in commands


def test_failed_done_worker_gate_moves_integration_review_to_needs_review(tmp_path):
    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "fail-12345678"
    cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-fail", name="fail", cwd=cwd)
    fake_run = _fake_integration_run(
        cwd,
        worker_commit="fail111",
        pytest_result=(1, "FAILED tests/isotope/test_gate.py::test_x\n", ""),
    )

    worker_payload = collect_worker_reviews(
        codex_home=codex_home,
        run=_fake_worker_review_run(
            cwd,
            pytest_result=(1, "FAILED tests/isotope/test_gate.py::test_x\n", ""),
        ),
        process_checker=lambda pid: False,
    )
    assert worker_payload["workers"][0]["test_passed"] is False

    integration_payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert integration_payload["summary"]["ready_to_integrate"] == 0
    assert integration_payload["summary"]["needs_review"] == 1
    item = integration_payload["groups"]["needs_review"][0]
    assert item["record_id"] == "managed-fail"
    assert item["test_passed"] is False
    assert item["test_exit_code"] == 1
    assert "pytest failed" in item["reason"]
    assert "FAILED tests/isotope/test_gate.py::test_x" in item["test_output_tail"]


def test_worker_review_marks_deleted_worktree_test_skipped(tmp_path):
    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "gone-12345678"
    _write_done_record(codex_home, record_id="managed-gone", name="gone", cwd=cwd)

    payload = collect_worker_reviews(
        codex_home=codex_home,
        process_checker=lambda pid: False,
    )

    worker = payload["workers"][0]
    assert worker["cwd_exists"] is False
    assert worker["test_status"] == "skipped"
    assert worker["test_passed"] is None
    assert worker["test_exit_code"] is None
    assert "cwd/worktree 缺失" in worker["test_output_tail"]
    assert payload["automation_candidates"]["recover_or_archive"][0]["test_status"] == "skipped"


def _fake_worker_review_run(
    cwd: Path,
    *,
    pytest_result: tuple[int, str, str],
):
    def fake_run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        _assert_completed_process_kwargs(kwargs)
        if _is_pytest_gate_command(command):
            assert Path(kwargs["cwd"]) == cwd
            assert kwargs["env"]["PYTHONPATH"] == "src"
            return subprocess.CompletedProcess(command, *pytest_result)
        if command[:3] == ["git", "-C", str(cwd)]:
            args = tuple(command[3:])
            if args == ("rev-parse", "--show-toplevel"):
                return subprocess.CompletedProcess(command, 0, str(cwd) + "\n", "")
            if args == ("rev-parse", "--abbrev-ref", "HEAD"):
                return subprocess.CompletedProcess(command, 0, "supervisor/pass-12345678\n", "")
            if args == ("status", "--short"):
                return subprocess.CompletedProcess(command, 0, " M src/example.py\n", "")
            if args == ("diff", "--stat"):
                return subprocess.CompletedProcess(command, 0, " src/example.py | 1 +\n", "")
        raise AssertionError(f"unexpected command: {command}")

    return fake_run


def _fake_integration_run(
    cwd: Path,
    *,
    worker_commit: str,
    pytest_result: tuple[int, str, str],
):
    def fake_run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        _assert_completed_process_kwargs(kwargs)
        if _is_pytest_gate_command(command):
            assert Path(kwargs["cwd"]) == cwd
            assert kwargs["env"]["PYTHONPATH"] == "src"
            return subprocess.CompletedProcess(command, *pytest_result)
        if command[:3] == ["git", "-C", str(cwd)]:
            args = tuple(command[3:])
            responses = {
                ("rev-parse", "--abbrev-ref", "HEAD"): (
                    0,
                    "supervisor/fail-12345678\n",
                    "",
                ),
                ("rev-parse", "HEAD"): (0, worker_commit + "\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("rev-parse", "main^{tree}"): (0, "tree-ok\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", worker_commit, "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", worker_commit): (0, "", ""),
                ("cherry", "main", worker_commit): (0, "+ " + worker_commit + "\n", ""),
                ("merge-tree", "--write-tree", "main", worker_commit): (
                    0,
                    "tree-ok\n",
                    "",
                ),
            }
            try:
                return subprocess.CompletedProcess(command, *responses[args])
            except KeyError as exc:
                raise AssertionError(f"unexpected command: {command}") from exc
        raise AssertionError(f"unexpected command: {command}")

    return fake_run


def _assert_completed_process_kwargs(kwargs: dict[str, object]) -> None:
    assert kwargs["check"] is False
    assert kwargs["text"] is True
    assert kwargs["capture_output"] is True


def _is_pytest_gate_command(command: list[str]) -> bool:
    return (
        command[1:] == ["-m", "pytest", "tests/isotope", "-q"]
        and command[0] in {".venv/bin/python", sys.executable}
    )


def _write_done_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
) -> None:
    log_path = codex_home / "supervisor" / "logs" / f"{record_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                f"SUPERVISOR_SUMMARY: {name} summary",
                "SUPERVISOR_NEXT: 等待 Supervisor 归档",
            ]
        ),
        encoding="utf-8",
    )
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "record_id": record_id,
                    "name": name,
                    "cwd": str(cwd),
                    "prompt": f"review {name}",
                    "command": ["codex", "exec", "-C", str(cwd), "prompt"],
                    "pid": 0,
                    "started_at": "2026-05-20T12:00:00+00:00",
                    "log_path": str(log_path),
                    "status": "launched",
                    "backend": "process",
                    "tmux_session": None,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
