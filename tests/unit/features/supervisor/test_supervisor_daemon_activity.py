from __future__ import annotations

from isotope.features.supervisor.commands.daemon_command import (
    daemon_activity_payload,
    print_daemon_activity_plain,
    recent_llm_action_from_log,
    recent_supervisor_action_from_log,
)


class _StubApi:
    MERGE_DISPATCH_TARGET_NAME = "merge-dispatch"

    def _sync_managed_worker_failures(self, **kwargs) -> None:
        return None

    def collect_integration_reviews(self, **kwargs) -> dict:
        return {"status": "ok", "summary": {}}


def test_recent_supervisor_action_from_log_reads_legacy_llm_header() -> None:
    assert recent_supervisor_action_from_log(
        "[LLM 白名单动作]\n"
        "monitor / still running\n"
        "已跳过：still running\n"
    ) == {"kind": "monitor", "reason": "still running"}


def test_recent_supervisor_action_from_log_reads_supervisor_header() -> None:
    assert recent_supervisor_action_from_log(
        "[Supervisor 白名单动作]\n"
        "monitor / still running\n"
        "已跳过：still running\n"
    ) == {"kind": "monitor", "reason": "still running"}


def test_recent_supervisor_action_from_log_reads_program_route_header() -> None:
    assert recent_supervisor_action_from_log(
        "[程序路由动作]\n"
        "cleanup_worktree / recommended_next_step=delete_ready\n"
        "动作来源：worker_lifecycle_execution\n"
    ) == {
        "kind": "cleanup_worktree",
        "reason": "recommended_next_step=delete_ready",
    }


def test_recent_llm_action_from_log_wraps_supervisor_parser() -> None:
    text = (
        "[Supervisor 白名单动作]\n"
        "monitor / still running\n"
        "已跳过：still running\n"
    )

    assert recent_llm_action_from_log(text) == recent_supervisor_action_from_log(text)


def test_print_daemon_activity_labels_recent_action_as_supervisor(capsys) -> None:
    print_daemon_activity_plain(
        {
            "recent_llm_action": {
                "kind": "monitor",
                "reason": "still running",
            }
        }
    )

    text = capsys.readouterr().out
    assert "Supervisor 动作：monitor / still running" in text
    assert "LLM 动作：monitor / still running" not in text


def test_print_daemon_activity_prefers_recent_supervisor_action_alias(capsys) -> None:
    print_daemon_activity_plain(
        {
            "recent_supervisor_action": {
                "kind": "send_status",
                "reason": "neutral",
            },
            "recent_llm_action": {
                "kind": "monitor",
                "reason": "legacy",
            },
        }
    )

    text = capsys.readouterr().out
    assert "Supervisor 动作：send_status / neutral" in text
    assert "monitor / legacy" not in text


def test_daemon_activity_payload_exposes_recent_supervisor_action_alias(tmp_path) -> None:
    codex_home = tmp_path / ".codex"
    log_path = codex_home / "supervisor" / "logs" / "daemon.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "[Supervisor 白名单动作]\n"
        "monitor / still running\n"
        "已跳过：still running\n",
        encoding="utf-8",
    )

    activity = daemon_activity_payload(
        codex_home,
        {
            "status": "running",
            "log_path": str(log_path),
            "command": ["isotope-supervisor", "loop"],
        },
        api=_StubApi(),
    )

    assert activity["recent_supervisor_action"] == {
        "kind": "monitor",
        "reason": "still running",
    }
    assert activity["recent_llm_action"] == activity["recent_supervisor_action"]
