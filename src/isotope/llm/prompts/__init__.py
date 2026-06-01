"""Markdown-backed system prompts used by production LLM paths."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

SYSTEM_PROMPT_NAMES = (
    "agent_loop_planner",
    "capacity_calling",
    "desktop_chat",
    "goal_planning",
    "goal_planning_repair",
    "product_chat",
    "supervisor_llm_action",
    "supervisor_llm_summary",
    "workbench_ask",
)

_SYSTEM_PROMPT_SET = set(SYSTEM_PROMPT_NAMES)


@lru_cache(maxsize=len(SYSTEM_PROMPT_NAMES))
def load_system_prompt(name: str) -> str:
    """Load a registered system prompt from its markdown asset."""
    if name not in _SYSTEM_PROMPT_SET:
        raise ValueError(f"unknown system prompt: {name}")
    text = resources.files(__package__).joinpath(f"{name}.md").read_text(
        encoding="utf-8"
    )
    return text.strip()
