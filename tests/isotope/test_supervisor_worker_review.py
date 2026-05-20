from __future__ import annotations

import json
import subprocess
from pathlib import Path

from isotope.features.supervisor.runner import main as supervisor_main
from isotope.features.supervisor.worker_review import collect_worker_reviews


def test_supervisor_worker_review_collects_completed_worker_with_changes(
    tmp_path,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "feature-a-12345678"
    workspace.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-001.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "tests passed",
                "SUPERVISOR_STATUS: done",
                "SUPERVISOR_SUMMARY: worker 已完成入口和测试。",
                "SUPERVISOR_NEXT: 主控 Codex 审查 diff 后合并。",
            ]
        ),
        encoding="utf-8",
    )
    _write_record(
        codex_home,
        record_id="managed-001",
        name="feature-a",
        cwd=workspace,
        log_path=log_path,
        status="launched",
        pid=111,
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert text is True
        assert capture_output is True
        if command[3:] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "supervisor/feature-a-12345678\n", "")
        if command[3:] == ["status", "--short"]:
            return subprocess.CompletedProcess(
                command,
                0,
                " M src/isotope/features/supervisor/runner.py\n"
                "?? src/isotope/features/supervisor/worker_review.py\n",
                "",
            )
        if command[3:] == ["diff", "--stat"]:
            return subprocess.CompletedProcess(
                command,
                0,
                " src/isotope/features/supervisor/runner.py | 3 ++-\n"
                " 1 file changed, 2 insertions(+), 1 deletion(-)\n",
                "",
            )
        raise AssertionError(f"unexpected command: {command}")

    payload = collect_worker_reviews(
        codex_home=codex_home,
        run=fake_run,
        process_checker=lambda pid: False,
    )

    assert payload["status"] == "ok"
    assert payload["summary"] == {"total": 1, "existing_cwd": 1, "missing_cwd": 0}
    item = payload["workers"][0]
    assert item["name"] == "feature-a"
    assert item["cwd_exists"] is True
    assert item["worktree"]["branch"] == "supervisor/feature-a-12345678"
    assert item["supervisor_protocol"] == {
        "status": "done",
        "summary": "worker 已完成入口和测试。",
        "next": "主控 Codex 审查 diff 后合并。",
    }
    assert item["changes"]["status"] == "modified"
    assert item["changes"]["files"] == [
        {"status": "M", "path": "src/isotope/features/supervisor/runner.py"},
        {"status": "??", "path": "src/isotope/features/supervisor/worker_review.py"},
    ]
    assert item["validation_commands"][0] == f"git -C {workspace} status --short --branch"
    assert "pytest tests/isotope -q" in item["validation_commands"][2]
    assert "不自动合并" in item["merge_hint"]


def test_supervisor_worker_review_reports_deleted_worktree(tmp_path):
    codex_home = tmp_path / ".codex"
    missing_workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "gone-12345678"
    log_path = codex_home / "supervisor" / "logs" / "managed-002.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("SUPERVISOR_STATUS: done\n", encoding="utf-8")
    _write_record(
        codex_home,
        record_id="managed-002",
        name="gone",
        cwd=missing_workspace,
        log_path=log_path,
        status="launched",
        pid=222,
    )

    payload = collect_worker_reviews(
        codex_home=codex_home,
        process_checker=lambda pid: False,
    )

    item = payload["workers"][0]
    assert item["cwd_exists"] is False
    assert item["worktree"]["exists"] is False
    assert item["worktree"]["branch"] == "supervisor/gone-12345678"
    assert item["changes"]["status"] == "unavailable"
    assert item["validation_commands"] == [
        f"test -d {missing_workspace}",
        "git worktree list --porcelain",
    ]
    assert "worktree 已不存在" in item["merge_hint"]


def test_supervisor_worker_review_reports_clean_worker_and_cli_json(
    tmp_path,
    capsys,
    monkeypatch,
):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "clean-12345678"
    workspace.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-003.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("worker still clean\n", encoding="utf-8")
    _write_record(
        codex_home,
        record_id="managed-003",
        name="clean",
        cwd=workspace,
        log_path=log_path,
        status="launched",
        pid=333,
    )

    def fake_run(
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        if command[3:] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "supervisor/clean-12345678\n", "")
        if command[3:] in (["status", "--short"], ["diff", "--stat"]):
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr("isotope.features.supervisor.worker_review.subprocess.run", fake_run)
    monkeypatch.setattr(
        "isotope.features.supervisor.worker_review._pid_is_running",
        lambda pid: False,
    )

    exit_code = supervisor_main(
        ["worker-review", "--codex-home", str(codex_home), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["workers"][0]
    assert item["changes"] == {
        "status": "clean",
        "files": [],
        "stat": None,
        "summary": "无本地改动",
    }
    assert item["supervisor_protocol"] == {"status": None, "summary": None, "next": None}


def _write_record(
    codex_home: Path,
    *,
    record_id: str,
    name: str,
    cwd: Path,
    log_path: Path,
    status: str,
    pid: int,
) -> None:
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
                    "pid": pid,
                    "started_at": "2026-05-20T12:00:00+00:00",
                    "log_path": str(log_path),
                    "status": status,
                    "backend": "process",
                    "tmux_session": None,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
