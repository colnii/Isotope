"""Markdown-backed system prompts used by production LLM paths."""

from __future__ import annotations

from dataclasses import dataclass
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
    "social_participation",
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
    "social_participation_user",
    "social_reply_user",
    "supervisor_llm_action_user",
    "supervisor_llm_summary_user",
    "workbench_ask_user",
)

PROMPT_TEMPLATE_NAMES = SYSTEM_PROMPT_NAMES + USER_PROMPT_TEMPLATE_NAMES

_PROMPT_TEMPLATE_SET = set(PROMPT_TEMPLATE_NAMES)
_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_SECTION_PATTERN = re.compile(
    r"^<!--\s*prompt-section:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*-->\n"
    r"(.*?)\n"
    r"^<!--\s*/prompt-section\s*-->",
    re.DOTALL | re.MULTILINE,
)


@dataclass(frozen=True)
class _PromptAsset:
    path: str
    section: str | None = None


_PROMPT_ASSETS = {
    "agent_group_member": _PromptAsset(
        "agent_loop/group_member.prompt.md",
        section="agent_group_member",
    ),
    "agent_loop_planner": _PromptAsset(
        "agent_loop/planner.prompt.md",
        section="agent_loop_planner",
    ),
    "agent_loop_planner_user": _PromptAsset(
        "agent_loop/planner.prompt.md",
        section="agent_loop_planner_user",
    ),
    "capacity_calling": _PromptAsset(
        "capacity/calling.prompt.md",
        section="capacity_calling",
    ),
    "capacity_calling_user": _PromptAsset(
        "capacity/calling.prompt.md",
        section="capacity_calling_user",
    ),
    "capacity_calling_user_allow_no_capacity": _PromptAsset(
        "capacity/calling.prompt.md",
        section="capacity_calling_user_allow_no_capacity",
    ),
    "desktop_chat": _PromptAsset(
        "chat/desktop.prompt.md",
        section="desktop_chat",
    ),
    "goal_planning": _PromptAsset(
        "supervisor/goal_planning.prompt.md",
        section="goal_planning",
    ),
    "goal_planning_user": _PromptAsset(
        "supervisor/goal_planning.prompt.md",
        section="goal_planning_user",
    ),
    "goal_planning_repair": _PromptAsset(
        "supervisor/goal_planning.prompt.md",
        section="goal_planning_repair",
    ),
    "goal_planning_repair_user": _PromptAsset(
        "supervisor/goal_planning.prompt.md",
        section="goal_planning_repair_user",
    ),
    "product_chat": _PromptAsset(
        "chat/product.prompt.md",
        section="product_chat",
    ),
    "social_participation": _PromptAsset(
        "social/participation.prompt.md",
        section="social_participation",
    ),
    "social_participation_user": _PromptAsset(
        "social/participation.prompt.md",
        section="social_participation_user",
    ),
    "social_reply": _PromptAsset(
        "social/reply.prompt.md",
        section="social_reply",
    ),
    "social_reply_user": _PromptAsset(
        "social/reply.prompt.md",
        section="social_reply_user",
    ),
    "supervisor_conversation_loop": _PromptAsset(
        "supervisor/conversation_loop.prompt.md",
        section="supervisor_conversation_loop",
    ),
    "supervisor_llm_action": _PromptAsset(
        "supervisor/llm_action.prompt.md",
        section="supervisor_llm_action",
    ),
    "supervisor_llm_action_user": _PromptAsset(
        "supervisor/llm_action.prompt.md",
        section="supervisor_llm_action_user",
    ),
    "supervisor_llm_summary": _PromptAsset(
        "supervisor/llm_summary.prompt.md",
        section="supervisor_llm_summary",
    ),
    "supervisor_llm_summary_user": _PromptAsset(
        "supervisor/llm_summary.prompt.md",
        section="supervisor_llm_summary_user",
    ),
    "workbench_ask": _PromptAsset(
        "workbench/ask.prompt.md",
        section="workbench_ask",
    ),
    "workbench_ask_user": _PromptAsset(
        "workbench/ask.prompt.md",
        section="workbench_ask_user",
    ),
}


@lru_cache(maxsize=len(PROMPT_TEMPLATE_NAMES))
def load_prompt_template(name: str) -> str:
    """Load a registered prompt template from its markdown asset."""
    if name not in _PROMPT_TEMPLATE_SET:
        raise ValueError(f"unknown prompt template: {name}")
    asset = _PROMPT_ASSETS[name]
    text = _read_prompt_asset(asset.path)
    if asset.section is not None:
        return _extract_prompt_section(text, asset.section)
    return text.strip()


@lru_cache(maxsize=len(PROMPT_TEMPLATE_NAMES))
def load_prompt_source(name: str) -> str:
    """Load the full registered prompt source for human review."""
    if name not in _PROMPT_TEMPLATE_SET:
        raise ValueError(f"unknown prompt template: {name}")
    return _read_prompt_asset(_PROMPT_ASSETS[name].path).strip()


@lru_cache(maxsize=len(PROMPT_TEMPLATE_NAMES))
def _read_prompt_asset(path: str) -> str:
    return resources.files(__package__).joinpath(*path.split("/")).read_text(
        encoding="utf-8"
    )


def _extract_prompt_section(text: str, section: str) -> str:
    matches = [
        match.group(2).strip()
        for match in _SECTION_PATTERN.finditer(text)
        if match.group(1) == section
    ]
    if not matches:
        raise ValueError(f"missing prompt section: {section}")
    if len(matches) > 1:
        raise ValueError(f"duplicate prompt section: {section}")
    return matches[0]


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
