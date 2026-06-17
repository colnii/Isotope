"""Product-level Supervisor conversation loop over capabilities and agent loop."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from isotope.capabilities.runner import CapabilityRunner
from isotope.capabilities.tools.terminal import (
    DEFAULT_ALLOWED_COMMANDS,
    DEFAULT_TERMINAL_APPROVAL_MODE,
    TERMINAL_APPROVAL_MODES,
)
from isotope.features.supervisor.commands.handlers.capacity import (
    _execute_agent_loop_capacity_step,
    agent_loop_json_result,
)
from isotope.features.supervisor.native_coding_run import (
    CODING_TASK_RUN_CAPABILITY,
    run_native_coding_agent_loop,
)
from isotope.features.research.providers import tavily_api_key_from_config
from isotope.llm.prompts import render_json_prompt_template
from isotope.llm.provider import LLMResponse
from isotope.platform.schemas.input_contract import (
    contract_properties,
    public_contract_properties,
    public_required_contract_keys,
)

from .desktop_chat_context import compact_desktop_chat_history_messages
from .conversation.direct_answer import (
    capability_gap_user_answer,
    direct_answer_rejection_observation,
    recovered_unstructured_direct_answer,
)
from .conversation.decision_parsing import parse_decision
from .conversation.generation import generate_with_timeout as _generate_with_timeout
from .conversation.repeated_capacity import (
    capacity_call_key,
    repeated_capability_observation,
    repeated_failed_capability_answer,
)
from .conversation_parallel import run_parallel_event_generators
from .conversation_observations import (
    capability_result_detail_from_agent_loop,
    capacity_observation_from_event_payload,
    capacity_observation_message_content,
    model_observation_from_agent_loop,
    research_artifact_detail_from_agent_loop,
    screen_artifact_detail_from_agent_loop,
)
from .conversation_research_context import research_context_from_observations
from .conversation_timeouts import (
    CapacityExecutionTimeout,
    capacity_timeout_seconds as _capacity_timeout_seconds,
    execute_capacity_step_with_timeout,
)


_INVALID_DIRECT_ANSWER_RECOVERY_LIMIT = 3


class SupervisorConversationProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        raise NotImplementedError


@dataclass(frozen=True)
class SupervisorConversationEvent:
    event: str
    payload: dict[str, Any]
    provider: str = "unknown"
    model: str = "unknown"
    private: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def run_supervisor_conversation_events(
    *,
    state_root: Path | str,
    cwd: Path | str,
    user_message: str,
    provider: SupervisorConversationProvider,
    max_tokens: int = 512,
    history: list[dict[str, str]] | None = None,
    capacity_runner: CapabilityRunner | None = None,
    max_turns: int = 300,
    timeout_seconds: float | None = None,
    terminal_approval_mode: str = DEFAULT_TERMINAL_APPROVAL_MODE,
    terminal_allowed_commands: list[str] | None = None,
) -> Iterator[SupervisorConversationEvent]:
    clean_message = _require_text(user_message, "user_message")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")
    if isinstance(max_turns, bool) or not isinstance(max_turns, int) or max_turns <= 0:
        raise ValueError("max_turns must be a positive integer")
    context = _conversation_context(
        state_root=Path(state_root).expanduser(),
        cwd=Path(cwd).expanduser(),
        capacity_runner=capacity_runner,
        terminal_approval_mode=terminal_approval_mode,
        terminal_allowed_commands=terminal_allowed_commands,
    )
    observations: list[dict[str, Any]] = []
    failed_calls: dict[str, dict[str, Any]] = {}
    completed_calls: dict[str, dict[str, Any]] = {}
    invalid_direct_answer_rejections = 0
    for _turn_index in range(max_turns):
        response = _generate_with_timeout(
            provider,
            messages=_conversation_messages(
                clean_message,
                context,
                history=history,
                observations=observations,
            ),
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        decision = parse_decision(response.content)
        if decision["kind"] == "direct_answer":
            answer = _require_text(decision.get("answer"), "answer")
            rejection = direct_answer_rejection_observation(
                decision,
                observations=observations,
            )
            if rejection is not None:
                invalid_direct_answer_rejections += 1
                recovered_answer = recovered_unstructured_direct_answer(
                    decision,
                    rejection_count=invalid_direct_answer_rejections,
                )
                if recovered_answer is not None:
                    yield SupervisorConversationEvent(
                        event="delta",
                        payload={"text": recovered_answer},
                        provider=response.provider,
                        model=response.model,
                        private={
                            "decision_kind": "recovered_unstructured_direct_answer"
                        },
                    )
                    return
                if (
                    invalid_direct_answer_rejections
                    < _INVALID_DIRECT_ANSWER_RECOVERY_LIMIT
                ):
                    observations.append(rejection)
                    continue
            else:
                invalid_direct_answer_rejections = 0
            yield SupervisorConversationEvent(
                event="delta",
                payload={"text": answer},
                provider=response.provider,
                model=response.model,
                private={
                    "decision_kind": (
                        "direct_answer_recovered"
                        if rejection is not None
                        else "direct_answer"
                    )
                },
            )
            return
        if decision["kind"] in {"call_capability", "call_capabilities"}:
            invalid_direct_answer_rejections = 0
            capacity_decisions: list[dict[str, Any]]
            if decision["kind"] == "call_capability":
                capacity_decisions = [decision]
            else:
                calls = decision.get("calls")
                if not isinstance(calls, list) or not calls:
                    yield SupervisorConversationEvent(
                        event="delta",
                        payload={"text": "没有可执行的并行能力调用。"},
                        provider=response.provider,
                        model=response.model,
                    )
                    return
                capacity_decisions = [
                    {"kind": "call_capability", **call}
                    for call in calls
                    if isinstance(call, dict)
                ]
                if not capacity_decisions:
                    yield SupervisorConversationEvent(
                        event="delta",
                        payload={"text": "没有可执行的并行能力调用。"},
                        provider=response.provider,
                        model=response.model,
                    )
                    return
            repeated_failure = repeated_failed_capability_answer(
                capacity_decisions,
                failed_calls=failed_calls,
            )
            if repeated_failure is not None:
                yield SupervisorConversationEvent(
                    event="delta",
                    payload={"text": repeated_failure},
                    provider=response.provider,
                    model=response.model,
                )
                return
            repeated_call = repeated_capability_observation(
                capacity_decisions,
                completed_calls=completed_calls,
            )
            if repeated_call is not None:
                observations.append(repeated_call)
                continue
            base_event_ids = [
                _capacity_event_id(str(capacity_decision.get("capacity_id", "unknown")))
                for capacity_decision in capacity_decisions
            ]
            event_id_counts = {
                base_event_id: base_event_ids.count(base_event_id)
                for base_event_id in set(base_event_ids)
            }
            seen_event_ids: dict[str, int] = {}
            capacity_event_ids: list[str] = []
            for base_event_id in base_event_ids:
                seen_event_ids[base_event_id] = seen_event_ids.get(base_event_id, 0) + 1
                event_id = base_event_id
                if event_id_counts[base_event_id] > 1:
                    event_id = f"{base_event_id}_{seen_event_ids[base_event_id]}"
                capacity_event_ids.append(event_id)
            event_streams = [
                _run_capability_decision(
                    capacity_decision,
                    state_root=Path(state_root).expanduser(),
                    context=context,
                    provider=provider,
                    user_message=clean_message,
                    observations=list(observations),
                    timeout_seconds=timeout_seconds,
                    event_id=event_id,
                )
                for capacity_decision, event_id in zip(
                    capacity_decisions,
                    capacity_event_ids,
                    strict=True,
                )
            ]
            event_iterator = (
                event_streams[0]
                if len(event_streams) == 1
                else run_parallel_event_generators(event_streams)
            )
            for event in event_iterator:
                yield event
                if event.event == "capacity_result":
                    observation = capacity_observation_from_event_payload(
                        payload=event.payload,
                        private=event.private,
                    )
                    observations.append(observation)
                    payload_capacity_id = event.payload.get("capacity_id")
                    if isinstance(payload_capacity_id, str):
                        call_key = event.private.get("capacity_call_key")
                        if not isinstance(call_key, str):
                            call_key = payload_capacity_id
                        if event.payload.get("status") == "error":
                            result_text = event.payload.get(
                                "result",
                                event.payload.get("result_text"),
                            )
                            failed_calls[call_key] = (
                                dict(result_text)
                                if isinstance(result_text, dict)
                                else {}
                            )
                            completed_calls.pop(call_key, None)
                        else:
                            failed_calls.pop(call_key, None)
                            completed_calls[call_key] = observation
            continue
        if decision["kind"] == "report_capability_gap":
            invalid_direct_answer_rejections = 0
            gap = _record_capability_gap(
                decision,
                state_root=Path(state_root).expanduser(),
                user_message=clean_message,
                source_entrypoint=str(context.get("entrypoint", "desktop_chat")),
            )
            yield SupervisorConversationEvent(event="capability_gap", payload=gap)
            yield SupervisorConversationEvent(
                event="delta",
                payload={"text": capability_gap_user_answer(gap)},
                provider=response.provider,
                model=response.model,
            )
            return
    raise ValueError("conversation loop exhausted max_turns without a direct answer")


def _conversation_context(
    *,
    state_root: Path,
    cwd: Path,
    capacity_runner: CapabilityRunner | None,
    terminal_approval_mode: str,
    terminal_allowed_commands: list[str] | None,
) -> dict[str, Any]:
    runner = capacity_runner if capacity_runner is not None else CapabilityRunner()
    raw_capabilities = runner.list_capabilities()
    has_file_read = any(
        capability.get("capability_id") == "file.read"
        for capability in raw_capabilities
    )
    capabilities = [
        {
            "capability_id": capability.get("capability_id"),
            "title": capability.get("title"),
            "description": capability.get("description"),
            "shelf": capability.get("shelf"),
            "domain_tags": capability.get("domain_tags"),
            **_conversation_capability_projection(capability),
        }
        for capability in raw_capabilities
        if not (has_file_read and capability.get("capability_id") == "code.read")
    ]
    return {
        "kind": "supervisor_conversation_context",
        "entrypoint": "desktop_chat",
        "system_context": {
            "state_root": str(state_root),
            "root": str(state_root),
            "cwd": str(cwd),
            "terminal_approval_mode": _terminal_approval_mode(terminal_approval_mode),
            "terminal_allowed_commands": _terminal_allowed_commands(terminal_allowed_commands),
        },
        "capacity_manifest": {
            "kind": "capacity_manifest",
            "source": "registered_capabilities",
            "capability_count": len(capabilities),
            "capabilities": capabilities,
        },
    }


def _conversation_messages(
    user_message: str,
    context: dict[str, Any],
    *,
    history: list[dict[str, str]] | None,
    observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": render_json_prompt_template(
                "supervisor_conversation_loop",
                {"capacity_manifest": context["capacity_manifest"]},
            ),
        },
    ]
    if observations:
        messages.append(
            {
                "role": "user",
                "content": capacity_observation_message_content(observations),
            }
        )
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": user_message})
    return messages


def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if history is None:
        return []
    clean: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        stripped = content.strip()
        if stripped:
            clean.append({"role": role, "content": stripped})
    return compact_desktop_chat_history_messages(clean)


def _conversation_capability_projection(capability: dict[str, Any]) -> dict[str, Any]:
    input_contract = capability.get("input_contract")
    properties = (
        input_contract.get("properties", {})
        if isinstance(input_contract, dict)
        else {}
    )
    public_properties = public_contract_properties(
        input_contract if isinstance(input_contract, dict) else {}
    )
    public_required = public_required_contract_keys(
        input_contract if isinstance(input_contract, dict) else {}
    )
    operation_property = (
        properties.get("operation", {}) if isinstance(properties, dict) else {}
    )
    operations = (
        operation_property.get("enum")
        if isinstance(operation_property, dict)
        else None
    )
    return _omit_empty(
        {
            "capability_id": capability.get("capability_id"),
            "title": capability.get("title"),
            "description": capability.get("description"),
            "shelf": capability.get("shelf"),
            "domain_tags": capability.get("domain_tags"),
            "required_inputs": public_required,
            "input_properties": _conversation_input_properties(public_properties),
            "operations": operations,
            "network_required": capability.get("network_required"),
        }
    )


def _conversation_input_properties(
    properties: dict[str, Any] | Any,
) -> dict[str, dict[str, Any]]:
    if not isinstance(properties, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        if not isinstance(name, str) or not isinstance(schema, dict):
            continue
        property_result = {
            key: schema[key]
            for key in ("type", "enum", "default", "description")
            if key in schema
        }
        if property_result:
            result[name] = property_result
    return result


def _omit_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, [], {})
    }


def _run_capability_decision(
    decision: dict[str, Any],
    *,
    state_root: Path,
    context: dict[str, Any],
    provider: SupervisorConversationProvider,
    user_message: str,
    observations: list[dict[str, Any]] | None,
    timeout_seconds: float | None,
    event_id: str,
) -> Iterator[SupervisorConversationEvent]:
    capacity_id = _require_text(decision.get("capacity_id"), "capacity_id")
    call_key = capacity_call_key(decision)
    arguments = decision.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    inputs = _capability_inputs_from_decision(
        capacity_id,
        arguments=arguments,
        context=context,
        user_message=user_message,
        observations=observations,
    )
    display_inputs = _capacity_display_inputs(capacity_id, inputs)
    title = _capability_title(capacity_id, context=context)
    yield SupervisorConversationEvent(
        event="capacity_start",
        payload={
            "id": event_id,
            "capacity_id": capacity_id,
            "title": title,
            "status": "running",
            "inputs": _safe_detail_value(display_inputs),
            "result": {},
            "details": [
                {
                    "label": "Inputs",
                    "kind": "json",
                    "content": _safe_detail_value(display_inputs),
                }
            ],
        },
    )
    try:
        if capacity_id == CODING_TASK_RUN_CAPABILITY:
            system_context = context.get("system_context")
            if not isinstance(system_context, dict):
                raise ValueError("system_context must be available for coding_task.run")
            agent_loop = run_native_coding_agent_loop(
                state_root=state_root,
                cwd=Path(_require_text(system_context.get("cwd"), "cwd")),
                goal=_require_text(inputs.get("goal"), "goal"),
                inputs=inputs,
                provider=provider,
                max_steps=_scoped_coding_steps(inputs.get("max_steps")),
            )
        else:
            agent_loop = _execute_capacity_step_with_timeout(
                goal=f"Conversation capability call: {capacity_id}",
                capability_id=capacity_id,
                inputs=inputs,
                state_root=state_root / "supervisor" / "conversation-loop-runs",
                timeout_seconds=_capacity_timeout_seconds(capacity_id, timeout_seconds),
            )
        result = agent_loop_json_result({"agent_loop": agent_loop})
        extra_details = [
            detail
            for detail in [
                capability_result_detail_from_agent_loop(
                    capacity_id=capacity_id,
                    agent_loop=agent_loop,
                ),
                screen_artifact_detail_from_agent_loop(agent_loop),
                research_artifact_detail_from_agent_loop(agent_loop),
            ]
            if detail is not None
        ]
        private = {
            "capacity_call_key": call_key,
            "model_observation": model_observation_from_agent_loop(
                capacity_id=capacity_id,
                status="ok",
                result=result,
                agent_loop=agent_loop,
                state_root=state_root,
            )
        }
        status = _capacity_result_status(result)
    except Exception as exc:  # noqa: BLE001 - stream public capacity failure.
        result = {
            "error_type": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
        }
        if isinstance(exc, CapacityExecutionTimeout):
            result["error_type"] = "TimeoutError"
            result["capacity_id"] = exc.capacity_id
            result["timeout_seconds"] = exc.timeout_seconds
        extra_details = []
        private = {
            "capacity_call_key": call_key,
            "model_observation": {
                "kind": "capacity_observation",
                "capacity_id": capacity_id,
                "status": "error",
                "result": result,
            }
        }
        status = "error"
    yield SupervisorConversationEvent(
        event="capacity_result",
        payload={
            "id": event_id,
            "capacity_id": capacity_id,
            "title": title,
            "status": status,
            "inputs": _safe_detail_value(display_inputs),
            "result": _safe_detail_value(result),
            "details": [
                {
                    "label": "Inputs",
                    "kind": "json",
                    "content": _safe_detail_value(display_inputs),
                },
                {
                    "label": "Result",
                    "kind": "json",
                    "content": _safe_detail_value(result),
                },
                *extra_details,
            ],
        },
        private=private,
    )


def _execute_capacity_step_with_timeout(
    *,
    goal: str,
    capability_id: str,
    inputs: dict[str, Any],
    state_root: Path,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    return execute_capacity_step_with_timeout(
        goal=goal,
        capability_id=capability_id,
        inputs=inputs,
        state_root=state_root,
        timeout_seconds=timeout_seconds,
        executor_func=_execute_agent_loop_capacity_step,
    )


def _scoped_coding_steps(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 6
    return min(max(value, 1), 12)


def _capability_inputs_from_decision(
    capacity_id: str,
    *,
    arguments: dict[str, Any],
    context: dict[str, Any],
    user_message: str = "",
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    allowed_inputs = _capability_input_names(capacity_id)
    if not allowed_inputs:
        return dict(arguments)
    inputs = {
        key: value
        for key, value in arguments.items()
        if isinstance(key, str) and key in allowed_inputs
    }
    system_context = context.get("system_context")
    if isinstance(system_context, dict):
        for key, value in system_context.items():
            if key in allowed_inputs or (
                capacity_id == "terminal.exec"
                and key in {"terminal_approval_mode", "terminal_allowed_commands"}
            ):
                inputs[key] = value
    inputs = _apply_conversation_goal_plan_write_route(
        capacity_id,
        inputs=inputs,
        user_message=user_message,
    )
    inputs = _apply_conversation_goal_plan_research_context(
        capacity_id,
        inputs=inputs,
        observations=observations,
    )
    inputs = _normalize_conversation_capability_inputs(capacity_id, inputs)
    return inputs


def _apply_conversation_goal_plan_write_route(
    capacity_id: str,
    *,
    inputs: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    if capacity_id != "supervisor.goal_plan":
        return inputs
    normalized = dict(inputs)
    if not _explicit_goal_plan_write_requested(user_message):
        normalized.pop("write", None)
        return normalized
    normalized["write"] = True
    return normalized


def _apply_conversation_goal_plan_research_context(
    capacity_id: str,
    *,
    inputs: dict[str, Any],
    observations: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if capacity_id != "supervisor.goal_plan" or "research_context" in inputs:
        return inputs
    research_context = research_context_from_observations(observations)
    if not research_context:
        return inputs
    normalized = dict(inputs)
    normalized["research_context"] = research_context
    return normalized


def _explicit_goal_plan_write_requested(user_message: str) -> bool:
    text = user_message.strip()
    if not text:
        return False
    if _goal_plan_queue_write_suppressed(text):
        return False
    write_markers = (
        "写入目标队列",
        "写到目标队列",
        "加入目标队列",
        "加到目标队列",
        "放入目标队列",
        "可以写入",
        "确认写入",
        "同意写入",
        "允许写入",
        "写入吧",
        "就写入",
        "入队",
        "创建目标",
    )
    return any(marker in text for marker in write_markers)


def _goal_plan_queue_write_suppressed(text: str) -> bool:
    if "预览" in text:
        return True
    return re.search(r"(不|别|不用).{0,6}(写|入队|加入|放入)", text) is not None


def _normalize_conversation_capability_inputs(
    capacity_id: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    if capacity_id == "terminal.exec":
        normalized = dict(inputs)
        approval_mode = normalized.pop("terminal_approval_mode", DEFAULT_TERMINAL_APPROVAL_MODE)
        allowed_commands = normalized.pop("terminal_allowed_commands", list(DEFAULT_ALLOWED_COMMANDS))
        normalized.setdefault("approval_mode", _terminal_approval_mode(approval_mode))
        normalized.setdefault("allowed_commands", _terminal_allowed_commands(allowed_commands))
        return normalized
    if capacity_id == "coding_task.execute":
        normalized = dict(inputs)
        normalized.setdefault("run_id", "conversation_loop")
        normalized.setdefault("execution_id", "conversation_loop")
        return normalized
    if capacity_id != "research.search":
        return inputs
    normalized = {
        key: value
        for key, value in inputs.items()
        if key not in {"allow_network", "tavily_max_results"}
    }
    if _configured_tavily_research_available():
        normalized.setdefault("provider", "tavily")
        normalized.setdefault("allow_network", True)
    return normalized


def _configured_tavily_research_available() -> bool:
    if os.environ.get("TAVILY_API_KEY"):
        return True
    try:
        return bool(tavily_api_key_from_config())
    except Exception:
        return False


def _terminal_approval_mode(value: Any) -> str:
    if isinstance(value, str) and value in TERMINAL_APPROVAL_MODES:
        return value
    return DEFAULT_TERMINAL_APPROVAL_MODE


def _terminal_allowed_commands(value: Any) -> list[str]:
    if not isinstance(value, list):
        return list(DEFAULT_ALLOWED_COMMANDS)
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _capability_input_names(capacity_id: str) -> set[str]:
    try:
        capability = CapabilityRunner().describe_capability(capacity_id)
    except ValueError:
        return set()
    input_contract = capability.get("input_contract")
    properties = contract_properties(
        input_contract if isinstance(input_contract, dict) else {}
    )
    return set(properties)


def _capacity_event_id(capacity_id: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in capacity_id.lower())
    return f"capacity_{safe.strip('_') or 'unknown'}"


def _capacity_result_status(result: dict[str, Any]) -> str:
    screen_control = result.get("screen_control")
    if (
        isinstance(screen_control, dict)
        and screen_control.get("status") == "pending_user_approval"
    ):
        return "pending_user_approval"
    terminal_status = result.get("agent_loop_terminal_exec_status")
    if terminal_status == "completed":
        return "ok"
    if terminal_status == "pending_user_approval":
        return "blocked"
    if terminal_status in {"failed", "denied"}:
        return "error"
    research_status = result.get("agent_loop_research_search_status")
    if research_status in {"provider_failed", "validation_failed"}:
        return "blocked"
    if result.get("agent_loop_coding_status") == "verified":
        return "ok"
    return "ok" if result.get("agent_loop_tick_status") == "executed" else "blocked"


def _capability_title(capacity_id: str, *, context: dict[str, Any]) -> str:
    manifest = context.get("capacity_manifest")
    capabilities = manifest.get("capabilities") if isinstance(manifest, dict) else None
    if isinstance(capabilities, list):
        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            if capability.get("capability_id") != capacity_id:
                continue
            title = capability.get("title")
            if isinstance(title, str) and title.strip():
                return title
    return capacity_id


def _capacity_display_inputs(capacity_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if capacity_id == CODING_TASK_RUN_CAPABILITY:
        return {
            key: value
            for key, value in inputs.items()
            if key not in {"root", "cwd", "run_id", "execution_id", "workspace_id"}
        }
    display = dict(inputs)
    if capacity_id == "coding_task.apply_reviewed_diff":
        display.pop("root", None)
        display.pop("cwd", None)
        display.pop("workspace_id", None)
        display.pop("expected_source_digests", None)
        return display
    if capacity_id == "terminal.exec":
        display.pop("root", None)
        display.pop("cwd", None)
        display.pop("allowed_commands", None)
        return display
    if capacity_id == "code.ast_edit":
        display.pop("root", None)
        display.pop("cwd", None)
        replacement = display.get("replacement")
        if isinstance(replacement, str):
            display["replacement"] = {
                "line_count": len(replacement.splitlines()),
                "character_count": len(replacement),
            }
        return display
    if capacity_id in {"supervisor.project_status", "isotope.self_repair"}:
        display.pop("state_root", None)
        display.pop("cwd", None)
        return display
    if capacity_id == "research.search":
        display.pop("provider", None)
        display.pop("allow_network", None)
        display.pop("tavily_max_results", None)
        return display
    if capacity_id.startswith(("skills.", "mcp.")):
        display.pop("cwd", None)
        return display
    if capacity_id != "coding_task.execute":
        return display
    patch = display.get("patch")
    if isinstance(patch, str):
        display["patch"] = {
            "line_count": len(patch.splitlines()),
            "character_count": len(patch),
        }
    argv = display.get("argv")
    if isinstance(argv, list):
        display["argv"] = {
            "argument_count": len(argv),
            "command": argv[0] if argv and isinstance(argv[0], str) else None,
        }
    return display


def _safe_detail_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated: nested content]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 40:
                result["truncated"] = "object contained more than 40 keys"
                break
            if not isinstance(key, str) or _unsafe_detail_key(key):
                continue
            result[key] = _safe_detail_value(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        items = [_safe_detail_value(item, depth=depth + 1) for item in value[:20]]
        if len(value) > 20:
            items.append({"truncated": f"list contained {len(value)} items"})
        return items
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "\n[truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _unsafe_detail_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in (
            "api_key",
            "apikey",
            "secret",
            "token",
            "raw",
            "patch",
            "argv",
            "messages",
            "prompt",
            "transcript",
        )
    )


def _record_capability_gap(
    decision: dict[str, Any],
    *,
    state_root: Path,
    user_message: str,
    source_entrypoint: str,
) -> dict[str, Any]:
    raw_gap = decision.get("gap", {})
    if not isinstance(raw_gap, dict):
        raw_gap = {}
    gap_id = "gap_" + uuid4().hex[:12]
    payload = {
        "kind": "capability_gap",
        "gap_id": gap_id,
        "status": "recorded",
        "missing_capability_kind": _safe_string(
            raw_gap.get("missing_capability_kind"),
            default="unknown",
        ),
        "reason": _safe_string(raw_gap.get("reason"), default="capability gap reported"),
        "needed_context": _safe_string_list(raw_gap.get("needed_context")),
        "user_goal": user_message[:500],
        "suggested_next_capability": _safe_string(
            raw_gap.get("suggested_next_capability"),
            default="",
        ),
        "source_entrypoint": source_entrypoint,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    gap_dir = state_root / "supervisor" / "capability-gaps"
    gap_dir.mkdir(parents=True, exist_ok=True)
    (gap_dir / f"{gap_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def _safe_string(value: Any, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped[:1000]


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:20]:
        if isinstance(item, str) and item.strip():
            result.append(item.strip()[:500])
    return result


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()
