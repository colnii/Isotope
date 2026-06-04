"""Markdown-backed system prompts used by production LLM paths."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
import json
import re
from typing import Any

SYSTEM_PROMPT_NAMES = (
    "agent_group_member",
    "agent_loop_planner",
    "capacity_calling",
    "desktop_chat",
    "goal_planning",
    "goal_planning_repair",
    "product_chat",
    "social_reply",
    "supervisor_conversation_loop",
    "supervisor_llm_action",
    "supervisor_llm_summary",
    "workbench_ask",
)

USER_PROMPT_TEMPLATE_NAMES = (
    "agent_loop_planner_user",
    "capacity_calling_user",
    "capacity_calling_user_allow_no_capacity",
    "goal_planning_user",
    "goal_planning_repair_user",
    "social_reply_user",
    "supervisor_llm_action_user",
    "supervisor_llm_summary_user",
    "workbench_ask_user",
)

PROMPT_TEMPLATE_NAMES = SYSTEM_PROMPT_NAMES + USER_PROMPT_TEMPLATE_NAMES

_PROMPT_TEMPLATE_SET = set(PROMPT_TEMPLATE_NAMES)
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@lru_cache(maxsize=len(PROMPT_TEMPLATE_NAMES))
def load_prompt_template(name: str) -> str:
    """Load a registered prompt template from its markdown asset."""
    if name not in _PROMPT_TEMPLATE_SET:
        raise ValueError(f"unknown prompt template: {name}")
    text = resources.files(__package__).joinpath(f"{name}.md").read_text(
        encoding="utf-8"
    )
    return text.strip()


def load_system_prompt(name: str) -> str:
    """Load a registered system prompt from its markdown asset."""
    if name not in SYSTEM_PROMPT_NAMES:
        raise ValueError(f"unknown system prompt: {name}")
    return load_prompt_template(name)


def prompt_json(value: Any) -> str:
    """Serialize a value for insertion into a JSON-shaped prompt template."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_prompt_text(template: str, variables: dict[str, str]) -> str:
    """Render a prompt template with explicit string replacement only."""
    used: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise ValueError(f"missing prompt template variables: {name}")
        used.add(name)
        return variables[name]

    rendered = _PLACEHOLDER_PATTERN.sub(replace, template)
    unused = sorted(set(variables) - used)
    if unused:
        raise ValueError("unused prompt template variables: " + ", ".join(unused))
    unresolved = _PLACEHOLDER_PATTERN.findall(rendered)
    if unresolved:
        raise ValueError(
            "unresolved prompt template variables: " + ", ".join(sorted(unresolved))
        )
    return rendered.strip()


def render_prompt_template(name: str, variables: dict[str, str]) -> str:
    """Render a registered prompt template with string variables."""
    return render_prompt_text(load_prompt_template(name), variables)


def render_json_prompt_template(name: str, variables: dict[str, Any]) -> str:
    """Render a registered prompt template with JSON-serialized variables."""
    return render_prompt_template(
        name,
        {key: prompt_json(value) for key, value in variables.items()},
    )
