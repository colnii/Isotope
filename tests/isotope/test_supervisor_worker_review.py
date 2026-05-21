from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

from isotope.features.supervisor.runner import main as supervisor_main
from isotope.features.supervisor.worker_review import (
    collect_worker_reviews,
    render_worker_review_plain,
)


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
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        check = kwargs["check"]
        text = kwargs["text"]
        capture_output = kwargs["capture_output"]
        assert check is False
        assert text is True
        assert capture_output is True
        if _is_pytest_gate_command(command):
            assert Path(kwargs["cwd"]) == workspace
            assert kwargs["env"]["PYTHONPATH"] == "src"
            return subprocess.CompletedProcess(command, 0, "12 passed in 0.34s\n", "")
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
    assert payload["summary"] == {
        "total": 1,
        "visible": 1,
        "hidden_by_lightweight_limit": 0,
        "existing_cwd": 1,
        "missing_cwd": 0,
    }
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
    assert item["reviewer"]["needed"] is True
    assert item["reviewer"]["cwd"] == str(workspace)
    assert item["reviewer"]["branch"] == "supervisor/feature-a-12345678"
    assert item["reviewer"]["goal"] == "review feature-a"
    assert item["reviewer"]["change_summary"] == "2 个路径有改动"
    assert item["reviewer"]["validation_commands"] == item["validation_commands"]
    assert item["reviewer"]["must_check_risks"] == [
        "只复查 diff、测试和 worker 汇报，不自动启动新 worker。",
        "不自动合并、不删除 worktree、不重写分支。",
        "确认改动是否越过原目标范围，尤其是未跟踪文件和 Supervisor 入口行为。",
        "验证命令失败时先记录证据，避免用合并掩盖失败。",
    ]
    assert "codex exec" in item["reviewer"]["command"]
    assert str(workspace) in item["reviewer"]["command"]
    assert "目标：review feature-a" in item["reviewer"]["prompt"]
    assert "cwd：" + str(workspace) in item["reviewer"]["prompt"]
    assert "branch：supervisor/feature-a-12345678" in item["reviewer"]["prompt"]
    assert "建议验证命令：" in item["reviewer"]["prompt"]
    assert "必须检查的风险：" in item["reviewer"]["prompt"]
    assert item["next_decision"] == {
        "recommendation": "review_then_merge_candidate",
        "summary": "worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。",
        "merge_suitable": True,
        "continue_or_split_task": False,
        "risk_level": "medium",
        "reasons": [
            "worker 汇报 done",
            "存在 2 个改动路径",
            "包含未跟踪文件",
            "需要先运行建议验证命令",
        ],
        "next_actions": [
            "审查 git diff 和 worker 汇报",
            "运行建议验证命令",
            "验证通过后由主控/人工处理合并",
        ],
    }
    assert payload["automation_candidates"] == {
        "review_then_merge": [
            {
                "record_id": "managed-001",
                "name": "feature-a",
                "cwd": str(workspace),
                "branch": "supervisor/feature-a-12345678",
                "recommendation": "review_then_merge_candidate",
                "risk_level": "medium",
                "reason": "worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。",
                "reasons": [
                    "worker 汇报 done",
                    "存在 2 个改动路径",
                    "包含未跟踪文件",
                    "需要先运行建议验证命令",
                ],
                "next_actions": [
                    "审查 git diff 和 worker 汇报",
                    "运行建议验证命令",
                    "验证通过后由主控/人工处理合并",
                ],
                "validation_commands": item["validation_commands"],
                "test_status": "passed",
                "test_passed": True,
                "test_exit_code": 0,
                "test_output_tail": "12 passed in 0.34s",
                "reviewer_command": item["reviewer"]["command"],
            }
        ],
        "continue_or_split": [],
        "archive_or_wait": [],
        "recover_or_archive": [],
    }

    plain = render_worker_review_plain(payload)
    assert "决策汇总：合并候选 1 / 继续拆任务 0 / 缺失 worktree 0 / 需 fresh review 1" in plain
    assert "Fresh Codex 复查建议：" in plain
    assert "下一步决策：worker 已完成且有本地改动；建议先复查 diff 并跑验证，通过后再人工合并。" in plain
    assert "决策标记：适合合并：是 / 继续拆任务：否 / 风险：medium" in plain
    assert item["reviewer"]["command"] in plain


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
    assert item["reviewer"]["needed"] is False
    assert item["reviewer"]["reason"] == "cwd/worktree 缺失，无法生成可执行复查建议"
    assert item["next_decision"]["recommendation"] == "recover_or_archive_missing_worktree"
    assert item["next_decision"]["merge_suitable"] is False
    assert item["next_decision"]["continue_or_split_task"] is False
    assert payload["automation_candidates"]["recover_or_archive"] == [
        {
            "record_id": "managed-002",
            "name": "gone",
            "cwd": str(missing_workspace),
            "branch": "supervisor/gone-12345678",
            "recommendation": "recover_or_archive_missing_worktree",
            "risk_level": "high",
            "reason": "worker worktree 缺失；先确认分支和登记表，再决定恢复或归档。",
            "reasons": ["worker 汇报 done"],
            "next_actions": [
                "运行 git worktree list --porcelain",
                "确认 worker 分支是否仍存在",
                "人工决定恢复 worktree 或归档登记",
            ],
            "validation_commands": [
                f"test -d {missing_workspace}",
                "git worktree list --porcelain",
            ],
            "test_status": "skipped",
            "test_passed": None,
            "test_exit_code": None,
            "test_output_tail": "cwd/worktree 缺失，跳过 pytest。",
            "reviewer_command": None,
        }
    ]


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
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        check = kwargs["check"]
        text = kwargs["text"]
        capture_output = kwargs["capture_output"]
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
    assert item["reviewer"]["needed"] is False
    assert item["reviewer"]["reason"] == "无本地改动，无需 fresh Codex 复查"
    assert item["next_decision"]["recommendation"] == "archive_or_wait"
    assert item["next_decision"]["merge_suitable"] is False
    assert payload["automation_candidates"]["archive_or_wait"][0]["record_id"] == "managed-003"


