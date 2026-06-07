"""Direct-answer validation for Supervisor conversation decisions."""

from __future__ import annotations

import re


_TOOL_ACTION_PATTERN = re.compile(
    r"(我来|让我|现在|马上|接下来|立即|重新|需要先|我会|我将).{0,40}"
    r"(调用|搜索|检索|查找|查看|读取|阅读|检查|运行|执行|扫描|打开|访问)"
    r"|^(先|继续|开始|现在).{0,30}"
    r"(调用|搜索|检索|查找|查看|读取|阅读|检查|运行|执行|扫描|打开|访问)"
)


def direct_answer_promises_capability(answer: str) -> bool:
    """Return true when a final answer is really a promise to use a tool."""

    text = " ".join(answer.strip().split())
    if not text:
        return False
    return _TOOL_ACTION_PATTERN.search(text) is not None


def invalid_direct_answer_observation(answer: str) -> dict[str, str]:
    return {
        "kind": "invalid_direct_answer",
        "status": "rejected",
        "reason": "direct_answer promised a future capability call without calling it",
        "answer_excerpt": _clip_answer(answer),
        "instruction": (
            "direct_answer 是最终用户可见回答；如果需要实际搜索、查看、读取、"
            "运行或调用工具，下一轮必须返回 call_capability 或 call_capabilities。"
        ),
    }


def _clip_answer(answer: str) -> str:
    text = " ".join(answer.strip().split())
    if len(text) <= 240:
        return text
    return text[:239] + "..."
