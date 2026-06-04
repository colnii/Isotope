from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope.features.notifications.flow import NotificationFlow
from isotope.features.supervisor.planner.decision_requests import (
    read_active_decision_requests,
    record_decision_answer,
)
from isotope.features.supervisor.runner import (
    _auto_archive_integrated_merge_workers,
    _auto_promote_done_merge_workers_to_main,
    main as supervisor_main,
)


NOW = datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc)


def test_supervisor_loop_skips_blocking_merge_promotion_by_default(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda **kwargs: _integration_payload(
            ready_to_integrate=[],
            already_integrated=[],
            merge_workers=[
                {
                    "record_id": "managed-merge",
                    "name": "supervisor-merge-dispatch",
                    "branch": "supervisor/supervisor-merge-dispatch",
                    "worker_commit": "merge123",
                    "supervisor_protocol": {
                        "status": "done",
                        "summary": "CI 已通过。",
                    },
                }
            ],
        ),
    )

    def fail_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("merge promotion should not run during the default loop")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
        },
    )()

    assert _auto_promote_done_merge_workers_to_main(args, run=fail_run) == []


def test_auto_promote_blocked_merge_worker_launches_same_worktree_repair(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    merge_worktree = repo_root / ".worktrees" / "supervisor" / "merge-dispatch"
    repo_root.mkdir()
    merge_worktree.mkdir(parents=True)
    _write_managed_record(
        codex_home,
        record_id="managed-merge",
        name="supervisor-merge-dispatch",
        cwd=merge_worktree,
        protocol_status="blocked",
        worker_role="merge_dispatch",
        extra_log=(
            "SUPERVISOR_SUMMARY: cherry-pick fe47809 时 tests/unit/test_flow.py "
            "出现 content conflict\n"
            "SUPERVISOR_NEXT: 需要继续处理当前 cherry-pick 冲突\n"
        ),
        prompt="source: integration_review",
    )
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "cwd": str(merge_worktree),
                "cwd_exists": True,
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "blocked",
                    "summary": (
                        "cherry-pick fe47809 时 tests/unit/test_flow.py "
                        "出现 content conflict"
                    ),
                    "next": "需要继续处理当前 cherry-pick 冲突",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    launched: dict[str, Any] = {}

    class StubRecord:
        name = "supervisor-merge-dispatch-repair"
        record_id = "managed-repair"
        pid = 45690
        backend = "process"
        worker_role = "merge_repair"

    def stub_launch_managed_codex(**kwargs: Any) -> StubRecord:
        launched.update(kwargs)
        return StubRecord()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        stub_launch_managed_codex,
    )
    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
            "auto_merge_promote": True,
            "prompt_cooldown": 0,
            "worker_profile": "coding",
            "worker_codex_model": None,
            "worker_codex_config": None,
        },
    )()

    repaired = _auto_promote_done_merge_workers_to_main(args, run=subprocess.run)

    assert repaired[0]["status"] == "repair_launched"
    assert repaired[0]["kind"] == "merge_worker_conflict_repair"
    assert repaired[0]["repair"]["managed"]["worker_role"] == "merge_repair"
    assert launched["cwd"] == merge_worktree
    assert launched["name"] == "supervisor-merge-dispatch-repair"
    assert launched["worker_role"] == "merge_repair"
    assert "source: integration_review" in launched["prompt"]
    assert "git status" in launched["prompt"]
    assert "cherry-pick --continue" in launched["prompt"]
    assert "tests/unit/test_flow.py" in launched["prompt"]


