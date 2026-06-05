from __future__ import annotations

from isotope.features.supervisor.commands.daemon_command import (
    print_daemon_activity_plain,
    recent_llm_action_from_log,
)


def test_recent_action_from_log_reads_legacy_llm_header() -> None:
    assert recent_llm_action_from_log(
        "[LLM 白名单动作]\n"
        "monitor / still running\n"
        "已跳过：still running\n"
    ) == {"kind": "monitor", "reason": "still running"}


def test_recent_action_from_log_reads_supervisor_header() -> None:
    assert recent_llm_action_from_log(
        "[Supervisor 白名单动作]\n"
        "monitor / still running\n"
        "已跳过：still running\n"
    ) == {"kind": "monitor", "reason": "still running"}


def test_recent_action_from_log_reads_program_route_header() -> None:
    assert recent_llm_action_from_log(
        "[程序路由动作]\n"
        "cleanup_worktree / recommended_next_step=delete_ready\n"
        "动作来源：worker_lifecycle_execution\n"
    ) == {
        "kind": "cleanup_worktree",
        "reason": "recommended_next_step=delete_ready",
    }


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
