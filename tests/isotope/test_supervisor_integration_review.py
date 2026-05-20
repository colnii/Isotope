from __future__ import annotations

import json
import subprocess
from pathlib import Path

from isotope.features.supervisor.runner import main as supervisor_main


def test_supervisor_integration_review_groups_ready_and_already_integrated(tmp_path):
    from isotope.features.supervisor.integration_review import (
        collect_integration_reviews,
        render_integration_review_plain,
    )

    codex_home = tmp_path / ".codex"
    ready_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "ready-12345678"
    done_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "done-12345678"
    ready_cwd.mkdir(parents=True)
    done_cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-ready", name="ready", cwd=ready_cwd)
    _write_done_record(codex_home, record_id="managed-done", name="done", cwd=done_cwd)

    fake_run = _fake_git(
        {
            ready_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/ready-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "ready111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "ready111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "ready111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "ready111"): (0, "tree-ok\n", ""),
            },
            done_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/done-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "done222\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "done222", "main"): (0, "", ""),
                ("merge-base", "--is-ancestor", "main", "done222"): (1, "", ""),
                ("merge-tree", "--write-tree", "main", "done222"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(
        codex_home=codex_home,
        include_unfinished=True,
        run=fake_run,
    )

    assert payload["status"] == "ok"
    assert payload["base_ref"] == "main"
    assert payload["summary"] == {
        "total": 2,
        "ready_to_integrate": 1,
        "already_integrated": 1,
        "needs_review": 0,
        "conflict_risk": 0,
    }
    ready = payload["groups"]["ready_to_integrate"][0]
    assert ready["record_id"] == "managed-ready"
    assert ready["branch"] == "supervisor/ready-12345678"
    assert ready["worker_commit"] == "ready111"
    assert ready["base_commit"] == "main999"
    assert ready["main_contains_worker"] is False
    assert ready["worker_contains_main"] is True
    assert ready["reason"] == "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。"
    already = payload["groups"]["already_integrated"][0]
    assert already["record_id"] == "managed-done"
    assert already["main_contains_worker"] is True

    plain = render_integration_review_plain(payload)
    assert "ready_to_integrate：1" in plain
    assert "already_integrated：1" in plain
    assert "supervisor/ready-12345678 @ ready111" in plain


def test_supervisor_integration_review_flags_dirty_and_unfinished_workers(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    dirty_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "dirty-12345678"
    blocked_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "blocked-12345678"
    dirty_cwd.mkdir(parents=True)
    blocked_cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-dirty", name="dirty", cwd=dirty_cwd)
    _write_record(
        codex_home,
        record_id="managed-blocked",
        name="blocked",
        cwd=blocked_cwd,
        protocol_status="blocked",
    )

    fake_run = _fake_git(
        {
            dirty_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/dirty-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "dirty111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, " M src/isotope/features/supervisor/runner.py\n", ""),
                ("merge-base", "--is-ancestor", "dirty111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "dirty111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "dirty111"): (0, "tree-ok\n", ""),
            },
            blocked_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/blocked-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "blocked111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "blocked111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "blocked111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "blocked111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(
        codex_home=codex_home,
        include_unfinished=True,
        run=fake_run,
    )

    assert payload["summary"]["needs_review"] == 2
    reasons = {item["record_id"]: item["reason"] for item in payload["groups"]["needs_review"]}
    assert reasons["managed-dirty"] == "worker worktree 仍有未提交改动；先复查并要求 worker 提交。"
    assert reasons["managed-blocked"] == "worker 未汇报 done；先按 SUPERVISOR_NEXT 继续或拆分。"


def test_supervisor_integration_review_defaults_to_done_unarchived_workers(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    done_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "done-12345678"
    blocked_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "blocked-12345678"
    archived_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "archived-12345678"
    done_cwd.mkdir(parents=True)
    blocked_cwd.mkdir(parents=True)
    archived_cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-done", name="done", cwd=done_cwd)
    _write_record(
        codex_home,
        record_id="managed-blocked",
        name="blocked",
        cwd=blocked_cwd,
        protocol_status="blocked",
    )
    _write_done_record(
        codex_home,
        record_id="managed-archived",
        name="archived",
        cwd=archived_cwd,
        record_status="archived",
    )

    fake_run = _fake_git(
        {
            done_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/done-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "done111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "done111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "done111"): (0, "", ""),
                ("merge-tree", "--write-tree", "main", "done111"): (0, "tree-ok\n", ""),
            },
        }
    )

    payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert payload["include_unfinished"] is False
    assert payload["summary"]["total"] == 1
    assert payload["workers"][0]["record_id"] == "managed-done"


def test_supervisor_integration_review_flags_merge_conflict_risk(tmp_path):
    from isotope.features.supervisor.integration_review import collect_integration_reviews

    codex_home = tmp_path / ".codex"
    conflict_cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "conflict-12345678"
    conflict_cwd.mkdir(parents=True)
    _write_done_record(
        codex_home,
        record_id="managed-conflict",
        name="conflict",
        cwd=conflict_cwd,
    )

    fake_run = _fake_git(
        {
            conflict_cwd: {
                ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/conflict-12345678\n", ""),
                ("rev-parse", "HEAD"): (0, "conflict111\n", ""),
                ("rev-parse", "main"): (0, "main999\n", ""),
                ("status", "--short"): (0, "", ""),
                ("merge-base", "--is-ancestor", "conflict111", "main"): (1, "", ""),
                ("merge-base", "--is-ancestor", "main", "conflict111"): (1, "", ""),
                ("merge-tree", "--write-tree", "main", "conflict111"): (
                    1,
                    "",
                    "CONFLICT (content): Merge conflict in src/example.py\n",
                ),
            },
        }
    )

    payload = collect_integration_reviews(codex_home=codex_home, run=fake_run)

    assert payload["summary"]["conflict_risk"] == 1
    item = payload["groups"]["conflict_risk"][0]
    assert item["record_id"] == "managed-conflict"
    assert item["merge_conflict"] is True
    assert item["reason"] == "只读 merge-tree 检测到 conflict；需要人工 rebase/merge 处理。"
    assert "CONFLICT (content)" in item["merge_check"]["stderr"]


def test_supervisor_integration_review_cli_json(tmp_path, capsys, monkeypatch):
    codex_home = tmp_path / ".codex"
    cwd = tmp_path / "repo" / ".worktrees" / "supervisor" / "ready-12345678"
    cwd.mkdir(parents=True)
    _write_done_record(codex_home, record_id="managed-ready", name="ready", cwd=cwd)
    monkeypatch.setattr(
        "isotope.features.supervisor.integration_review.subprocess.run",
        _fake_git(
            {
                cwd: {
                    ("rev-parse", "--abbrev-ref", "HEAD"): (0, "supervisor/ready-12345678\n", ""),
                    ("rev-parse", "HEAD"): (0, "ready111\n", ""),
                    ("rev-parse", "main"): (0, "main999\n", ""),
                    ("status", "--short"): (0, "", ""),
                    ("merge-base", "--is-ancestor", "ready111", "main"): (1, "", ""),
                    ("merge-base", "--is-ancestor", "main", "ready111"): (0, "", ""),
                    ("merge-tree", "--write-tree", "main", "ready111"): (0, "tree-ok\n", ""),
                }
            }
        ),
    )

    exit_code = supervisor_main(
        ["integration-review", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["ready_to_integrate"] == 1
    assert payload["groups"]["ready_to_integrate"][0]["record_id"] == "managed-ready"


def _fake_git(
    responses: dict[Path, dict[tuple[str, ...], tuple[int, str, str]]],
):
    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["git", "-C", command[2]]
        assert check is False
        assert text is True
        assert capture_output is True
        cwd = Path(command[2])
        args = tuple(command[3:])
        try:
            returncode, stdout, stderr = responses[cwd][args]
        except KeyError as exc:
            raise AssertionError(f"unexpected command: {command}") from exc
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return fake_run


def _write_done_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    record_status: str = "launched",
) -> None:
    _write_record(
        codex_home,
        record_id=record_id,
        name=name,
        cwd=cwd,
        protocol_status="done",
        record_status=record_status,
    )


def _write_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    protocol_status: str,
    record_status: str = "launched",
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
                    "prompt": f"review {name}",
                    "command": ["codex", "exec", "-C", str(cwd), "prompt"],
                    "pid": 0,
                    "started_at": "2026-05-20T12:00:00+00:00",
                    "log_path": str(log_path),
                    "status": record_status,
                    "backend": "process",
                    "tmux_session": None,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
