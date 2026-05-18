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
LLM_ACTION_ALLOWED_KINDS = (
    "monitor",
    "send_status",
    "send_continue",
    "resume_session",
    "launch_session",
    "request_context",
    "ask_user",
)
LLM_RESUME_PROMPT_KINDS = ("send_status", "send_continue")
LLM_ASK_USER_CONTEXT_STATUSES = ("missing", "outdated", "conflict")


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
                failures.append(
                    f"{entry.provider}:{type(exc).__name__}"
                    f"({_safe_failure_message(exc, entry.api_key)})"
                )
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
    recent_context_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build the prompt for guarded LLM planning."""
    candidate_targets = [
        {
            "target_name": _suggested_target_name(session),
            "session_id": session.session_id,
            "cwd": session.cwd,
            "status": session.supervisor_status or session.status,
            "reason": session.supervisor_summary or session.reason,
            "can_send_to_tmux": _has_managed_send_target(session),
            "can_resume": _can_resume_session(session),
            "tmux_session": session.managed_tmux_session,
            "managed_terminal_ready": session.managed_terminal_ready,
            "managed_bell": session.managed_bell,
            "managed_bell_event_at": session.managed_bell_event_at,
            "supervisor_status": session.supervisor_status,
            "supervisor_summary": _clip(session.supervisor_summary),
            "supervisor_next": _clip(session.supervisor_next),
        }
        for session in report.sessions
        if _is_llm_candidate_target(session)
    ]
    resumable_session_ids = [
        session.session_id for session in report.sessions if _can_resume_session(session)
    ]
    completed_session_ids = [
        session.session_id for session in report.sessions if _is_completed_session(session)
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是 Codex Supervisor 的 LLM planner（规划器）。"
                "你负责根据窗口状态选择下一步动作；"
                "规则和白名单只是 guardrail（护栏）。"
                "只能从允许动作里选择一个动作，不得编造命令，不得要求任意文本发送。"
                "只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "allowed_kinds": list(LLM_ACTION_ALLOWED_KINDS),
                    "available_workspaces": _available_workspaces(report),
                    "candidate_targets": candidate_targets,
                    "resumable_session_ids": resumable_session_ids,
                    "completed_session_ids": completed_session_ids,
                    "command_suggestions": command_suggestions,
                    "recent_context_results": recent_context_results or [],
                    "action_rules": [
                        (
                            "recommendation.target_session_id 只是状态线索，"
                            "不代表可执行目标。"
                        ),
                        (
                            "resume_session.session_id 必须来自 resumable_session_ids；"
                            "resumable_session_ids 为空时不得输出 resume_session。"
                        ),
                        (
                            "completed_session_ids 里的会话已经完成或归档，"
                            "不得恢复；需要继续下一批时使用 request_context 或 launch_session。"
                        ),
                    ],
                    "context_capability": {
                        "kind": "request_context",
                        "description": (
                            "信息不足时，按 query 主动检索项目上下文；"
                            "不要要求系统每轮固定塞文档全文。"
                        ),
                        "schema": {
                            "kind": "request_context",
                            "cwd": "/path/to/repo",
                            "query": "要查的问题或关键词",
                            "reason": "一句中文原因",
                        },
                    },
                    "decision_gate": {
                        "kind": "ask_user",
                        "description": (
                            "只有同时满足三项才允许停下来问用户拍板："
                            "Codex 已明确提出拍板请求；"
                            "LLM 无法从用户已有指示判断；"
                            "已检索上下文且结果缺失、过时或冲突。"
                        ),
                        "schema": {
                            "kind": "ask_user",
                            "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                            "question": "需要用户拍板的问题",
                            "codex_requested_decision": True,
                            "instructions_exhausted": True,
                            "context_status": "missing|outdated|conflict",
                            "reason": "一句中文原因",
                        },
                    },
                    "generated_at": report.generated_at,
                    "recommendation": report.recommendation.to_dict(),
                    "output_schema": {
                        "kind": "resume_session",
                        "target_name": "lane-a",
                        "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
                        "prompt_kind": "send_continue",
                        "reason": "一句中文原因",
                    },
                    "launch_schema": {
                        "kind": "launch_session",
                        "target_name": "new-lane",
                        "cwd": "/path/to/repo",
                        "prompt": "由 LLM 根据上下文自由写给新 Codex 会话的中文指令",
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
    recent_context_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not _has_any_llm_target(report):
        return {
            "kind": "monitor",
            "target_name": None,
            "reason": "当前没有可控的 Supervisor 目标，先继续监控。",
            "command_suggestion": None,
        }
    raw = provider.summarize(
        build_llm_action_messages(report, command_suggestions, recent_context_results)
    )
    payload = _extract_json_object(raw)
    kind = _required_payload_string(payload, "kind")
    if kind not in LLM_ACTION_ALLOWED_KINDS:
        supported = ", ".join(LLM_ACTION_ALLOWED_KINDS)
        raise ValueError(f"unsupported LLM action: {kind}; allowed: {supported}")
    target_name = _optional_payload_string(payload, "target_name")
    reason = _optional_payload_string(payload, "reason") or "LLM 建议执行该白名单动作。"
    session_id: str | None = None
    prompt_kind: str | None = None
    question: str | None = None
    context_status: str | None = None
    codex_requested_decision: bool | None = None
    instructions_exhausted: bool | None = None
    if kind == "resume_session":
        session_id = _required_payload_string(payload, "session_id")
        if not _has_resume_target(report, session_id):
            raise ValueError(f"unknown resumable session for LLM action: {session_id}")
        prompt_kind = _optional_payload_string(payload, "prompt_kind") or "send_continue"
        if prompt_kind not in LLM_RESUME_PROMPT_KINDS:
            supported = ", ".join(LLM_RESUME_PROMPT_KINDS)
            raise ValueError(f"unsupported resume prompt_kind: {prompt_kind}; allowed: {supported}")
        command_suggestion = _command_suggestion_for_kind(
            command_suggestions,
            kind,
            session_id=session_id,
            prompt_kind=prompt_kind,
        )
        if command_suggestion is None:
            raise ValueError(f"no command suggestion for LLM action: {kind}")
        target_name = target_name or command_suggestion.get("target_name")
    elif kind == "launch_session":
        target_name = target_name or "planner-session"
        cwd = _optional_payload_string(payload, "cwd") or _default_workspace(report)
        if cwd is None or cwd not in _available_workspaces(report):
            raise ValueError(f"unknown workspace for LLM action: {cwd}")
        prompt = _required_payload_string(payload, "prompt")
        command_suggestion = _launch_session_command_suggestion(
            target_name=target_name,
            cwd=cwd,
            prompt=prompt,
        )
    elif kind == "request_context":
        target_name = None
        cwd = _optional_payload_string(payload, "cwd") or _default_workspace(report)
        if cwd is None or cwd not in _available_workspaces(report):
            raise ValueError(f"unknown workspace for LLM action: {cwd}")
        query = _required_payload_string(payload, "query")
        command_suggestion = _request_context_command_suggestion(cwd=cwd, query=query)
    elif kind == "ask_user":
        session_id = _required_payload_string(payload, "session_id")
        target = _ask_user_target(report, session_id)
        if target is None:
            raise ValueError("ask_user requires a Codex decision request")
        if not _required_payload_bool(payload, "codex_requested_decision"):
            raise ValueError("ask_user requires codex_requested_decision=true")
        if not _required_payload_bool(payload, "instructions_exhausted"):
            raise ValueError("ask_user requires instructions_exhausted=true")
        if not _has_context_check_for_target(recent_context_results, target):
            raise ValueError("ask_user requires a context check")
        context_status = _required_payload_string(payload, "context_status")
        if context_status not in LLM_ASK_USER_CONTEXT_STATUSES:
            supported = ", ".join(LLM_ASK_USER_CONTEXT_STATUSES)
            raise ValueError(
                f"ask_user context_status must be one of: {supported}"
            )
        question = _required_payload_string(payload, "question")
        codex_requested_decision = True
        instructions_exhausted = True
        target_name = target_name or _suggested_target_name(target)
        command_suggestion = None
    elif kind != "monitor":
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
        **({"session_id": session_id} if session_id is not None else {}),
        **({"prompt_kind": prompt_kind} if prompt_kind is not None else {}),
        **({"cwd": cwd} if kind == "launch_session" else {}),
        **({"prompt": prompt} if kind == "launch_session" else {}),
        **({"cwd": cwd} if kind == "request_context" else {}),
        **({"query": query} if kind == "request_context" else {}),
        **({"question": question} if question is not None else {}),
        **({"context_status": context_status} if context_status is not None else {}),
        **(
            {"codex_requested_decision": codex_requested_decision}
            if codex_requested_decision is not None
            else {}
        ),
        **(
            {"instructions_exhausted": instructions_exhausted}
            if instructions_exhausted is not None
            else {}
        ),
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


def _safe_failure_message(exc: Exception, api_key: str) -> str:
    message = " ".join(str(exc).split())
    if api_key:
        message = message.replace(api_key, _redacted_secret(api_key))
    return _clip_text(message or type(exc).__name__, limit=180)


def _redacted_secret(value: str) -> str:
    if len(value) <= 3:
        return "..."
    return value[:3] + "..."


def _clip_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


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
        raw_excerpt = _clip_text(" ".join(stripped.split()), limit=180)
        raise ValueError(f"LLM action must be a JSON object; raw={raw_excerpt}")
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


def _required_payload_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"LLM action field must be bool: {field}")
    return value


def _command_suggestion_for_kind(
    command_suggestions: list[dict[str, str]],
    kind: str,
    *,
    target_name: str | None = None,
    session_id: str | None = None,
    prompt_kind: str | None = None,
) -> dict[str, str] | None:
    for suggestion in command_suggestions:
        if suggestion.get("kind") != kind:
            continue
        if session_id is not None and suggestion.get("session_id") != session_id:
            continue
        if prompt_kind is not None and suggestion.get("prompt_kind") != prompt_kind:
            continue
        if target_name is not None and not _command_targets_name(
            suggestion.get("command", ""),
            target_name,
        ):
            continue
        return suggestion
    return None


def _launch_session_command_suggestion(
    *,
    target_name: str,
    cwd: str,
    prompt: str,
) -> dict[str, str]:
    return {
        "kind": "launch_session",
        "label": "启动新的 Codex 托管会话",
        "target_name": target_name,
        "cwd": cwd,
        "prompt": prompt,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "launch",
                "--name",
                target_name,
                "--cwd",
                cwd,
                "--prompt",
                prompt,
            ]
        ),
    }


def _request_context_command_suggestion(
    *,
    cwd: str,
    query: str,
) -> dict[str, str]:
    return {
        "kind": "request_context",
        "label": "检索项目上下文",
        "cwd": cwd,
        "query": query,
        "command": shlex.join(
            [
                "isotope-supervisor",
                "context",
                "--cwd",
                cwd,
                "--query",
                query,
            ]
        ),
    }


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
        _has_managed_send_target(session) and session.managed_name == target_name
        for session in report.sessions
    )


def _has_resume_target(report: CodexSupervisorReport, session_id: str) -> bool:
    return any(
        _can_resume_session(session) and session.session_id == session_id
        for session in report.sessions
    )


def _ask_user_target(report: CodexSupervisorReport, session_id: str) -> Any | None:
    for session in report.sessions:
        if session.session_id == session_id and _session_requests_user_decision(session):
            return session
    return None


def _session_requests_user_decision(session: Any) -> bool:
    status = (getattr(session, "supervisor_status", None) or "").lower()
    if status == "needs_user":
        return True
    if status != "blocked" and getattr(session, "status", None) != "needs_user":
        return False
    text = " ".join(
        str(value)
        for value in (
            getattr(session, "supervisor_summary", None),
            getattr(session, "supervisor_next", None),
            getattr(session, "reason", None),
            getattr(session, "last_assistant_message", None),
        )
        if value
    )
    return any(
        marker in text
        for marker in (
            "用户",
            "确认",
            "选择",
            "决定",
            "拍板",
            "提供",
            "是否",
            "人工",
        )
    )


def _has_context_check_for_target(
    recent_context_results: list[dict[str, Any]] | None,
    target: Any,
) -> bool:
    if not recent_context_results:
        return False
    target_cwd = getattr(target, "cwd", None)
    for result in recent_context_results:
        if not isinstance(result, dict):
            continue
        if isinstance(target_cwd, str) and target_cwd:
            if result.get("cwd") != target_cwd:
                continue
        return True
    return False


def _has_any_llm_target(report: CodexSupervisorReport) -> bool:
    return any(_is_llm_candidate_target(session) for session in report.sessions) or bool(
        _available_workspaces(report)
    )


def _is_llm_candidate_target(session: Any) -> bool:
    return _has_managed_send_target(session) or _can_resume_session(session)


def _has_managed_send_target(session: Any) -> bool:
    return bool(session.managed_name and session.managed_tmux_session)


def _can_resume_session(session: Any) -> bool:
    session_id = getattr(session, "session_id", None)
    return (
        isinstance(session_id, str)
        and bool(session_id)
        and not session_id.startswith("managed:")
        and not _is_completed_session(session)
    )


def _suggested_target_name(session: Any) -> str:
    if session.managed_name:
        return session.managed_name
    return "resume-" + session.short_session_id


def _available_workspaces(report: CodexSupervisorReport) -> list[str]:
    seen: set[str] = set()
    workspaces: list[str] = []
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if not isinstance(cwd, str) or not cwd or cwd in seen:
            continue
        seen.add(cwd)
        workspaces.append(cwd)
    return workspaces


def _default_workspace(report: CodexSupervisorReport) -> str | None:
    workspaces = _available_workspaces(report)
    return workspaces[0] if workspaces else None


def _is_completed_session(session: Any) -> bool:
    return (
        getattr(session, "status", None) in {"done", "archived"}
        or getattr(session, "supervisor_status", None) == "done"
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