def test_supervisor_worker_review_ignores_status_protocol_prompt_template(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "template-12345678"
    workspace.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-004.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "Supervisor 状态汇报要求：",
                "SUPERVISOR_STATUS: working|done|blocked|needs_user",
                "SUPERVISOR_SUMMARY: 用一句中文说明当前状态",
                "SUPERVISOR_NEXT: 用一句中文说明建议下一步",
            ]
        ),
        encoding="utf-8",
    )
    _write_record(
        codex_home,
        record_id="managed-004",
        name="template",
        cwd=workspace,
        log_path=log_path,
        status="launched",
        pid=444,
    )

    def fake_run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        check = kwargs["check"]
        text = kwargs["text"]
        capture_output = kwargs["capture_output"]
        if command[3:] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "supervisor/template-12345678\n", "")
        if command[3:] in (["status", "--short"], ["diff", "--stat"]):
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command: {command}")

    payload = collect_worker_reviews(
        codex_home=codex_home,
        run=fake_run,
        process_checker=lambda pid: False,
    )

    item = payload["workers"][0]
    assert item["supervisor_protocol"] == {"status": None, "summary": None, "next": None}
    assert item["next_decision"]["recommendation"] == "archive_or_wait"


def test_supervisor_worker_review_decides_blocked_worker_should_continue_or_split(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = tmp_path / "repo" / ".worktrees" / "supervisor" / "blocked-12345678"
    workspace.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-005.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "SUPERVISOR_STATUS: blocked",
                "SUPERVISOR_SUMMARY: scope too broad for one worker.",
                "SUPERVISOR_NEXT: split tests and runner wiring into separate tasks.",
            ]
        ),
        encoding="utf-8",
    )
    _write_record(
        codex_home,
        record_id="managed-005",
        name="blocked",
        cwd=workspace,
        log_path=log_path,
        status="launched",
        pid=555,
    )

    def fake_run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        check = kwargs["check"]
        text = kwargs["text"]
        capture_output = kwargs["capture_output"]
        if command[3:] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "supervisor/blocked-12345678\n", "")
        if command[3:] == ["status", "--short"]:
            return subprocess.CompletedProcess(command, 0, " M tests/isotope/test_x.py\n", "")
        if command[3:] == ["diff", "--stat"]:
            return subprocess.CompletedProcess(command, 0, " tests/isotope/test_x.py | 2 ++\n", "")
        raise AssertionError(f"unexpected command: {command}")

    payload = collect_worker_reviews(
        codex_home=codex_home,
        run=fake_run,
        process_checker=lambda pid: False,
    )

    item = payload["workers"][0]

    assert item["next_decision"] == {
        "recommendation": "continue_or_split_task",
        "summary": "worker 未完成但已有改动；不适合合并，建议按汇报继续推进或拆成后续任务。",
        "merge_suitable": False,
        "continue_or_split_task": True,
        "risk_level": "high",
        "reasons": [
            "worker 汇报 blocked",
            "存在 1 个改动路径",
            "需要先运行建议验证命令",
        ],
        "next_actions": [
            "阅读 worker 的 SUPERVISOR_NEXT",
            "判断是否继续当前 worker 或拆出新任务",
            "暂不合并该 worktree",
        ],
    }
    assert payload["automation_candidates"]["continue_or_split"][0]["record_id"] == "managed-005"


