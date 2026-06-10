"""Codex-assisted self-repair launcher for Isotope capability gaps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .commands.llm.execution import prepare_launch_worktree
from .planner.work_order import build_launch_work_order_prompt
from .registry import SELF_REPAIR_WORKER_ROLE, launch_managed_codex
DEFAULT_SELF_REPAIR_NAME = "desktop-self-repair"


def launch_isotope_self_repair(
    *,
    state_root: Path | str,
    cwd: Path | str,
    user_goal: str,
    failure_summary: str,
    suggested_fix_summary: str = "",
    target_name: str = DEFAULT_SELF_REPAIR_NAME,
    capability_gap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    name = _non_empty(target_name, "target_name")
    goal = _non_empty(user_goal, "user_goal")
    failure = _non_empty(failure_summary, "failure_summary")

    worktree = prepare_launch_worktree(cwd=workspace, target_name=name)
    if worktree.get("enabled") is not True:
        return {
            "kind": "isotope_self_repair",
            "status": "blocked",
            "reason": (
                "worktree_prepare_failed"
                if worktree.get("failed")
                else "worktree_unavailable"
            ),
            "worktree": dict(worktree),
        }

    worker_cwd = Path(str(worktree["cwd"])).expanduser()
    prompt = self_repair_work_order_prompt(
        target_name=name,
        cwd=worker_cwd,
        user_goal=goal,
        failure_summary=failure,
        suggested_fix_summary=suggested_fix_summary,
        capability_gap=capability_gap,
    )
    record = launch_managed_codex(
        codex_home=Path(state_root).expanduser(),
        cwd=worker_cwd,
        name=name,
        prompt=prompt,
        worker_role=SELF_REPAIR_WORKER_ROLE,
    )
    return {
        "kind": "isotope_self_repair",
        "status": "launched",
        "worktree": dict(worktree),
        "managed": _managed_record_payload(record),
        "capability_gap": dict(capability_gap or {}),
    }


def self_repair_work_order_prompt(
    *,
    target_name: str,
    cwd: Path | str,
    user_goal: str,
    failure_summary: str,
    suggested_fix_summary: str = "",
    capability_gap: dict[str, Any] | None = None,
) -> str:
    fix_hint = suggested_fix_summary.strip() or "由你根据代码和验证结果判断。"
    goal = "\n".join(
        [
            "Isotope self-repair request.",
            f"用户原始目标：{user_goal.strip()}",
            f"当前 Isotope 能力缺口：{failure_summary.strip()}",
            _capability_gap_prompt_section(capability_gap),
            f"建议修复方向：{fix_hint}",
            (
                "边界：你在隔离 worktree 中修复 Isotope 自身；"
                "非平凡代码改动由 Codex 完成，Isotope 只负责任务编排。"
            ),
            (
                "限制：不要合入 main；不要安装新依赖、skill 或 MCP；"
                "不要改长期配置，除非用户明确批准。"
            ),
            (
                "要求：先读现有实现和测试，复用已有 contract；"
                "做最小可验证改动，运行相关测试，产生 Conventional Commits 提交。"
            ),
        ]
    )
    return build_launch_work_order_prompt(
        target_name=target_name,
        cwd=str(cwd),
        goal=goal,
        allow_remote_push=False,
    )


def _capability_gap_prompt_section(capability_gap: dict[str, Any] | None) -> str:
    if not capability_gap:
        return "关联 capability gap：无。"
    needed_context = capability_gap.get("needed_context")
    context_text = (
        "、".join(item for item in needed_context if isinstance(item, str))
        if isinstance(needed_context, list)
        else ""
    )
    return "\n".join(
        [
            "关联 capability gap：",
            f"- gap_id：{capability_gap.get('gap_id') or ''}",
            f"- missing_capability_kind：{capability_gap.get('missing_capability_kind') or ''}",
            f"- reason：{capability_gap.get('reason') or ''}",
            f"- needed_context：{context_text}",
            f"- suggested_next_capability：{capability_gap.get('suggested_next_capability') or ''}",
        ]
    )


def _managed_record_payload(record: Any) -> dict[str, Any]:
    return {
        "name": getattr(record, "name", None),
        "record_id": getattr(record, "record_id", None),
        "pid": getattr(record, "pid", None),
        "backend": getattr(record, "backend", None),
        "worker_role": getattr(record, "worker_role", None),
        "cwd": getattr(record, "cwd", None),
        "log_path": getattr(record, "log_path", None),
    }


def _non_empty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


__all__ = [
    "DEFAULT_SELF_REPAIR_NAME",
    "SELF_REPAIR_WORKER_ROLE",
    "launch_isotope_self_repair",
    "self_repair_work_order_prompt",
]
