from __future__ import annotations

import json

from isotope.features.supervisor.replan import (
    build_supervisor_replan,
    render_supervisor_replan_plain,
)
from isotope.features.supervisor.runner import main as supervisor_main


def test_supervisor_replan_turns_worker_review_candidates_into_read_only_advice():
    worker_reviews = {
        "automation_candidates": {
            "review_then_merge": [
                {
                    "record_id": "managed-001",
                    "name": "merge-ready",
                    "cwd": "/repo/.worktrees/supervisor/merge-ready",
                    "branch": "supervisor/merge-ready",
                    "risk_level": "medium",
                    "reason": "worker 已完成且有本地改动。",
                    "next_actions": ["审查 git diff", "运行建议验证命令"],
                    "validation_commands": ["git status --short --branch"],
                    "reviewer_command": "codex exec -C /repo review",
                }
            ],
            "continue_or_split": [
                {
                    "record_id": "managed-002",
                    "name": "blocked-lane",
                    "cwd": "/repo/.worktrees/supervisor/blocked-lane",
                    "branch": "supervisor/blocked-lane",
                    "risk_level": "high",
                    "reason": "worker 未完成但已有改动。",
                    "next_actions": ["阅读 worker 的 SUPERVISOR_NEXT"],
                    "validation_commands": ["pytest tests/unit/test_x.py -q"],
                    "reviewer_command": "codex exec -C /repo inspect",
                }
            ],
            "archive_or_wait": [
                {
                    "record_id": "managed-003",
                    "name": "clean-lane",
                    "cwd": "/repo/.worktrees/supervisor/clean-lane",
                    "branch": "supervisor/clean-lane",
                    "risk_level": "low",
                    "reason": "worker 没有本地改动。",
                    "next_actions": ["检查 worker 状态协议和日志"],
                }
            ],
            "recover_or_archive": [
                {
                    "record_id": "managed-004",
                    "name": "gone-lane",
                    "cwd": "/repo/.worktrees/supervisor/gone-lane",
                    "branch": "supervisor/gone-lane",
                    "risk_level": "high",
                    "reason": "worker worktree 缺失。",
                    "next_actions": ["运行 git worktree list --porcelain"],
                }
            ],
        },
        "safety": {"auto_merge": False, "delete_branch": False},
    }
    active_goals = [
        {
            "goal_id": "goal-001",
            "target_name": "merge-ready",
            "goal": "完成可合并 worker。",
            "last_status": "done",
        },
        {
            "goal_id": "goal-002",
            "target_name": "blocked-lane",
            "goal": "继续处理阻塞 worker。",
            "last_status": "blocked",
        },
    ]

    payload = build_supervisor_replan(
        worker_reviews=worker_reviews,
        active_goals=active_goals,
    )

    assert payload["status"] == "ok"
    assert payload["summary"] == {
        "total": 4,
        "review_then_merge": 1,
        "continue_or_split": 1,
        "archive_or_wait": 1,
        "recover_or_archive": 1,
        "active_goals": 2,
    }
    assert payload["safety"] == {
        "read_only": True,
        "auto_merge": False,
        "auto_archive": False,
        "delete_branch": False,
        "note": "只生成下一轮建议，不自动合并、不自动归档、不删除 worktree 或分支。",
    }
    kinds = [item["kind"] for item in payload["recommendations"]]
    assert kinds == [
        "review_then_merge",
        "continue_or_split",
        "archive_or_wait",
        "recover_or_archive",
    ]

    merge_advice = payload["recommendations"][0]
    assert merge_advice["label"] == "复查合并"
    assert merge_advice["target_name"] == "merge-ready"
    assert merge_advice["goal"] == {
        "goal_id": "goal-001",
        "target_name": "merge-ready",
        "goal": "完成可合并 worker。",
        "last_status": "done",
    }
    assert merge_advice["read_only"] is True
    assert "不自动合并" in merge_advice["guardrail"]
    assert merge_advice["next_actions"] == [
        "审查 git diff",
        "运行建议验证命令",
    ]

    assert payload["recommendations"][1]["label"] == "继续拆分"
    assert payload["recommendations"][2]["label"] == "归档等待"
    assert payload["recommendations"][3]["label"] == "恢复/归档"


