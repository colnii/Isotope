"""Build Supervisor-managed worker work order prompts."""

from __future__ import annotations


def build_launch_work_order_prompt(
    *,
    target_name: str,
    cwd: str,
    goal: str,
) -> str:
    return "\n".join(
        [
            "WORK ORDER",
            f"goal: {goal.strip()}",
            f"cwd: {cwd.strip()}",
            f"target_name: {target_name.strip()}",
            "allowed_scope: 只处理本次 goal 直接相关的代码、测试和必要文档。",
            "forbidden_scope: 不主动推送远端；不扩大到无关功能；不改用户未要求的仓库规则。",
            (
                "budget_hint: prompt-only，建议 20 分钟内给出状态，"
                "最多主动继续 3 轮，最多请求上下文 2 次。"
            ),
            "budget_note: 这不是 Supervisor 强制预算控制；真正计数和拦截属于后续 B 层。",
            (
                "done_conditions: 目标完成、必要验证通过，若产生代码或文档改动，"
                "必须在本 worktree 内提交一个 Conventional Commits 提交；"
                "最后说明改动、证据、提交哈希和剩余风险。"
            ),
            (
                "completion_template: done: 目标完成、验证通过、必要改动已提交；"
                "summary 写明改动、验证证据、提交哈希和剩余风险。"
            ),
            (
                "completion_template: needs_user: "
                "只有上下文缺失、过时、冲突或产品取舍会改变实现方向时使用；"
                "next 写清需要用户拍板的最小问题。"
            ),
            (
                "completion_template: blocked: "
                "只有验证失败、工具/环境阻塞或无法安全继续时使用；"
                "summary 或 next 写明未提交原因和恢复入口。"
            ),
            (
                "completion_template: integration_review_marker: 保持 worktree 干净，"
                "把最终 worker commit 写入 summary；当 base 分支包含该 commit "
                "或等价补丁时，integration-review 会自动归入 already_integrated。"
            ),
            (
                "commit_exception: 只有验证失败、需求需要用户拍板或任务明确只读时才可以不提交，"
                "并必须在 SUPERVISOR_SUMMARY 或 SUPERVISOR_NEXT 说明原因。"
            ),
            (
                "ask_user_conditions: 只有 Codex 明确请求拍板、既有用户指示不足，"
                "且上下文缺失、过时或冲突时才停下来问用户。"
            ),
            (
                "report_protocol: 完成、暂停或遇到阻塞时，严格输出 "
                "SUPERVISOR_STATUS、SUPERVISOR_SUMMARY、SUPERVISOR_NEXT 三行。"
            ),
            (
                "ci_watch_writeback: 若本工单包含 push 后 CI watch，"
                "SUPERVISOR_SUMMARY 必须写明 CI run id 和 CI conclusion；"
                "SUPERVISOR_NEXT 必须写明结论后的下一步，失败时下一步要说明"
                "需要查看哪条 run 或交给谁修复。"
            ),
        ]
    )


__all__ = ["build_launch_work_order_prompt"]
