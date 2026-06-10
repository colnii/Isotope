from __future__ import annotations

import subprocess
from typing import Any

from isotope.features.supervisor.registry import ManagedCodexRecord
from isotope.features.supervisor.workers.integration_review import (
    review_managed_record_integration,
)


def test_self_repair_worker_requires_review_before_integration(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    log_path = tmp_path / "worker.log"
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: 修复完成",
                "SUPERVISOR_NEXT: 等待集成",
            ]
        ),
        encoding="utf-8",
    )
    record = ManagedCodexRecord(
        record_id="self-repair-1",
        name="desktop-self-repair",
        cwd=str(repo),
        prompt="repair manifest/observation boundary",
        command=("codex",),
        pid=1234,
        started_at="2026-06-11T00:00:00+00:00",
        log_path=str(log_path),
        worker_role="self_repair",
    )

    review = review_managed_record_integration(
        record,
        base_ref="main",
        run_test_gate=False,
        run_candidate_validation=True,
        run=_fake_ready_git,
        validation_run=None,
    )

    assert review["group"] == "needs_review"
    assert "self-repair" in review["reason"]
    assert "人工复查" in review["reason"]
    assert review["worker_role"] == "self_repair"


def _fake_ready_git(
    command: list[str],
    *_args: Any,
    **_kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    args = _git_args(command)
    if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
        return _completed(command, stdout="supervisor/desktop-self-repair-test\n")
    if args == ["rev-parse", "HEAD"]:
        return _completed(command, stdout="workercommit\n")
    if args == ["rev-parse", "main"]:
        return _completed(command, stdout="maincommit\n")
    if args == ["rev-parse", "main^{tree}"]:
        return _completed(command, stdout="maintree\n")
    if args == ["status", "--short"]:
        return _completed(command, stdout="")
    if args == ["merge-base", "--is-ancestor", "workercommit", "main"]:
        return _completed(command, returncode=1)
    if args == ["merge-base", "--is-ancestor", "main", "workercommit"]:
        return _completed(command)
    if args == ["merge-tree", "--write-tree", "main", "workercommit"]:
        return _completed(command, stdout="mergedtree\n")
    if args == ["cherry", "main", "workercommit"]:
        return _completed(command, stdout="+ workercommit subject\n")
    raise AssertionError(f"unexpected git command: {command!r}")


def _git_args(command: list[str]) -> list[str]:
    return command[3:] if command[:2] == ["git", "-C"] else command


def _completed(
    command: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
