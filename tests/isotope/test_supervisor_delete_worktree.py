from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from isotope.features.supervisor.flow import CodexSupervisorReport
from isotope.features.supervisor.llm_summary import generate_llm_action_decision
from isotope.features.supervisor.runner import (
    _delete_worktree_candidate_payloads,
    _execute_llm_action,
)


NOW = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_llm_delete_worktree_requires_explicit_confirmation():
    class FakeProvider:
        def summarize(self, messages: list[dict[str, str]]) -> str:
            return json.dumps(
                {
                    "kind": "delete_worktree",
                    "target_name": "done-worker",
                    "record_id": "managed-done",
                    "reason": "worker 已合并且可清理。",
                },
                ensure_ascii=False,
            )

    with pytest.raises(ValueError, match="confirm_delete_worktree=true"):
        generate_llm_action_decision(
            _empty_report(),
            [],
            FakeProvider(),
            delete_worktree_candidates=[
                {
                    "name": "done-worker",
                    "record_id": "managed-done",
                    "cwd": "/repo/.worktrees/supervisor/done-worker-12345678",
                    "integration_group": "already_integrated",
                    "archived": True,
                }
            ],
        )


def test_execute_delete_worktree_removes_archived_integrated_supervisor_worktree(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    worktree = repo_root / ".worktrees" / "supervisor" / "done-worker-12345678"
    worktree.mkdir(parents=True)
    _write_managed_record_event(
        codex_home,
        record_id="managed-done",
        name="done-worker",
        cwd=worktree,
        record_status="launched",
        protocol_status="done",
    )
    _write_managed_record_event(
        codex_home,
        record_id="managed-done",
        name="done-worker",
        cwd=worktree,
        record_status="archived",
        protocol_status="done",
    )
    run_calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        run_calls.append(command)
        check = kwargs.get("check", False)
        text = kwargs.get("text", False)
        capture_output = kwargs.get("capture_output", False)
        assert check is False
        assert text is True
        assert capture_output is True
        if _is_pytest_gate_command(command):
            assert Path(kwargs["cwd"]) == worktree
            env = kwargs["env"]
            assert isinstance(env, dict)
            assert env["PYTHONPATH"] == "src"
            return subprocess.CompletedProcess(command, 0, "12 passed in 0.34s\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "supervisor/done-worker-12345678\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "done111\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "main"]:
            return subprocess.CompletedProcess(command, 0, "main999\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "main^{tree}"]:
            return subprocess.CompletedProcess(command, 0, "tree-ok\n", "")
        if command == ["git", "-C", str(worktree), "status", "--short"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == ["git", "-C", str(worktree), "merge-base", "--is-ancestor", "done111", "main"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == ["git", "-C", str(worktree), "merge-base", "--is-ancestor", "main", "done111"]:
            return subprocess.CompletedProcess(command, 1, "", "")
        if command == ["git", "-C", str(worktree), "merge-tree", "--write-tree", "main", "done111"]:
            return subprocess.CompletedProcess(command, 0, "tree-ok\n", "")
        if command == ["git", "-C", str(repo_root), "worktree", "remove", str(worktree)]:
            shutil.rmtree(worktree)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "supervisor/done-worker-12345678@{upstream}",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                "origin/supervisor/done-worker-12345678\n",
                "",
            )
        if command == [
            "git",
            "-C",
            str(repo_root),
            "merge-base",
            "--is-ancestor",
            "supervisor/done-worker-12345678",
            "main",
        ]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == [
            "git",
            "-C",
            str(repo_root),
            "branch",
            "-d",
            "supervisor/done-worker-12345678",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                "Deleted branch supervisor/done-worker-12345678.\n",
                "",
            )
        if command == [
            "git",
            "-C",
            str(repo_root),
            "push",
            "origin",
            "--delete",
            "supervisor/done-worker-12345678",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                "",
                "To https://example.test/repo.git\n - [deleted] supervisor/done-worker-12345678\n",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "isotope.features.supervisor.integration_review.subprocess.run",
        fake_run,
    )

    result = _execute_llm_action(
        _runner_args(codex_home),
        _empty_report(),
        {
            "llm_action": {
                "kind": "delete_worktree",
                "target_name": "done-worker",
                "record_id": "managed-done",
                "confirm_delete_worktree": True,
                "reason": "已确认 worker 完成、归档且已合入 main。",
            }
        },
    )

    assert result["kind"] == "delete_worktree"
    assert result["deleted_worktree"] == str(worktree)
    assert result["managed"]["record_id"] == "managed-done"
    assert result["integration"]["group"] == "already_integrated"
    assert result["branch_cleanup"] == {
        "branch": "supervisor/done-worker-12345678",
        "deleted_local_branch": "supervisor/done-worker-12345678",
        "upstream": "origin/supervisor/done-worker-12345678",
        "deleted_upstream_branch": "origin/supervisor/done-worker-12345678",
    }
    assert worktree.exists() is False
    assert ["git", "-C", str(repo_root), "worktree", "remove", str(worktree)] in run_calls
    assert [
        "git",
        "-C",
        str(repo_root),
        "branch",
        "-d",
        "supervisor/done-worker-12345678",
    ] in run_calls
    assert [
        "git",
        "-C",
        str(repo_root),
        "push",
        "origin",
        "--delete",
        "supervisor/done-worker-12345678",
    ] in run_calls


def test_delete_worktree_candidates_include_archived_integrated_merge_worker(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    worktree = repo_root / ".worktrees" / "supervisor" / "merge-worker-12345678"
    worktree.mkdir(parents=True)
    _write_managed_record_event(
        codex_home,
        record_id="managed-merge",
        name="supervisor-merge-dispatch",
        cwd=worktree,
        record_status="launched",
        protocol_status="done",
        prompt="source=integration_review merge managed-source",
    )
    _write_managed_record_event(
        codex_home,
        record_id="managed-merge",
        name="supervisor-merge-dispatch",
        cwd=worktree,
        record_status="archived",
        protocol_status="done",
        prompt="source=integration_review merge managed-source",
    )

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if _is_pytest_gate_command(command):
            return subprocess.CompletedProcess(command, 0, "12 passed\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "supervisor/supervisor-merge-dispatch-12345678\n",
                "",
            )
        if command == ["git", "-C", str(worktree), "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "merge111\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "main"]:
            return subprocess.CompletedProcess(command, 0, "merge111\n", "")
        if command == ["git", "-C", str(worktree), "rev-parse", "main^{tree}"]:
            return subprocess.CompletedProcess(command, 0, "tree-ok\n", "")
        if command == ["git", "-C", str(worktree), "status", "--short"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == ["git", "-C", str(worktree), "merge-base", "--is-ancestor", "merge111", "main"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == ["git", "-C", str(worktree), "merge-base", "--is-ancestor", "main", "merge111"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command == ["git", "-C", str(worktree), "merge-tree", "--write-tree", "main", "merge111"]:
            return subprocess.CompletedProcess(command, 0, "tree-ok\n", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)
    monkeypatch.setattr(
        "isotope.features.supervisor.integration_review.subprocess.run",
        fake_run,
    )

    candidates = _delete_worktree_candidate_payloads(_runner_args(codex_home))

    assert candidates == [
        {
            "name": "supervisor-merge-dispatch",
            "target_name": "supervisor-merge-dispatch",
            "record_id": "managed-merge",
            "cwd": str(worktree),
            "archived": True,
            "integration_group": "merge_workers",
            "main_contains_worker": True,
            "main_has_worker_patch": True,
            "worker_commit": "merge111",
            "base_ref": "main",
        }
    ]


def test_execute_delete_worktree_skips_unarchived_worker(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    worktree = repo_root / ".worktrees" / "supervisor" / "active-worker-12345678"
    worktree.mkdir(parents=True)
    _write_managed_record_event(
        codex_home,
        record_id="managed-active",
        name="active-worker",
        cwd=worktree,
        record_status="launched",
        protocol_status="done",
    )

    def fail_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"git should not be called for unarchived worker: {command}")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fail_run)

    result = _execute_llm_action(
        _runner_args(codex_home),
        _empty_report(),
        {
            "llm_action": {
                "kind": "delete_worktree",
                "target_name": "active-worker",
                "record_id": "managed-active",
                "confirm_delete_worktree": True,
                "reason": "模型误选未归档 worker。",
            }
        },
    )

    assert result["skipped"] is True
    assert result["reason"] == "managed worker is not archived"
    assert worktree.exists() is True


def test_execute_delete_worktree_skips_path_outside_supervisor_worktrees(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "repo" / "normal-workspace"
    workspace.mkdir(parents=True)
    _write_managed_record_event(
        codex_home,
        record_id="managed-outside",
        name="outside-worker",
        cwd=workspace,
        record_status="archived",
        protocol_status="done",
    )

    result = _execute_llm_action(
        _runner_args(codex_home),
        _empty_report(),
        {
            "llm_action": {
                "kind": "delete_worktree",
                "target_name": "outside-worker",
                "record_id": "managed-outside",
                "confirm_delete_worktree": True,
                "reason": "模型误选普通目录。",
            }
        },
    )

    assert result["skipped"] is True
    assert result["reason"] == "worktree is outside .worktrees/supervisor"
    assert workspace.exists() is True


def _runner_args(codex_home: Path) -> argparse.Namespace:
    return argparse.Namespace(codex_home=str(codex_home))


def _empty_report() -> CodexSupervisorReport:
    return CodexSupervisorReport(generated_at=NOW.isoformat(), sessions=())


def _write_managed_record_event(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    record_status: str,
    protocol_status: str,
    prompt: str | None = None,
) -> None:
    log_path = codex_home / "supervisor" / "logs" / f"{record_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                f"SUPERVISOR_STATUS: {protocol_status}",
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
                    "prompt": prompt or f"review {name}",
                    "command": ["codex", "exec", "-C", str(cwd), "prompt"],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(log_path),
                    "status": record_status,
                    "backend": "process",
                    "tmux_session": None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def _is_pytest_gate_command(command: list[str]) -> bool:
    return (
        command[1:] == ["-m", "pytest", "tests/isotope", "-q"]
        and command[0] in {".venv/bin/python", sys.executable}
    )
