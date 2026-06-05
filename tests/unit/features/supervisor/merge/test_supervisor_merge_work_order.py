from __future__ import annotations

import json

from isotope.features.supervisor.planner.merge_work_order import build_merge_work_order_prompt
from isotope.features.supervisor.runner import main as supervisor_main


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
    assert "excluded_workers 仅用于报告原因" in prompt


def test_merge_work_order_prompt_keeps_branch_and_history_safety_rules():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "worker 分支、base 分支、来源分支、worktree、Git 历史和工作目录保持原状" in prompt
    assert "force push、reset --hard、rebase 已共享分支或重写远端历史属于本工单外动作" in prompt
    assert "遇到 conflict、测试失败、CI 失败或权限不足时汇报 blocked" in prompt
    assert "cleanup 仅归档 Supervisor 账本" in prompt


def test_merge_work_order_prompt_requires_ci_watch_result_writeback():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "CI run id" in prompt
    assert "CI conclusion" in prompt
    assert "CI 通过后汇报 SUPERVISOR_STATUS: done" in prompt
    assert "触发 cleanup 归档" in prompt
    assert "CI 失败时保留当前 merge worktree" in prompt
    assert "SUPERVISOR_SUMMARY" in prompt
    assert "SUPERVISOR_NEXT" in prompt
    assert "CI 失败时" in prompt


def test_merge_work_order_prompt_requires_automatic_ci_verification_after_push():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "git rev-parse --abbrev-ref HEAD" in prompt
    assert "git rev-parse HEAD" in prompt
    assert (
        'gh run list --workflow CI --branch "$CURRENT_BRANCH" --commit "$HEAD_SHA"'
        in prompt
    )
    assert "gh run watch CI_RUN_ID --exit-status" in prompt
    assert "gh run view CI_RUN_ID" in prompt
    assert "CI run 缺失" in prompt
    assert "CI conclusion 非 success" in prompt


def test_merge_work_order_prompt_requires_ci_failure_reason_and_stop():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "gh run view CI_RUN_ID --log-failed" in prompt
    assert "测试失败、lint 错误、安装失败或 workflow 配置错误" in prompt
    assert "rerun CI、再次 push 和重复尝试留给后续明确工单" in prompt
    assert "SUPERVISOR_STATUS: blocked" in prompt


def test_merge_work_order_prompt_requires_ci_timeout_stop():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "最多等待 30 分钟" in prompt
    assert "CI timeout" in prompt
    assert "超过 30 分钟" in prompt
    assert "汇报 blocked" in prompt


def test_merge_work_order_prompt_handles_empty_ready_group():
    payload = _integration_review_payload()
    payload["groups"]["ready_to_integrate"] = []
    payload["summary"]["ready_to_integrate"] = 0

    prompt = build_merge_work_order_prompt(payload)

    assert "ready_workers: 0" in prompt
    assert "没有 ready_to_integrate worker；cherry-pick/push 路径无候选" in prompt
    assert "SUPERVISOR_STATUS: needs_user|blocked|done" in prompt


def test_merge_work_order_prompt_uses_execution_protocol_language():
    prompt = build_merge_work_order_prompt(_integration_review_payload())

    assert "forbidden_scope" not in prompt
    assert "禁止" not in prompt
    assert "不要" not in prompt
    assert "不能" not in prompt
    assert "只" + "读" not in prompt
    assert "只" + "生成" not in prompt
    assert "工单" + "文本" not in prompt
    assert "停止并汇报" not in prompt
    assert "自动解决大范围冲突" not in prompt


def test_supervisor_merge_work_order_cli_prints_plain_prompt(capsys, monkeypatch):
    calls = []

    def stub_collect_integration_reviews(
        *, codex_home, base_ref, include_unfinished, **kwargs
    ):
        calls.append(
            {
                "codex_home": str(codex_home),
                "base_ref": base_ref,
                "include_unfinished": include_unfinished,
            }
        )
        return _integration_review_payload()

    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        stub_collect_integration_reviews,
    )

    exit_code = supervisor_main(
        [
            "merge-work-order",
            "--codex-home",
            "/tmp/test-codex-home",
            "--base",
            "main",
        ]
    )

    assert exit_code == 0
    text = capsys.readouterr().out
    assert text.startswith("WORK ORDER\n")
    assert "source: supervisor integration-review payload" in text
    assert "ready-one / managed-ready" in text
    assert calls == [
        {
            "codex_home": "/tmp/test-codex-home",
            "base_ref": "main",
            "include_unfinished": False,
        }
    ]


def test_supervisor_merge_work_order_cli_json_includes_status_summary_and_prompt(
    capsys,
    monkeypatch,
):
    monkeypatch.setattr(
        "isotope.features.supervisor.runner.collect_integration_reviews",
        lambda *, codex_home, base_ref, include_unfinished, **kwargs: _integration_review_payload(),
    )

    exit_code = supervisor_main(
        [
            "merge-work-order",
            "--codex-home",
            "/tmp/test-codex-home",
            "--base",
            "main",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["summary"]["ready_to_integrate"] == 1
    assert payload["prompt"].startswith("WORK ORDER\n")
    assert "ready-one / managed-ready" in payload["prompt"]


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
                    "reason": "merge-tree 检查检测到 conflict；需要人工 rebase/merge 处理。",
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