def test_supervisor_loop_keeps_ready_worker_for_explicit_cleanup(
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
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_payload(
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
    assert "cleanup_archived" not in payload
    assert ready_worktree.exists() is True
    assert active_worktree.exists() is True

    registry_events = _registry_events(codex_home)
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == []
    assert NotificationFlow.in_process(codex_home).get_notification(
        notification.notification_id
    ).unread is True


def test_supervisor_loop_keeps_already_integrated_worktree_for_explicit_cleanup(
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
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_payload(
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
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
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
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "cleanup_archived" not in payload
    assert done_worktree.exists() is True
    assert active_worktree.exists() is True

    registry_events = _registry_events(codex_home)
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == []


def test_supervisor_loop_executes_lifecycle_cleanup_only_with_explicit_flag(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    done_worktree = repo_root / ".worktrees" / "supervisor" / "done-worker-12345678"
    done_worktree.mkdir(parents=True)
    _write_managed_record(
        codex_home,
        record_id="managed-done",
        name="done-worker",
        cwd=done_worktree,
        protocol_status="done",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_payload(
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
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
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
            "--lifecycle-cleanup-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worker_lifecycle_execution"]["kind"] == "archive_cleanup"
    assert payload["executed"]["kind"] == "archive_cleanup"
    assert payload["executed"]["archived"][0]["managed"]["record_id"] == "managed-done"

    registry_events = _registry_events(codex_home)
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == ["done-worker"]


def test_supervisor_loop_executes_lifecycle_archive_with_archive_flag(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    done_worktree = repo_root / ".worktrees" / "supervisor" / "done-worker-12345678"
    done_worktree.mkdir(parents=True)
    _write_managed_record(
        codex_home,
        record_id="managed-done",
        name="done-worker",
        cwd=done_worktree,
        protocol_status="done",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_payload(
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
        "isotope.features.supervisor.flow._git_branch_for",
        lambda cwd: None,
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
            "--lifecycle-archive-execute",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worker_lifecycle_execution"]["kind"] == "archive_cleanup"
    assert payload["executed"]["kind"] == "archive_cleanup"
    assert payload["executed"]["archived"][0]["managed"]["record_id"] == "managed-done"
    assert done_worktree.exists() is True

    registry_events = _registry_events(codex_home)
    archived_names = [
        item["name"] for item in registry_events if item.get("status") == "archived"
    ]
    assert archived_names == ["done-worker"]


def test_auto_archive_merge_cleanup_targets_source_record_id_when_names_repeat(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "workspace"
    old_source_worktree = workspace / "source-old"
    new_source_worktree = workspace / "source-new"
    merge_worktree = workspace / "merge-worker"
    old_source_worktree.mkdir(parents=True)
    new_source_worktree.mkdir()
    merge_worktree.mkdir()
    _write_managed_record(
        codex_home,
        record_id="managed-source-old",
        name="source-worker",
        cwd=old_source_worktree,
        protocol_status="done",
    )
    _write_managed_record(
        codex_home,
        record_id="managed-source-new",
        name="source-worker",
        cwd=new_source_worktree,
        protocol_status="working",
    )
    _write_managed_record(
        codex_home,
        record_id="managed-merge",
        name="supervisor-merge-dispatch",
        cwd=merge_worktree,
        protocol_status="done",
        prompt="merge source candidate managed-source-old",
    )

    archived = _auto_archive_integrated_merge_workers(
        codex_home=codex_home,
        review_payload=_integration_payload(
            merge_workers=[
                {
                    "record_id": "managed-merge",
                    "name": "supervisor-merge-dispatch",
                    "group": "merge_workers",
                    "supervisor_protocol": {
                        "status": "done",
                        "summary": "merge worker done",
                        "next": "等待 Supervisor 归档",
                    },
                }
            ],
            ready_to_integrate=[],
            already_integrated=[
                {
                    "record_id": "managed-source-old",
                    "name": "source-worker",
                    "group": "already_integrated",
                }
            ],
        ),
    )

    assert [item["record_id"] for item in archived] == [
        "managed-source-old",
        "managed-merge",
    ]
    latest_status_by_record_id = {
        item["record_id"]: item["status"] for item in _registry_events(codex_home)
    }
    assert latest_status_by_record_id["managed-source-old"] == "archived"
    assert latest_status_by_record_id["managed-source-new"] == "launched"
    assert latest_status_by_record_id["managed-merge"] == "archived"


def test_auto_promote_done_merge_worker_fast_forwards_main_after_branch_ci_success(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "done",
                    "summary": "CI run 101 conclusion 为 success。",
                    "next": "等待 Supervisor cleanup 归档。",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    calls: list[list[str]] = []

    def stub_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["gh", "run", "list"]:
            branch = command[command.index("--branch") + 1]
            if branch == "supervisor/supervisor-merge-dispatch-abcd1234":
                stdout = json.dumps(
                    [
                        {
                            "databaseId": 101,
                            "headSha": "merge123",
                            "status": "completed",
                            "conclusion": "success",
                            "url": "https://example.test/branch-ci",
                        }
                    ]
                )
                return subprocess.CompletedProcess(command, 0, stdout, "")
            if branch == "main":
                stdout = json.dumps(
                    [
                        {
                            "databaseId": 102,
                            "headSha": "merge123",
                            "status": "completed",
                            "conclusion": "success",
                            "url": "https://example.test/main-ci",
                        }
                    ]
                )
                return subprocess.CompletedProcess(command, 0, stdout, "")
        if command == ["gh", "run", "watch", "102", "--exit-status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["gh", "run", "view", "102"]:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "databaseId": 102,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": "success",
                        "url": "https://example.test/main-ci",
                    }
                ),
                "",
            )
        if command[:3] == ["git", "-C", str(repo_root)]:
            args = command[3:]
            if args == ["status", "--short"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, "main\n", "")
            if args == ["merge", "--ff-only", "merge123"]:
                return subprocess.CompletedProcess(command, 0, "Updating main\n", "")
            if args == ["diff", "--check"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["push", "origin", "main"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, "merge123\n", "")
        raise AssertionError(f"unexpected command: {command}")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
                "auto_merge_promote": True,
        },
    )()

    promoted = _auto_promote_done_merge_workers_to_main(args, run=stub_run)

    assert promoted == [
        {
            "kind": "merge_worker_main_promotion",
            "name": "supervisor-merge-dispatch",
            "record_id": "managed-merge",
            "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
            "worker_commit": "merge123",
            "status": "done",
            "main_head": "merge123",
            "branch_ci": {
                "databaseId": 101,
                "headSha": "merge123",
                "status": "completed",
                "conclusion": "success",
                "url": "https://example.test/branch-ci",
            },
            "main_ci": {
                "databaseId": 102,
                "headSha": "merge123",
                "status": "completed",
                "conclusion": "success",
                "url": "https://example.test/main-ci",
            },
        }
    ]
    assert ["git", "-C", str(repo_root), "merge", "--ff-only", "merge123"] in calls
    assert ["git", "-C", str(repo_root), "push", "origin", "main"] in calls
    assert ["gh", "run", "watch", "102", "--exit-status"] in calls


def test_auto_promote_done_merge_worker_records_decision_when_branch_ci_fails(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "done",
                    "summary": "CI run 101 conclusion 为 failure。",
                    "next": "等待 Supervisor 处理 promotion 失败。",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    calls: list[list[str]] = []

    def stub_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["gh", "run", "list"]:
            stdout = json.dumps(
                [
                    {
                        "databaseId": 101,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": "failure",
                        "url": "https://example.test/branch-ci",
                    }
                ]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        raise AssertionError(f"unexpected command: {command}")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
                "auto_merge_promote": True,
            "webhook_url": None,
            "webhook_secret": None,
        },
    )()

    promoted = _auto_promote_done_merge_workers_to_main(args, run=stub_run)

    assert promoted[0]["status"] == "blocked"
    assert promoted[0]["reason"] == "branch CI did not succeed"
    decision = promoted[0]["decision_request"]
    assert decision["request_id"].startswith("decision-")
    assert decision["target_name"] == "supervisor-merge-dispatch"
    assert decision["reason"] == "merge_promotion_failed"
    assert decision["gate"]["event_type"] == "merge_promotion_failed"
    assert not any(command[:3] == ["git", "-C", str(repo_root)] for command in calls)
    active_decisions = [
        json.loads(line)
        for line in (codex_home / "supervisor" / "decision_requests.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert active_decisions == [decision]


def test_auto_promote_done_merge_worker_honors_abandon_decision_without_retry(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "done",
                    "summary": "CI run 101 conclusion 为 failure。",
                    "next": "等待 Supervisor 处理 promotion 失败。",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    calls: list[list[str]] = []

    def stub_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["gh", "run", "list"]:
            stdout = json.dumps(
                [
                    {
                        "databaseId": 101,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": "failure",
                    }
                ]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        raise AssertionError(f"unexpected command: {command}")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
                "auto_merge_promote": True,
            "webhook_url": None,
            "webhook_secret": None,
        },
    )()
    first = _auto_promote_done_merge_workers_to_main(args, run=stub_run)
    decision = first[0]["decision_request"]
    assert decision["reason"] == "merge_promotion_failed"
    record_decision_answer(
        codex_home=codex_home,
        request_id=decision["request_id"],
        answer="放弃这个 merge worker，不再尝试合入。",
    )
    calls.clear()

    second = _auto_promote_done_merge_workers_to_main(args, run=stub_run)

    assert second[0]["status"] == "skipped_by_decision"
    assert second[0]["reason"] == "merge promotion abandoned by decision"
    assert second[0]["name"] == "supervisor-merge-dispatch"
    assert second[0]["record_id"] == "managed-merge"
    answered = second[0]["decision_answer"]
    assert answered["event"] == "decision_answer"
    assert answered["request_id"] == decision["request_id"]
    assert answered["session_id"] == "managed:managed-merge"
    assert answered["target_name"] == "supervisor-merge-dispatch"
    assert answered["answer"] == "放弃这个 merge worker，不再尝试合入。"
    assert answered["reason"] == "merge_promotion_failed"
    assert answered["context_status"] == "promotion_blocked"
    assert answered["gate"] == decision["gate"]
    assert calls == []
    assert read_active_decision_requests(codex_home=codex_home) == ()


def test_auto_promote_done_merge_worker_launches_repair_worker_from_decision(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repair_worktree = repo_root / ".worktrees" / "supervisor" / "repair"
    repo_root.mkdir()
    repair_worktree.mkdir(parents=True)
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "done",
                    "summary": "CI run 101 conclusion 为 failure。",
                    "next": "等待 Supervisor 处理 promotion 失败。",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )

    def stub_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "list"]:
            stdout = json.dumps(
                [
                    {
                        "databaseId": 101,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": "failure",
                        "url": "https://example.test/branch-ci",
                    }
                ]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        raise AssertionError(f"unexpected command: {command}")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
                "auto_merge_promote": True,
            "webhook_url": None,
            "webhook_secret": None,
            "worker_profile": "coding",
            "worker_codex_model": None,
            "worker_codex_config": None,
        },
    )()
    first = _auto_promote_done_merge_workers_to_main(args, run=stub_run)
    decision = first[0]["decision_request"]
    record_decision_answer(
        codex_home=codex_home,
        request_id=decision["request_id"],
        answer="请派 worker 修复 CI 后重试。",
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._prepare_launch_worktree",
        lambda *, cwd, target_name: {
            "enabled": True,
            "source_cwd": str(cwd),
            "cwd": str(repair_worktree),
            "worktree_root": str(repair_worktree),
            "branch": f"supervisor/{target_name}-test",
        },
    )
    launched: dict[str, Any] = {}

    class StubRecord:
        name = "supervisor-merge-dispatch-repair"
        record_id = "managed-repair"
        pid = 45690
        backend = "process"
        worker_role = "merge_repair"

    def stub_launch_managed_codex(**kwargs: Any) -> StubRecord:
        launched.update(kwargs)
        return StubRecord()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.launch_managed_codex",
        stub_launch_managed_codex,
    )

    repaired = _auto_promote_done_merge_workers_to_main(args, run=stub_run)

    assert repaired[0]["status"] == "repair_launched"
    assert repaired[0]["repair"]["kind"] == "launch_session"
    assert repaired[0]["repair"]["managed"]["worker_role"] == "merge_repair"
    assert repaired[0]["repair"]["managed"]["name"] == "supervisor-merge-dispatch-repair"
    assert launched["cwd"] == repair_worktree
    assert launched["name"] == "supervisor-merge-dispatch-repair"
    assert launched["worker_role"] == "merge_repair"
    assert "merge123" in launched["prompt"]
    assert "https://example.test/branch-ci" in launched["prompt"]
    assert "请派 worker 修复 CI 后重试。" in launched["prompt"]


def test_auto_promote_done_merge_worker_retries_after_retry_decision(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "done",
                    "summary": "CI run 101 conclusion 为 failure。",
                    "next": "等待 Supervisor 处理 promotion 失败。",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    ci_succeeds = False
    calls: list[list[str]] = []

    def stub_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["gh", "run", "list"]:
            branch = command[command.index("--branch") + 1]
            conclusion = "success" if ci_succeeds else "failure"
            stdout = json.dumps(
                [
                    {
                        "databaseId": 101 if branch != "main" else 102,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                ]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        if command == ["gh", "run", "watch", "102", "--exit-status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["gh", "run", "view", "102"]:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "databaseId": 102,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ),
                "",
            )
        if command[:3] == ["git", "-C", str(repo_root)]:
            args = command[3:]
            if args == ["status", "--short"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, "main\n", "")
            if args == ["merge", "--ff-only", "merge123"]:
                return subprocess.CompletedProcess(command, 0, "Updating main\n", "")
            if args == ["diff", "--check"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["push", "origin", "main"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, "merge123\n", "")
        raise AssertionError(f"unexpected command: {command}")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
                "auto_merge_promote": True,
            "webhook_url": None,
            "webhook_secret": None,
        },
    )()
    first = _auto_promote_done_merge_workers_to_main(args, run=stub_run)
    decision = first[0]["decision_request"]
    record_decision_answer(
        codex_home=codex_home,
        request_id=decision["request_id"],
        answer="重试 promotion。",
    )
    ci_succeeds = True
    calls.clear()

    retried = _auto_promote_done_merge_workers_to_main(args, run=stub_run)

    assert retried[0]["status"] == "done"
    assert ["git", "-C", str(repo_root), "merge", "--ff-only", "merge123"] in calls
    assert read_active_decision_requests(codex_home=codex_home) == ()


def test_auto_promote_done_merge_worker_retries_after_repair_worker_done(
    tmp_path,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repair_worktree = repo_root / ".worktrees" / "supervisor" / "repair"
    repo_root.mkdir()
    repair_worktree.mkdir(parents=True)
    review_payload = _integration_payload(
        merge_workers=[
            {
                "record_id": "managed-merge",
                "name": "supervisor-merge-dispatch",
                "group": "merge_workers",
                "branch": "supervisor/supervisor-merge-dispatch-abcd1234",
                "worker_commit": "merge123",
                "main_contains_worker": False,
                "supervisor_protocol": {
                    "status": "done",
                    "summary": "CI run 101 conclusion 为 failure。",
                    "next": "等待 Supervisor 处理 promotion 失败。",
                },
            }
        ],
        ready_to_integrate=[],
        already_integrated=[],
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: review_payload,
    )
    ci_succeeds = False
    calls: list[list[str]] = []

    def stub_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:3] == ["gh", "run", "list"]:
            branch = command[command.index("--branch") + 1]
            conclusion = "success" if ci_succeeds else "failure"
            stdout = json.dumps(
                [
                    {
                        "databaseId": 101 if branch != "main" else 102,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": conclusion,
                    }
                ]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        if command == ["gh", "run", "watch", "102", "--exit-status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:4] == ["gh", "run", "view", "102"]:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "databaseId": 102,
                        "headSha": "merge123",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ),
                "",
            )
        if command[:3] == ["git", "-C", str(repo_root)]:
            args = command[3:]
            if args == ["status", "--short"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, "main\n", "")
            if args == ["merge", "--ff-only", "merge123"]:
                return subprocess.CompletedProcess(command, 0, "Updating main\n", "")
            if args == ["diff", "--check"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["push", "origin", "main"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if args == ["rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(command, 0, "merge123\n", "")
        raise AssertionError(f"unexpected command: {command}")

    args = type(
        "Args",
        (),
        {
            "command": "loop",
            "codex_home": str(codex_home),
            "workspace_root": str(repo_root),
                "auto_merge_promote": True,
            "webhook_url": None,
            "webhook_secret": None,
            "worker_profile": "coding",
            "worker_codex_model": None,
            "worker_codex_config": None,
        },
    )()
    first = _auto_promote_done_merge_workers_to_main(args, run=stub_run)
    decision = first[0]["decision_request"]
    record_decision_answer(
        codex_home=codex_home,
        request_id=decision["request_id"],
        answer="修复后重试 promotion。",
    )
    _write_managed_record(
        codex_home,
        record_id="managed-repair",
        name="supervisor-merge-dispatch-repair",
        cwd=repair_worktree,
        protocol_status="done",
        worker_role="merge_repair",
    )
    ci_succeeds = True
    calls.clear()

    retried = _auto_promote_done_merge_workers_to_main(args, run=stub_run)

    assert retried[0]["status"] == "done"
    assert retried[0]["repair_completed"]["managed"]["record_id"] == "managed-repair"
    assert retried[0]["repair_completed"]["managed"]["status"] == "archived"
    assert ["git", "-C", str(repo_root), "merge", "--ff-only", "merge123"] in calls
    latest_status_by_record_id = {
        item["record_id"]: item["status"] for item in _registry_events(codex_home)
    }
    assert latest_status_by_record_id["managed-repair"] == "archived"


def _write_managed_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    protocol_status: str,
    extra_log: str = "",
    prompt: str | None = None,
    worker_role: str = "worker",
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
                    "prompt": prompt or f"review {name}",
                    "command": [
                        "codex",
                        "exec",
                        "-C",
                        str(cwd),
                        prompt or "prompt",
                    ],
                    "pid": 0,
                    "started_at": NOW.isoformat(),
                    "log_path": str(log_path),
                    "status": "launched",
                    "backend": "process",
                    "tmux_session": None,
                    "worker_role": worker_role,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def _integration_payload(
    *,
    merge_workers: list[dict[str, Any]] | None = None,
    ready_to_integrate: list[dict[str, Any]],
    already_integrated: list[dict[str, Any]],
) -> dict[str, Any]:
    groups = {
        "merge_workers": merge_workers or [],
        "ready_to_integrate": ready_to_integrate,
        "already_integrated": already_integrated,
        "needs_review": [],
        "conflict_risk": [],
    }
    workers = [*(merge_workers or []), *ready_to_integrate, *already_integrated]
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
