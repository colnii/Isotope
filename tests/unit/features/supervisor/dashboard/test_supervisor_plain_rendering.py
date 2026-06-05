from __future__ import annotations

from typing import Any

from isotope.features.supervisor.commands.plain_rendering import (
    print_advice_llm_action_plain,
    print_supervise_plain,
)


class _StubApi:
    def _dashboard_payload(self, report: Any, *, decision_requests: list[dict[str, Any]]):
        return {"report": report, "decision_requests": decision_requests}

    def _print_dashboard_plain(self, payload: dict[str, Any]) -> None:
        print("[dashboard]")

    def _is_merge_dispatch_launch_action(self, action: dict[str, Any]) -> bool:
        return False


def test_supervise_plain_prints_worker_lifecycle_summary(capsys):
    payload = {
        "automation": {"ready": True, "reason": "ready"},
        "recommendation": {"label": "继续监控", "action": "monitor"},
        "worker_lifecycle_decision": {
            "stage": "archived",
            "next_step": "cleanup_worktree",
            "policy": {
                "policy_status": "program_resolved",
                "program_action": "archive_integrated",
                "remaining_step": "cleanup_worktree",
                "blocked_reason": None,
            },
            "timeline": [
                {
                    "stage": "integrated",
                    "action": "archive_integrated",
                    "status": "observed",
                    "executed": False,
                },
                {
                    "stage": "archived",
                    "action": "archive_integrated",
                    "status": "executed",
                    "executed": True,
                },
            ],
        },
    }

    print_supervise_plain(payload, report=object(), api=_StubApi())

    text = capsys.readouterr().out
    assert "[Worker 生命周期]" in text
    assert "stage=archived next_step=cleanup_worktree policy=program_resolved" in text
    assert "remaining_step=cleanup_worktree" in text
    assert "timeline: integrated/archive_integrated observed; archived/archive_integrated executed" in text


def test_supervise_plain_prints_lifecycle_action_route(capsys):
    payload = {
        "automation": {"ready": True, "reason": "ready"},
        "recommendation": {"label": "继续监控", "action": "monitor"},
        "llm_action": {
            "kind": "cleanup_worktree",
            "source": "worker_lifecycle",
            "decision_source": "worker_lifecycle_execution",
            "routing_reason": (
                "program-owned lifecycle execution recommended delete_ready"
            ),
            "recommended_next_step": "delete_ready",
        },
    }

    print_supervise_plain(payload, report=object(), api=_StubApi())

    text = capsys.readouterr().out
    assert "[程序路由动作]" in text
    assert "[LLM 白名单动作]" not in text
    assert "cleanup_worktree / recommended_next_step=delete_ready" in text
    assert "动作来源：worker_lifecycle_execution" in text
    assert (
        "路由原因：program-owned lifecycle execution recommended delete_ready"
        in text
    )


def test_supervise_plain_prefers_supervisor_action_alias(capsys):
    payload = {
        "automation": {"ready": True, "reason": "ready"},
        "recommendation": {"label": "继续监控", "action": "monitor"},
        "llm_action": {"kind": "monitor", "reason": "legacy"},
        "supervisor_action": {"kind": "send_status", "reason": "neutral"},
    }

    print_supervise_plain(payload, report=object(), api=_StubApi())

    text = capsys.readouterr().out
    assert "[Supervisor 白名单动作]" in text
    assert "[LLM 白名单动作]" not in text
    assert "send_status / neutral" in text
    assert "monitor / legacy" not in text


def test_supervise_plain_prefers_supervisor_followup_action_alias(capsys):
    payload = {
        "automation": {"ready": True, "reason": "ready"},
        "recommendation": {"label": "继续监控", "action": "monitor"},
        "llm_followup_action": {"kind": "monitor", "reason": "legacy followup"},
        "supervisor_followup_action": {
            "kind": "send_status",
            "reason": "neutral followup",
        },
    }

    print_supervise_plain(payload, report=object(), api=_StubApi())

    text = capsys.readouterr().out
    assert "[Supervisor 同轮后续动作]" in text
    assert "[LLM 同轮后续动作]" not in text
    assert "send_status / neutral followup" in text
    assert "monitor / legacy followup" not in text


def test_advice_plain_labels_model_action_as_supervisor(capsys):
    print_advice_llm_action_plain(
        {
            "kind": "monitor",
            "reason": "still running",
        }
    )

    text = capsys.readouterr().out
    assert "Supervisor 动作：monitor" in text
    assert "Supervisor 原因：still running" in text
    assert "LLM 动作：monitor" not in text
    assert "LLM 原因：still running" not in text


def test_advice_plain_labels_routed_action_as_program(capsys):
    print_advice_llm_action_plain(
        {
            "kind": "cleanup_worktree",
            "decision_source": "worker_lifecycle_execution",
            "routing_reason": (
                "program-owned lifecycle execution recommended delete_ready"
            ),
            "recommended_next_step": "delete_ready",
        }
    )

    text = capsys.readouterr().out
    assert "程序路由动作：cleanup_worktree" in text
    assert "程序路由原因：recommended_next_step=delete_ready" in text
    assert "动作来源：worker_lifecycle_execution" in text
    assert (
        "路由原因：program-owned lifecycle execution recommended delete_ready"
        in text
    )
