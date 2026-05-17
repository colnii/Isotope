"""Codex Supervisor 的 LLM summary（大模型摘要）工具。

模型号池来自本机 TOML 文件。默认读取同目录下的
``supervisor_llm_pool.toml``，也可用 ``SUPERVISOR_LLM_POOL_TOML_FILES``
指定多个路径。

支持两种 TOML 格式：

1. 新格式（推荐）—— 按 agent 分组：
   ``[[agents]]`` → ``[[agents.providers]]``，可按 agent_name 筛选。

2. 旧格式（兼容）—— 扁平 ``[[keys]]`` 列表。

api_keys 支持 ``env:VAR_NAME`` 或明文 key；默认 TOML 已被 gitignore 屏蔽。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from ...llm.provider import OpenAICompatibleChatProvider, Transport
from .flow import CodexSupervisorReport

DEFAULT_MAX_TOKENS = 512
LLM_ACTION_ALLOWED_KINDS = ("monitor", "send_status", "send_continue")


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------


class SummaryProvider(Protocol):
    def summarize(self, messages: list[dict[str, str]]) -> str:
        ...


@dataclass(frozen=True)
class PoolEntry:
    """号池里的一条可尝试模型配置。"""

    provider: str
    api_key: str
    base_url: str
    model: str
    max_tokens: int | None = None


class PooledSummaryProvider:
    """按顺序尝试 OpenAI-compatible（兼容 OpenAI 形状）模型配置。"""

    def __init__(
        self,
        *,
        entries: tuple[PoolEntry, ...],
        timeout: int = 60,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        transport: Transport | None = None,
    ) -> None:
        if not entries:
            raise ValueError("entries must not be empty")
        self._entries = entries
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._transport = transport

    def summarize(self, messages: list[dict[str, str]]) -> str:
        failures: list[str] = []
        for entry in self._entries:
            try:
                provider = OpenAICompatibleChatProvider(
                    provider=entry.provider,
                    api_key=entry.api_key,
                    base_url=entry.base_url,
                    model=entry.model,
                    timeout=self._timeout,
                    transport=self._transport,
                )
                response = provider.generate(
                    messages, max_tokens=entry.max_tokens or self._max_tokens
                )
                return _strip_thinking(response.content)
            except Exception as exc:
                failures.append(f"{entry.provider}:{type(exc).__name__}")
        raise ValueError("All LLM pool entries failed: " + ", ".join(failures))


def resolve_summary_provider_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    agent_name: str | None = None,
    transport: Transport | None = None,
) -> SummaryProvider:
    """从 TOML 号池创建摘要 provider（模型适配器）。

    ``agent_name`` 为 None 时使用全部 agent 的号池；
    指定 agent_name 时只加载对应 ``[[agents]]`` 下的 providers。
    """
    env = os.environ if environ is None else environ
    timeout = _env_int(env, "SUPERVISOR_LLM_TIMEOUT_SECONDS", default=60)
    max_tokens = _env_int(env, "SUPERVISOR_LLM_MAX_TOKENS", default=DEFAULT_MAX_TOKENS)

    files = _pool_toml_paths(env)
    entries = _load_pool_entries(files, env, agent_name=agent_name)
    if not entries:
        agent_hint = f" for agent '{agent_name}'" if agent_name else ""
        raise ValueError(
            f"No LLM pool entries found{agent_hint}. "
            "Check SUPERVISOR_LLM_POOL_TOML_FILES or the default "
            "supervisor_llm_pool.toml configuration."
        )

    return PooledSummaryProvider(
        entries=tuple(entries),
        timeout=timeout,
        max_tokens=max_tokens,
        transport=transport,
    )


def build_llm_summary_messages(report: CodexSupervisorReport) -> list[dict[str, str]]:
    compact_sessions = [
        {
            "session_id": session.session_id,
            "cwd": session.cwd,
            "git_branch": session.git_branch,
            "status": session.status_label,
            "reason": session.reason,
            "status_evidence": session.status_evidence,
            "age_seconds": session.age_seconds,
            "managed": session.managed,
            "managed_name": session.managed_name,
            "managed_backend": session.managed_backend,
            "managed_tmux_session": session.managed_tmux_session,
            "managed_bell": session.managed_bell,
            "managed_bell_event_at": session.managed_bell_event_at,
            "managed_bell_hook_installed": session.managed_bell_hook_installed,
            "managed_terminal_ready": session.managed_terminal_ready,
            "supervisor_status": session.supervisor_status,
            "supervisor_summary": _clip(session.supervisor_summary),
            "supervisor_next": _clip(session.supervisor_next),
            "last_user": _clip(session.last_user_message),
            "last_reply": _clip(session.last_assistant_message),
        }
        for session in report.sessions
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是 Codex Supervisor 的中文摘要层。"
                "根据压缩后的会话状态，判断每个窗口在干什么、是否需要介入、"
                "优先处理哪个窗口。不要编造日志里没有的信息。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "generated_at": report.generated_at,
                    "recommendation": report.recommendation.to_dict(),
                    "sessions": compact_sessions,
                    "output_requirements": [
                        "用中文输出 3-6 行",
                        "每行都要短",
                        "说明优先处理建议",
                        "不要输出 JSON",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def generate_llm_summary(
    report: CodexSupervisorReport,
    provider: SummaryProvider,
) -> str:
    return provider.summarize(build_llm_summary_messages(report))


def build_llm_action_messages(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Build the prompt for whitelist-bound action selection."""
    candidate_targets = [
        {
            "target_name": session.managed_name,
            "session_id": session.session_id,
            "status": session.supervisor_status or session.status,
            "reason": session.supervisor_summary or session.reason,
            "tmux_session": session.managed_tmux_session,
            "managed_terminal_ready": session.managed_terminal_ready,
            "managed_bell": session.managed_bell,
            "managed_bell_event_at": session.managed_bell_event_at,
            "supervisor_status": session.supervisor_status,
            "supervisor_summary": _clip(session.supervisor_summary),
            "supervisor_next": _clip(session.supervisor_next),
        }
        for session in report.sessions
        if session.managed_name and session.managed_tmux_session
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是 Codex Supervisor 的白名单动作选择层。"
                "只能从白名单里选择一个动作，不得编造命令，不得要求任意文本发送。"
                "只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "allowed_kinds": list(LLM_ACTION_ALLOWED_KINDS),
                    "candidate_targets": candidate_targets,
                    "command_suggestions": command_suggestions,
                    "generated_at": report.generated_at,
                    "recommendation": report.recommendation.to_dict(),
                    "output_schema": {
                        "kind": "send_continue",
                        "target_name": "lane-a",
                        "reason": "一句中文原因",
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def generate_llm_action_decision(
    report: CodexSupervisorReport,
    command_suggestions: list[dict[str, str]],
    provider: SummaryProvider,
) -> dict[str, Any]:
    if not _has_any_managed_target(report):
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "当前没有可控的托管 tmux lane，先继续监控。",
            "command_suggestion": None,
        }
    raw = provider.summarize(build_llm_action_messages(report, command_suggestions))
    payload = _extract_json_object(raw)
    kind = _required_payload_string(payload, "kind")
    if kind not in LLM_ACTION_ALLOWED_KINDS:
        supported = ", ".join(LLM_ACTION_ALLOWED_KINDS)
        raise ValueError(f"unsupported LLM action: {kind}; allowed: {supported}")
    target_name = _optional_payload_string(payload, "target_name")
    reason = _optional_payload_string(payload, "reason") or "LLM 建议执行该白名单动作。"
    if kind != "monitor":
        if target_name is None:
            raise ValueError(f"target_name is required for LLM action: {kind}")
        if not _has_managed_target(report, target_name):
            raise ValueError(f"unknown managed target for LLM action: {target_name}")
        command_suggestion = _command_suggestion_for_kind(
            command_suggestions,
            kind,
            target_name=target_name,
        )
        if command_suggestion is None:
            raise ValueError(f"no command suggestion for LLM action: {kind}")
    else:
        command_suggestion = _command_suggestion_for_kind(command_suggestions, kind)
    return {
        "kind": kind,
        "target_name": target_name,
        "reason": reason,
        "command_suggestion": command_suggestion,
    }


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _pool_toml_paths(env: Mapping[str, str]) -> list[Path]:
    """解析本机 TOML 号池路径。"""
    raw = _env_string(env, "SUPERVISOR_LLM_POOL_TOML_FILES")
    if raw:
        return [Path(p.strip()) for p in raw.split(",") if p.strip()]

    return [Path(__file__).resolve().parent / "supervisor_llm_pool.toml"]


def _load_pool_entries(
    files: list[Path],
    env: Mapping[str, str],
    *,
    agent_name: str | None = None,
) -> list[PoolEntry]:
    """读取 TOML 号池，展开 key 为 PoolEntry 列表。

    支持两种 TOML 格式：

    1. 新格式（推荐）—— 按 agent 分组：
       ``[[agents]]`` → ``[[agents.providers]]``

    2. 旧格式（兼容）—— 扁平列表：
       ``[[keys]]``

    ``agent_name`` 为 None 时加载全部 agent；指定时只加载对应的 ``[[agents]]``。
    """
    entries: list[PoolEntry] = []
    for path in files:
        if not path.is_file():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))

        # 新格式：[[agents]]
        if isinstance(data.get("agents"), list):
            for agent in data["agents"]:
                if not isinstance(agent, dict):
                    continue
                name = _optional_toml_str(agent, "name")
                if name is None:
                    continue
                if agent_name is not None and name != agent_name:
                    continue
                provider_list = agent.get("providers")
                if not isinstance(provider_list, list):
                    continue
                for item in provider_list:
                    if not isinstance(item, dict):
                        continue
                    _append_entries_from_toml_item(entries, item, env)

        # 旧格式（兼容）：[[keys]]
        if isinstance(data.get("keys"), list):
            for item in data["keys"]:
                if not isinstance(item, dict):
                    continue
                _append_entries_from_toml_item(entries, item, env)

    return entries


