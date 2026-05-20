from __future__ import annotations

from isotope.features.supervisor.merge_work_order import build_merge_work_order_prompt


def test_merge_work_order_prompt_lists_ready_workers_and_review_steps():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert prompt.startswith("WORK ORDER\n")
    assert "source: supervisor integration-review payload" in prompt
    assert "base_ref: main" in prompt
    assert "ready-one / managed-ready" in prompt
    assert "supervisor/ready-12345678 @ ready111" in prompt
    assert "cwd: /repo/.worktrees/supervisor/ready-12345678" in prompt
    assert "diff review" in prompt
    assert "cherry-pick" in prompt
    assert "组合测试" in prompt
    assert "push" in prompt
    assert "CI watch" in prompt


def test_merge_work_order_prompt_excludes_non_ready_workers_from_merge_plan():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "excluded_workers:" in prompt
    assert "conflict-one / managed-conflict [conflict_risk]" in prompt
    assert "review-one / managed-review [needs_review]" in prompt
    assert "done-one / managed-done [already_integrated]" in prompt
    assert "不要 cherry-pick excluded_workers" in prompt


def test_merge_work_order_prompt_keeps_branch_and_history_safety_rules():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "禁止删除 worker 分支、base 分支或 worktree" in prompt
    assert "禁止 force push、reset --hard、rebase 已共享分支或重写远端历史" in prompt
    assert "遇到 conflict、测试失败、CI 失败或权限不足时停止并汇报 blocked" in prompt
    assert "不主动归档、不清理、不删除来源分支" in prompt


def test_merge_work_order_prompt_handles_empty_ready_group():
    payload = _integration_review_payload()
    payload["groups"]["ready_to_integrate"] = []
    payload["summary"]["ready_to_integrate"] = 0

    prompt = build_merge_work_order_prompt(payload)

    assert "ready_workers: 0" in prompt
    assert "没有 ready_to_integrate worker；不要执行 cherry-pick/push" in prompt
    assert "SUPERVISOR_STATUS: needs_user|blocked|done" in prompt


def _integration_review_payload() -> dict[str, object]:
    return {
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
                    "name": "ready-one",
                    "cwd": "/repo/.worktrees/supervisor/ready-12345678",
                    "branch": "supervisor/ready-12345678",
                    "worker_commit": "ready111",
                    "base_ref": "main",
                    "reason": "worker 已完成、分支干净、main 尚未包含且未检测到 merge conflict。",
                    "dirty": False,
                    "merge_conflict": False,
                }
            ],
            "conflict_risk": [
                {
                    "record_id": "managed-conflict",
                    "name": "conflict-one",
                    "cwd": "/repo/.worktrees/supervisor/conflict-12345678",
                    "branch": "supervisor/conflict-12345678",
                    "worker_commit": "conflict111",
                    "reason": "只读 merge-tree 检测到 conflict；需要人工 rebase/merge 处理。",
                }
            ],
            "needs_review": [
                {
                    "record_id": "managed-review",
                    "name": "review-one",
                    "cwd": "/repo/.worktrees/supervisor/review-12345678",
                    "branch": "supervisor/review-12345678",
                    "worker_commit": "review111",
                    "reason": "worker 未汇报 done；先按 SUPERVISOR_NEXT 继续或拆分。",
                }
            ],
            "already_integrated": [
                {
                    "record_id": "managed-done",
                    "name": "done-one",
                    "cwd": "/repo/.worktrees/supervisor/done-12345678",
                    "branch": "supervisor/done-12345678",
                    "worker_commit": "done111",
                    "reason": "main 已包含 worker HEAD；可检查后归档。",
                }
            ],
        },
        "safety": {
            "auto_merge": False,
            "push": False,
            "delete_branch": False,
        },
    }
