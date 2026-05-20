from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.runner import main as supervisor_main


NOW = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)


def test_supervisor_loop_auto_archives_ready_worker_and_marks_done_notification(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    ready_worktree = workspace / "ready-worker"
    active_worktree = workspace / "active-worker"
    ready_worktree.mkdir(parents=True)
    active_worktree.mkdir()
    _write_managed_record(
        codex_home,
        record_id="managed-ready",
        name="ready-worker",
        cwd=ready_worktree,
        protocol_status="done",
    )
    _write_managed_record(
        codex_home,
        record_id="managed-active",
        name="active-worker",
        cwd=active_worktree,
        protocol_status="done",
        extra_log="◦ Working (esc to interrupt)\n",
    )
    notification = NotificationFlow.in_process(codex_home).create_notification(
        notification_type="supervisor_goal_status",
        title="Supervisor goal status: done",
        source_ref={
            "ref_type": "supervisor_goal_status",
            "goal_id": "goal-ready",
            "status": "done",
        },
    )

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished: _integration_payload(
            ready_to_integrate=[
                {
                    "record_id": "managed-ready",
                    "name": "ready-worker",
                    "group": "ready_to_integrate",
                }
            ],
            already_integrated=[],
        ),
    )

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--rule-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    archived = payload["cleanup_archived"]
    assert [item["kind"] for item in archived] == ["managed_worker", "notification"]
    assert archived[0]["name"] == "ready-worker"
    assert archived[0]["integration_group"] == "ready_to_integrate"
    assert "delete_worktree" not in archived[0]
    assert archived[1]["notification_id"] == notification.notification_id
    assert ready_worktree.exists() is True
    assert active_worktree.exists() is True

    registry_events = _registry_events(codex_home)
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == ["ready-worker"]
    assert NotificationFlow.in_process(codex_home).get_notification(
        notification.notification_id
    ).unread is False


def test_supervisor_loop_auto_removes_archived_already_integrated_worktree_only(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    done_worktree = repo_root / ".worktrees" / "supervisor" / "done-worker-12345678"
    active_worktree = repo_root / ".worktrees" / "supervisor" / "active-worker-12345678"
    done_worktree.mkdir(parents=True)
    active_worktree.mkdir()
    _write_managed_record(
        codex_home,
        record_id="managed-done",
        name="done-worker",
        cwd=done_worktree,
        protocol_status="done",
    )
    _write_managed_record(
        codex_home,
        record_id="managed-active",
        name="active-worker",
        cwd=active_worktree,
        protocol_status="done",
        extra_log="◦ Working (esc to interrupt)\n",
    )
    remove_calls: list[list[str]] = []

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished: _integration_payload(
            ready_to_integrate=[],
            already_integrated=[
                {
                    "record_id": "managed-done",
                    "name": "done-worker",
                    "group": "already_integrated",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.review_managed_record_integration",
        lambda record, *, base_ref="main", run=None: {
            "group": "already_integrated",
            "reason": "main 已包含 worker HEAD；可检查后归档。",
            "worker_commit": "done111",
            "base_ref": base_ref,
            "main_contains_worker": True,
            "main_has_worker_patch": False,
            "dirty": False,
        },
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
    )

    def fake_run(
        command: list[str],
        *,
        check: bool = False,
        text: bool = False,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        remove_calls.append(command)
        assert command == [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "remove",
            str(done_worktree),
        ]
        shutil.rmtree(done_worktree)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("isotope.features.supervisor.runner.subprocess.run", fake_run)

    exit_code = supervisor_main(
        [
            "loop",
            "--codex-home",
            str(codex_home),
            "--iterations",
            "1",
            "--interval",
            "1",
            "--no-auto-adopt",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    archived = payload["cleanup_archived"]
    assert [item["name"] for item in archived] == ["done-worker"]
    assert archived[0]["integration_group"] == "already_integrated"
    assert archived[0]["delete_worktree"]["deleted_worktree"] == str(done_worktree)
    assert remove_calls == [
        ["git", "-C", str(repo_root), "worktree", "remove", str(done_worktree)]
    ]
    assert done_worktree.exists() is False
    assert active_worktree.exists() is True

    registry_events = _registry_events(codex_home)
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == ["done-worker"]


def _write_managed_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    protocol_status: str,
    extra_log: str = "",
) -> None:
    log_path = codex_home / "supervisor" / "logs" / f"{record_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                f"SUPERVISOR_STATUS: {protocol_status}",
                f"SUPERVISOR_SUMMARY: {name} summary",
                "SUPERVISOR_NEXT: 等待 Supervisor 归档",
                extra_log,
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
                    "started_at": NOW.isoformat(),
                    "log_path": str(log_path),
                    "status": "launched",
                    "backend": "process",
                    "tmux_session": None,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def _integration_payload(
    *,
    ready_to_integrate: list[dict[str, Any]],
    already_integrated: list[dict[str, Any]],
) -> dict[str, Any]:
    groups = {
        "merge_workers": [],
        "ready_to_integrate": ready_to_integrate,
        "already_integrated": already_integrated,
        "needs_review": [],
        "conflict_risk": [],
    }
    workers = [*ready_to_integrate, *already_integrated]
    return {
        "status": "ok",
        "base_ref": "main",
        "include_unfinished": False,
        "summary": {
            key: len(value) for key, value in groups.items()
        } | {"total": len(workers)},
        "groups": groups,
        "workers": workers,
        "safety": {
            "auto_merge": False,
            "push": False,
            "delete_branch": False,
        },
    }


def _registry_events(codex_home: Path) -> list[dict[str, Any]]:
    registry_path = codex_home / "supervisor" / "managed_sessions.jsonl"
    return [
        json.loads(line)
        for line in registry_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