def test_supervisor_replan_reports_active_goals_without_worker_candidates():
    payload = build_supervisor_replan(
        worker_reviews={"automation_candidates": {}},
        active_goals=[
            {
                "goal_id": "goal-010",
                "target_name": "queued-worker",
                "goal": "继续队列里的目标。",
                "last_status": "working",
                "last_next": "等待 worker 汇报。",
            }
        ],
    )

    assert payload["summary"]["total"] == 1
    assert payload["recommendations"] == [
        {
            "kind": "continue_or_split",
            "label": "继续拆分",
            "record_id": None,
            "name": "queued-worker",
            "target_name": "queued-worker",
            "goal": {
                "goal_id": "goal-010",
                "target_name": "queued-worker",
                "goal": "继续队列里的目标。",
                "last_status": "working",
                "last_next": "等待 worker 汇报。",
            },
            "cwd": None,
            "branch": None,
            "risk_level": "medium",
            "reason": "active goal 仍在队列中，但 worker-review 没有对应候选；建议继续观察、恢复 worker 或拆出下一轮任务。",
            "next_actions": [
                "检查 active goal 最近状态",
                "确认是否已有对应 worker 在运行",
                "必要时继续推进或拆出下一轮 worker",
            ],
            "validation_commands": [],
            "reviewer_command": None,
            "read_only": True,
            "guardrail": "只提出继续/拆分建议；不自动启动、不自动归档、不自动合并。",
        }
    ]


def test_supervisor_replan_turns_integration_review_groups_into_next_advice():
    integration_reviews = {
        "status": "ok",
        "base_ref": "main",
        "summary": {
            "total": 4,
            "ready_to_integrate": 1,
            "already_integrated": 1,
            "needs_review": 1,
            "conflict_risk": 1,
        },
        "groups": {
            "ready_to_integrate": [
                {
                    "record_id": "managed-ready",
                    "name": "ready-worker",
                    "cwd": "/repo/.worktrees/supervisor/ready-worker",
                    "branch": "supervisor/ready-worker",
                    "worker_commit": "ready111",
                    "base_ref": "main",
                    "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
                }
            ],
            "already_integrated": [
                {
                    "record_id": "managed-done",
                    "name": "done-worker",
                    "cwd": "/repo/.worktrees/supervisor/done-worker",
                    "branch": "supervisor/done-worker",
                    "worker_commit": "done222",
                    "base_ref": "main",
                    "reason": "main 已包含 worker HEAD；可检查后归档。",
                }
            ],
            "needs_review": [
                {
                    "record_id": "managed-review",
                    "name": "review-worker",
                    "cwd": "/repo/.worktrees/supervisor/review-worker",
                    "branch": "supervisor/review-worker",
                    "worker_commit": "review333",
                    "base_ref": "main",
                    "reason": "worker worktree 仍有未提交改动；先复查并要求 worker 提交。",
                }
            ],
            "conflict_risk": [
                {
                    "record_id": "managed-conflict",
                    "name": "conflict-worker",
                    "cwd": "/repo/.worktrees/supervisor/conflict-worker",
                    "branch": "supervisor/conflict-worker",
                    "worker_commit": "conflict444",
                    "base_ref": "main",
                    "reason": "只读 merge-tree 检测到 conflict；需要人工 rebase/merge 处理。",
                }
            ],
        },
        "safety": {"auto_merge": False, "push": False, "delete_branch": False},
    }

    payload = build_supervisor_replan(
        worker_reviews={"automation_candidates": {}},
        integration_reviews=integration_reviews,
        active_goals=[],
    )

    assert payload["summary"] == {
        "total": 4,
        "review_then_merge": 1,
        "continue_or_split": 1,
        "archive_or_wait": 1,
        "recover_or_archive": 1,
        "active_goals": 0,
        "ready_to_integrate": 1,
        "already_integrated": 1,
        "needs_review": 1,
        "conflict_risk": 1,
        "merge_candidates": 1,
    }
    kinds = [item["kind"] for item in payload["recommendations"]]
    assert kinds == [
        "review_then_merge",
        "archive_or_wait",
        "continue_or_split",
        "recover_or_archive",
    ]
    ready = payload["recommendations"][0]
    assert ready["integration_group"] == "ready_to_integrate"
    assert ready["worker_commit"] == "ready111"
    assert ready["dynamic_codex_candidate"] is True
    assert ready["next_actions"] == [
        "交给动态 Codex worker 做最终 diff/test 复查",
        "复查通过后由主控或人工执行 merge",
        "merge 后再次运行 integration-review 确认 main 已包含 worker HEAD",
    ]
    assert payload["merge_candidates"] == [
        {
            "record_id": "managed-ready",
            "name": "ready-worker",
            "target_name": "ready-worker",
            "cwd": "/repo/.worktrees/supervisor/ready-worker",
            "branch": "supervisor/ready-worker",
            "worker_commit": "ready111",
            "base_ref": "main",
            "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
            "handoff": "dynamic_codex_worker",
            "read_only": True,
        }
    ]