def test_supervisor_worker_review_quotes_reviewer_command(tmp_path):
    codex_home = tmp_path / ".codex"
    workspace = (
        tmp_path
        / "repo with spaces"
        / ".worktrees"
        / "supervisor"
        / "feature-a;$(bad)-12345678"
    )
    workspace.mkdir(parents=True)
    log_path = codex_home / "supervisor" / "logs" / "managed-004.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("SUPERVISOR_STATUS: done\n", encoding="utf-8")
    _write_record(
        codex_home,
        record_id="managed-004",
        name="feature-a;$(bad)",
        cwd=workspace,
        log_path=log_path,
        status="launched",
        pid=444,
    )

    def fake_run(
        command: list[str],
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        check = kwargs["check"]
        text = kwargs["text"]
        capture_output = kwargs["capture_output"]
        if _is_pytest_gate_command(command):
            assert Path(kwargs["cwd"]) == workspace
            assert kwargs["env"]["PYTHONPATH"] == "src"
            return subprocess.CompletedProcess(command, 0, "12 passed in 0.34s\n", "")
        if command[3:] == ["rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(command, 0, str(workspace) + "\n", "")
        if command[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "supervisor/feature-a;$(bad)-12345678\n",
                "",
            )
        if command[3:] == ["status", "--short"]:
            return subprocess.CompletedProcess(command, 0, " M src/example.py\n", "")
        if command[3:] == ["diff", "--stat"]:
            return subprocess.CompletedProcess(
                command,
                0,
                " src/example.py | 1 +\n",
                "",
            )
        raise AssertionError(f"unexpected command: {command}")

    payload = collect_worker_reviews(
        codex_home=codex_home,
        run=fake_run,
        process_checker=lambda pid: False,
    )

    reviewer = payload["workers"][0]["reviewer"]

    assert reviewer["needed"] is True
    assert reviewer["command"] == (
        "codex exec -C "
        + shlex.quote(str(workspace))
        + " "
        + shlex.quote(reviewer["prompt"])
    )


def test_supervisor_worker_review_lightweight_limits_and_omits_heavy_fields(tmp_path):
    codex_home = tmp_path / ".codex"
    for index in range(45):
        workspace = (
            tmp_path
            / "repo"
            / ".worktrees"
            / "supervisor"
            / f"feature-{index:02d}-12345678"
        )
        workspace.mkdir(parents=True)
        log_path = codex_home / "supervisor" / "logs" / f"managed-{index:03d}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "\n".join(
                [
                    "SUPERVISOR_STATUS: done",
                    f"SUPERVISOR_SUMMARY: feature {index} done.",
                    "SUPERVISOR_NEXT: wait for integration.",
                ]
            ),
            encoding="utf-8",
        )
        _write_record(
            codex_home,
            record_id=f"managed-{index:03d}",
            name=f"feature-{index:02d}",
            cwd=workspace,
            log_path=log_path,
            status="launched",
            pid=1000 + index,
        )

    def fail_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"lightweight mode should not run commands: {command}")

    payload = collect_worker_reviews(
        codex_home=codex_home,
        lightweight=True,
        run=fail_run,
        process_checker=lambda pid: False,
    )

    assert payload["summary"] == {
        "total": 45,
        "visible": 40,
        "hidden_by_lightweight_limit": 5,
        "existing_cwd": 45,
        "missing_cwd": 0,
    }
    assert len(payload["workers"]) == 40
    assert payload["workers"][0]["record_id"] == "managed-005"
    assert payload["workers"][-1]["record_id"] == "managed-044"
    for worker in payload["workers"]:
        assert "prompt" not in worker
        assert "validation_commands" not in worker
        assert "command" not in worker["reviewer"]
        assert worker["test_status"] == "skipped"
        assert worker["changes"] == {
            "status": "unknown",
            "summary": "loop 快速状态未读取 diff",
        }
    for candidates in payload["automation_candidates"].values():
        for candidate in candidates:
            assert "validation_commands" not in candidate
            assert "reviewer_command" not in candidate


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


def _is_pytest_gate_command(command: list[str]) -> bool:
    return (
        command[1:] == ["-m", "pytest", "tests/isotope", "-q"]
        and command[0] in {".venv/bin/python", sys.executable}
    )
