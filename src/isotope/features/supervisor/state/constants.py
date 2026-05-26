"""Shared supervisor CLI constants."""

from __future__ import annotations

EXECUTABLE_ADVICE_KINDS = {"send_status", "send_continue"}
MERGE_DISPATCH_WORKER_ROLE = "merge_dispatch"
MERGE_REPAIR_WORKER_ROLE = "merge_repair"
RECURSIVE_WORKER_ROLES = {MERGE_DISPATCH_WORKER_ROLE, MERGE_REPAIR_WORKER_ROLE, "cleanup"}
DEFAULT_MAX_CONTEXT_REQUESTS = 0
DEFAULT_MAX_FAILURE_RETRIES = 3
DEFAULT_MAX_RUN_MINUTES = 0
DEFAULT_MAX_WORKER_RETRY_COUNT = 2
DEFAULT_WORKER_CODEX_MODEL = "gpt-5.5"
DEFAULT_WORKER_CODEX_CONFIG = ('model_reasoning_effort="high"',)
DEFAULT_WORKER_PROFILE = "coding"
WORKER_PROFILE_DEFAULTS = {
    "coding": {
        "model": DEFAULT_WORKER_CODEX_MODEL,
        "config": DEFAULT_WORKER_CODEX_CONFIG,
    },
    "light": {
        "model": DEFAULT_WORKER_CODEX_MODEL,
        "config": ('model_reasoning_effort="low"',),
    },
}
WORKER_PROFILE_CHOICES = tuple(WORKER_PROFILE_DEFAULTS)
TERMINAL_DONE_NEXT_MARKERS = (
    "可结束",
    "可以结束",
    "任务结束",
    "可归档",
    "可以归档",
    "等待归档",
    "等待 supervisor 归档",
    "归档或下发新任务",
    "无需继续",
    "不需要继续",
    "不用继续",
)
STATUS_REPORT_REQUEST = "\n".join(
    [
        "请汇报当前状态，回复时严格输出三行：",
        "第一行 `SUPERVISOR_STATUS: working|done|blocked|needs_user`；",
        "第二行 `SUPERVISOR_SUMMARY: 用一句中文说明当前进展`；",
        "第三行 `SUPERVISOR_NEXT: 用一句中文说明建议下一步`。",
    ]
)
EXECUTABLE_ADVICE_TEXT = {
    "send_status": " ".join(STATUS_REPORT_REQUEST.splitlines()),
    "send_continue": " ".join(
        [
            "继续推进当前任务。",
            "完成或遇到阻塞后，严格输出三行：",
            "第一行 `SUPERVISOR_STATUS: working|done|blocked|needs_user`；",
            "第二行 `SUPERVISOR_SUMMARY: 用一句中文说明当前进展`；",
            "第三行 `SUPERVISOR_NEXT: 用一句中文说明建议下一步`。",
        ]
    ),
}
LAUNCH_TMUX_HINT = (
    "isotope-supervisor launch --backend tmux --name <name> --cwd <repo> --prompt '<task>'"
)
LAUNCH_PROCESS_HINT = (
    "isotope-supervisor launch --name <name> --cwd <repo> --prompt '<task>'"
)
ADOPT_TMUX_HINT = (
    "isotope-supervisor adopt --name <name> --cwd <repo> --tmux-session <session>"
)
DEFAULT_CONTEXT_QUERY = "Supervisor 当前状态 下一步开发方向 AGENTS.md docs/current/status.md"
DEFAULT_LAUNCH_PROMPT = " ".join(
    [
        "请阅读 AGENTS.md 和 docs/current/status.md，",
        "根据当前项目状态自行判断并继续推进 Supervisor 下一步。",
        "不要停下来等待用户发号施令；只有满足拍板条件才请求用户确认。",
        "完成或遇到阻塞后，严格输出三行：",
        "第一行 `SUPERVISOR_STATUS: working|done|blocked|needs_user`；",
        "第二行 `SUPERVISOR_SUMMARY: 用一句中文说明当前进展`；",
        "第三行 `SUPERVISOR_NEXT: 用一句中文说明建议下一步`。",
    ]
)
DEFAULT_GOAL_REPLENISH_PROMPT = " ".join(
    [
        "根据 AGENTS.md、docs/current/status.md、docs/current/agent-task-queue.md",
        "和 docs/current/supervisor-capability-map.md，",
        "为 Supervisor/Isotope 当前目标继续规划下一批可并行、可验证的 Codex worker 任务。",
        "优先选择能推动长跑自动开发闭环、低冲突、完成后可独立提交的目标；",
        "只有满足拍板条件才生成需要用户决策的任务。",
    ]
)
DASHBOARD_GROUP_LABELS = {
    "needs_attention": "需要看",
    "done": "已完成",
    "working": "工作中",
}
ARCHIVABLE_SUPERVISOR_STATUSES = {"done"}

__all__ = tuple(name for name in globals() if name.isupper())
