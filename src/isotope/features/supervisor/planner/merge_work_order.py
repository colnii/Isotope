"""Build merge work order prompts from Supervisor integration reviews."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

NON_READY_GROUPS = (
    "conflict_risk",
    "needs_review",
    "already_integrated",
)


def build_merge_work_order_prompt(payload: Mapping[str, Any]) -> str:
    """Render a prompt for a dynamic Codex worker to merge ready workers."""
    base_ref = str(payload.get("base_ref") or "main").strip() or "main"
    groups = _mapping(payload.get("groups"))
    ready_workers = _items(groups.get("ready_to_integrate"))
    summary = _mapping(payload.get("summary"))

    lines = [
        "WORK ORDER",
        "source: supervisor integration-review payload",
        f"goal: 将 ready_to_integrate worker 审查后合入 {base_ref}，并跟踪 push 后 CI 结果。",
        f"base_ref: {base_ref}",
        f"ready_workers: {len(ready_workers)}",
        "execution_scope: 处理下面 merge_candidates 对应的 worker commit 和必要组合测试修复。",
        (
            "protected_scope: worker 分支、base 分支、来源分支、worktree、Git 历史"
            "和工作目录保持原状；force push、reset --hard、rebase 已共享分支"
            "或重写远端历史属于本工单外动作；cleanup 仅归档 Supervisor 账本。"
        ),
        (
            "execution_note: integration-review 是投影 payload；本工单允许动态 worker "
            "按步骤人工复查后执行合并，builder 模块只生成工单文本。"
        ),
    ]

    lines.extend(_summary_lines(summary))
    lines.extend(_ready_worker_lines(ready_workers))
    lines.extend(_excluded_worker_lines(groups))
    lines.extend(_execution_steps(base_ref=base_ref, ready_workers=ready_workers))
    lines.extend(_report_lines())
    return "\n".join(lines)


def _summary_lines(summary: Mapping[str, Any]) -> list[str]:
    if not summary:
        return []
    return [
        "integration_summary:",
        f"- total: {summary.get('total', 0)}",
        f"- ready_to_integrate: {summary.get('ready_to_integrate', 0)}",
        f"- conflict_risk: {summary.get('conflict_risk', 0)}",
        f"- needs_review: {summary.get('needs_review', 0)}",
        f"- already_integrated: {summary.get('already_integrated', 0)}",
    ]


def _ready_worker_lines(ready_workers: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = ["merge_candidates:"]
    if not ready_workers:
        return [
            *lines,
            "- none",
            "empty_ready_action: 没有 ready_to_integrate worker；cherry-pick/push 路径无候选，直接报告当前状态。",
        ]
    for worker in ready_workers:
        lines.extend(
            [
                f"- {_worker_label(worker)}",
                f"  branch: {_text(worker.get('branch'), 'unknown')}",
                f"  commit: {_text(worker.get('worker_commit'), 'unknown')}",
                "  ref: "
                f"{_text(worker.get('branch'), 'unknown')} @ "
                f"{_text(worker.get('worker_commit'), 'unknown')}",
                f"  cwd: {_text(worker.get('cwd'), 'unknown')}",
                f"  reason: {_text(worker.get('reason'), '无')}",
            ]
        )
    return lines


def _excluded_worker_lines(groups: Mapping[str, Any]) -> list[str]:
    lines = ["excluded_workers:"]
    has_excluded = False
    for group in NON_READY_GROUPS:
        for worker in _items(groups.get(group)):
            has_excluded = True
            lines.extend(
                [
                    f"- {_worker_label(worker)} [{group}]",
                    f"  branch: {_text(worker.get('branch'), 'unknown')}",
                    f"  commit: {_text(worker.get('worker_commit'), 'unknown')}",
                    f"  reason: {_text(worker.get('reason'), '无')}",
                ]
            )
    if not has_excluded:
        lines.append("- none")
    lines.append("excluded_rule: excluded_workers 仅用于报告原因，cherry-pick 输入只来自 merge_candidates。")
    return lines


def _execution_steps(
    *,
    base_ref: str,
    ready_workers: Sequence[Mapping[str, Any]],
) -> list[str]:
    lines = [
        "execution_steps:",
        "1. fresh state: 运行 git status --short --branch，确认当前分支和工作区干净。",
        (
            f"2. diff review: 对每个 merge_candidate 运行 git diff --stat {base_ref}..COMMIT "
            f"和 git diff {base_ref}..COMMIT，确认只包含目标改动。"
        ),
        (
            "3. cherry-pick: 按 merge_candidates 顺序执行 git cherry-pick -x COMMIT；"
            "如果出现 conflict，进入 needs_user/blocked 报告路径，写明冲突文件和恢复入口。"
        ),
        (
            "4. 组合测试: cherry-pick 全部成功后运行相关 pytest；共享路径改动时运行 "
            "PYTHONPATH=src .venv/bin/python -m pytest tests -q。"
        ),
        (
            "5. commit/push: 如果 cherry-pick 已产生提交且组合测试通过，检查 git log 和 "
            "git diff --check，然后 push 当前合并分支。"
        ),
        (
            "6. CI watch: push 后自动验证当前分支 CI。先记录 "
            "CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD) 和 "
            "HEAD_SHA=$(git rev-parse HEAD)，再运行 gh run list --workflow CI "
            "--branch \"$CURRENT_BRANCH\" --commit \"$HEAD_SHA\" --limit 1 --json "
            "databaseId,headSha,status,conclusion,url。"
        ),
        (
            "7. CI result: 找到 CI_RUN_ID 后运行 gh run watch CI_RUN_ID --exit-status，"
            "最多等待 30 分钟；随后运行 gh run view CI_RUN_ID --json "
            "databaseId,headSha,status,conclusion,url，记录 CI run id、"
            "CI conclusion 和 URL。"
        ),
        (
            "   CI failure handling: 如果 conclusion 是 failure、cancelled、timed_out "
            "或 action_required，运行 gh run view CI_RUN_ID --log-failed；"
            "摘出失败 job/step 和第一段关键错误，区分测试失败、lint 错误、"
            "安装失败或 workflow 配置错误。"
        ),
        (
            "   CI retry rule: CI 失败后汇报 SUPERVISOR_STATUS: blocked；"
            "下一步写明失败 run、关键错误和建议的后续修复 worker；rerun CI、再次 push "
            "和重复尝试留给后续明确工单。"
        ),
        (
            "   CI timeout rule: 如果超过 30 分钟仍没有 terminal conclusion，"
            "按 CI timeout 处理并汇报 blocked，写明 run id、head sha "
            "和已等待时长。"
        ),
        (
            "8. CI pass cleanup: CI 通过后汇报 SUPERVISOR_STATUS: done，"
            "在 SUPERVISOR_NEXT 写明触发 cleanup 归档；Supervisor loop/cleanup "
            "会基于 done 状态归档账本。"
        ),
        (
            "9. escalation rules: 遇到 conflict、测试失败、CI 失败或权限不足时汇报 blocked；"
            "CI run 缺失或 CI conclusion 非 success 都按 CI 失败处理；"
            "CI 失败时保留当前 merge worktree 供复查；分支和历史保持原状。"
        ),
    ]
    if not ready_workers:
        lines.append(
            "no_ready_override: 没有 ready_to_integrate worker；cherry-pick/push 路径无候选。"
        )
    return lines


def _report_lines() -> list[str]:
    return [
        (
            "done_conditions: diff review 完成、cherry-pick 结果明确、组合测试和 "
            "CI watch 有证据，CI conclusion 必须通过，且报告包含 CI run id、"
            "CI conclusion 和 cleanup 归档触发说明。"
        ),
        "report_protocol:",
        "SUPERVISOR_STATUS: needs_user|blocked|done",
        (
            "SUPERVISOR_SUMMARY: 用一句中文说明合并执行结果、测试证据、提交哈希、"
            "CI run id 和 CI conclusion。"
        ),
        (
            "SUPERVISOR_NEXT: 用一句中文说明下一步；CI 失败时写明失败时下一步，"
            "包括需要查看的 CI run id 或需要后续 worker 处理什么；CI 通过时写明 "
            "等待 Supervisor cleanup 归档。"
        ),
    ]


def _worker_label(worker: Mapping[str, Any]) -> str:
    return (
        f"{_text(worker.get('name'), 'unknown')} / "
        f"{_text(worker.get('record_id'), 'unknown')}"
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: object, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


__all__ = ["build_merge_work_order_prompt"]
