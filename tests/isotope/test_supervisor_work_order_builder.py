from __future__ import annotations

import argparse

from isotope.features.supervisor.runner import (
    _worker_codex_config,
    _worker_codex_model,
)
from isotope.features.supervisor.work_order_builder import (
    build_launch_work_order_prompt,
)


def test_launch_work_order_prompt_includes_commit_rules():
    prompt = build_launch_work_order_prompt(
        target_name="worker-a",
        cwd="/tmp/isotope-worker",
        goal="实现目标队列 worker。",
    )

    assert prompt.startswith("WORK ORDER\n")
    assert "target_name: worker-a" in prompt
    assert "cwd: /tmp/isotope-worker" in prompt
    assert "goal: 实现目标队列 worker。" in prompt
    assert "必须在本 worktree 内提交一个 Conventional Commits 提交" in prompt
    assert (
        "commit_exception: 只有验证失败、需求需要用户拍板或任务明确只读时才可以不提交"
        in prompt
    )
    assert "提交哈希和剩余风险" in prompt


def test_launch_work_order_prompt_includes_ask_user_gate():
    prompt = build_launch_work_order_prompt(
        target_name="worker-a",
        cwd="/tmp/isotope-worker",
        goal="实现目标队列 worker。",
    )

    assert (
        "ask_user_conditions: 只有 Codex 明确请求拍板、既有用户指示不足，"
        "且上下文缺失、过时或冲突时才停下来问用户。"
    ) in prompt
    assert (
        "report_protocol: 完成、暂停或遇到阻塞时，严格输出 "
        "SUPERVISOR_STATUS、SUPERVISOR_SUMMARY、SUPERVISOR_NEXT 三行。"
    ) in prompt


def test_coding_worker_profile_defaults_to_high_reasoning_gpt_5_5():
    args = argparse.Namespace(
        worker_codex_model=None,
        worker_codex_config=None,
        worker_profile="coding",
    )

    assert _worker_codex_model(args) == "gpt-5.5"
    assert _worker_codex_config(args) == ('model_reasoning_effort="high"',)