def _append_entries_from_toml_item(
    entries: list[PoolEntry],
    item: dict[str, object],
    env: Mapping[str, str],
) -> None:
    """从一个 TOML item（provider 块）展开 api_keys 为 PoolEntry。"""
    provider = _optional_toml_str(item, "provider") or "pool"
    base_url = _require_toml_str(item, "base_url")
    model = _require_toml_str(item, "model")
    max_tokens_val = item.get("max_tokens")
    if max_tokens_val is not None:
        if not isinstance(max_tokens_val, int) or max_tokens_val <= 0:
            raise ValueError(
                f"TOML pool entry max_tokens must be a positive integer, got: {max_tokens_val!r}"
            )
    raw_keys = item.get("api_keys")
    if not isinstance(raw_keys, list):
        return
    for entry in raw_keys:
        if not isinstance(entry, str) or not entry.strip():
            continue
        entry = entry.strip()
        if entry.startswith("env:"):
            api_key = env.get(entry[4:])
            if not api_key:
                continue
        else:
            api_key = entry
        entries.append(
            PoolEntry(
                provider=provider,
                api_key=api_key,
                base_url=base_url.rstrip("/"),
                model=model,
                max_tokens=max_tokens_val,
            )
        )


def _require_toml_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"TOML pool entry missing required string field: {key}")
    return value.strip()