def test_supervisor_replan_plain_output_keeps_safety_visible():
    payload = build_supervisor_replan(
        worker_reviews={
            "automation_candidates": {
                "review_then_merge": [
                    {
                        "record_id": "managed-001",
                        "name": "merge-ready",
                        "reason": "worker 已完成且有本地改动。",
                    }
                ]
            }
        },
        active_goals=[],
    )

    text = render_supervisor_replan_plain(payload)

    assert "[Supervisor Replan]" in text
    assert "总建议：1 / 复查合并 1 / 继续拆分 0 / 归档等待 0 / 恢复/归档 0 / active goals 0" in text
    assert "安全：只生成下一轮建议，不自动合并、不自动归档、不删除 worktree 或分支。" in text
    assert "复查合并：merge-ready / managed-001" in text


def test_supervisor_replan_plain_output_prints_integration_merge_candidates():
    payload = build_supervisor_replan(
        worker_reviews={"automation_candidates": {}},
        integration_reviews={
            "summary": {
                "ready_to_integrate": 1,
                "already_integrated": 0,
                "needs_review": 0,
                "conflict_risk": 0,
            },
            "groups": {
                "ready_to_integrate": [
                    {
                        "record_id": "managed-ready",
                        "name": "ready-worker",
                        "cwd": "/repo/.worktrees/supervisor/ready-worker",
                        "branch": "supervisor/ready-worker",
                        "worker_commit": "ready111",
                        "base_ref": "main",
                        "reason": "ready",
                    }
                ]
            },
        },
        active_goals=[],
    )

    text = render_supervisor_replan_plain(payload)

    assert "integration：ready_to_integrate 1 / already_integrated 0 / needs_review 0 / conflict_risk 0" in text
    assert "可交给动态 Codex worker 的合并候选：" in text
    assert "ready-worker / managed-ready / supervisor/ready-worker @ ready111" in text


def test_supervisor_replan_cli_json_turns_worker_review_candidates_into_advice(
    tmp_path,
    capsys,
    monkeypatch,
):
    worker_reviews = {
        "status": "ok",
        "automation_candidates": {
            "review_then_merge": [
                {
                    "record_id": "managed-011",
                    "name": "ready-worker",
                    "reason": "worker 已完成且有本地改动。",
                    "next_actions": ["审查 diff", "运行 pytest"],
                }
            ]
        },
        "safety": {"auto_merge": False},
    }
    active_goals = [
        {
            "goal_id": "goal-011",
            "target_name": "ready-worker",
            "worker_session_id": "managed:managed-011",
        }
    ]
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_worker_reviews",
        lambda *, codex_home, **kwargs: worker_reviews,
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._active_goal_dicts",
        lambda args, **kwargs: active_goals,
    )

    exit_code = supervisor_main(
        ["replan", "--codex-home", str(tmp_path / ".codex"), "--json"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["summary"]["review_then_merge"] == 1
    assert payload["recommendations"][0]["target_name"] == "ready-worker"
    assert payload["recommendations"][0]["read_only"] is True
    assert payload["safety"]["auto_merge"] is False


def test_supervisor_replan_cli_json_reads_integration_review_candidates(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_worker_reviews",
        lambda *, codex_home, **kwargs: {"automation_candidates": {}},
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: {
            "summary": {
                "ready_to_integrate": 1,
                "already_integrated": 0,
                "needs_review": 0,
                "conflict_risk": 0,
            },
            "groups": {
                "ready_to_integrate": [
                    {
                        "record_id": "managed-ready",
                        "name": "ready-worker",
                        "cwd": "/repo/.worktrees/supervisor/ready-worker",
                        "branch": "supervisor/ready-worker",
                        "worker_commit": "ready111",
                        "base_ref": base_ref,
                        "reason": "ready",
                    }
                ]
            },
        },
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._active_goal_dicts",
        lambda args, **kwargs: [],
    )

    exit_code = supervisor_main(
        [
            "replan",
            "--codex-home",
            str(tmp_path / ".codex"),
            "--base",
            "main",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["ready_to_integrate"] == 1
    assert payload["summary"]["merge_candidates"] == 1
    assert payload["merge_candidates"][0]["record_id"] == "managed-ready"
    assert payload["recommendations"][0]["dynamic_codex_candidate"] is True


def test_supervisor_replan_cli_plain_prints_read_only_advice(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_worker_reviews",
        lambda *, codex_home, **kwargs: {
            "automation_candidates": {
                "continue_or_split": [
                    {
                        "record_id": "managed-012",
                        "name": "blocked-worker",
                        "reason": "worker 汇报 blocked。",
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        "isotope.features.supervisor.runner._active_goal_dicts",
        lambda args, **kwargs: [],
    )

    exit_code = supervisor_main(["replan", "--codex-home", str(tmp_path / ".codex")])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "[Supervisor Replan]" in text
    assert "继续拆分：blocked-worker / managed-012" in text
    assert "安全：只生成下一轮建议，不自动合并、不自动归档、不删除 worktree 或分支。" in text