def _optional_toml_str(item: dict[str, object], key: str) -> str | None:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    candidates = _json_object_candidates(stripped)
    if not candidates:
        raise ValueError("LLM action must be a JSON object")
    for payload in reversed(candidates):
        if isinstance(payload.get("kind"), str):
            return payload
    return candidates[-1]


def _json_object_candidates(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.append(payload)
    return candidates


def _required_payload_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"LLM action field is required: {field}")
    return value.strip()


def _optional_payload_string(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _command_suggestion_for_kind(
    command_suggestions: list[dict[str, str]],
    kind: str,
    *,
    target_name: str | None = None,
) -> dict[str, str] | None:
    for suggestion in command_suggestions:
        if suggestion.get("kind") != kind:
            continue
        if target_name is not None and not _command_targets_name(
            suggestion.get("command", ""),
            target_name,
        ):
            continue
        return suggestion
    return None


def _command_targets_name(command: str, target_name: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    for index, part in enumerate(parts[:-1]):
        if part == "--name" and parts[index + 1] == target_name:
            return True
    return False


def _has_managed_target(report: CodexSupervisorReport, target_name: str) -> bool:
    return any(
        session.managed_name == target_name and bool(session.managed_tmux_session)
        for session in report.sessions
    )


def _has_any_managed_target(report: CodexSupervisorReport) -> bool:
    return any(
        session.managed_name is not None and bool(session.managed_tmux_session)
        for session in report.sessions
    )


def _clip(text: str | None, *, limit: int = 160) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "\u2026"


def _env_string(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if not value:
        return None
    return value.strip() or None


def _env_int(env: Mapping[str, str], name: str, *, default: int) -> int:
    value = _env_string(env, name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed
