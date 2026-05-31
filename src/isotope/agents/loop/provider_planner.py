"""LLM provider adapter for one Agent loop planner tick."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Protocol

from ...llm.provider import LLMResponse
from .context import (
    build_agent_loop_default_context,
    safe_agent_loop_default_context,
)
from .planner_contract import RAW_PROVIDER_FIELDS


class AgentLoopPlannerProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        ...


def run_agent_loop_provider_planner_tick(
    api: Any,
    run_id: str,
    *,
    provider: AgentLoopPlannerProvider,
    agent_id: str,
    tick_id: str,
    decision_id: str,
    tick_budget: dict[str, Any] | None = None,
    user_pause: dict[str, Any] | None = None,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Ask a provider for one planner decision, then execute it through loop contracts."""
    _require_string(run_id, "run_id")
    if not hasattr(provider, "generate") or not callable(provider.generate):
        raise ValueError("provider must expose generate(messages, max_tokens=...)")
    _require_string(agent_id, "agent_id")
    _require_string(tick_id, "tick_id")
    _require_string(decision_id, "decision_id")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")

    before_policy = api.get_agent_loop_tick_policy(
        run_id,
        tick_budget=deepcopy(tick_budget),
        user_pause=deepcopy(user_pause),
    )
    if before_policy["should_continue"] is not True:
        return {
            "kind": "agent_loop_provider_planner_tick",
            "tick_status": "stopped",
            "stop_reason": before_policy["must_stop_reason"],
            "before_policy": before_policy,
            "provider_result": None,
            "planner_contract_result": None,
            "after_policy": before_policy,
            "safety": _safety(max_tokens=max_tokens),
        }

    control = api.get_agent_loop_control(run_id)
    default_context = build_agent_loop_default_context(
        api,
        run_id,
        control=control,
    )
    provider_result = build_agent_loop_provider_planner_result(
        provider,
        control=control,
        default_context=default_context,
        agent_id=agent_id,
        tick_id=tick_id,
        decision_id=decision_id,
        max_tokens=max_tokens,
    )
    contract_result = api.run_agent_loop_real_planner_contract_step(run_id, provider_result)
    after_policy = api.get_agent_loop_tick_policy(
        run_id,
        tick_budget=_advance_tick_budget(tick_budget),
        user_pause=deepcopy(user_pause),
    )
    return {
        "kind": "agent_loop_provider_planner_tick",
        "tick_status": "executed",
        "stop_reason": after_policy["must_stop_reason"],
        "before_policy": before_policy,
        "provider_result": provider_result,
        "planner_contract_result": contract_result,
        "after_policy": after_policy,
        "safety": _safety(max_tokens=max_tokens),
    }


def build_agent_loop_provider_planner_result(
    provider: AgentLoopPlannerProvider,
    *,
    control: dict[str, Any],
    default_context: dict[str, Any] | None = None,
    agent_id: str,
    tick_id: str,
    decision_id: str,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Return quarantined provider output shaped for the real planner contract."""
    messages = _build_planner_messages(
        control=control,
        default_context=default_context,
        agent_id=agent_id,
        tick_id=tick_id,
        decision_id=decision_id,
    )
    response = provider.generate(messages, max_tokens=max_tokens)
    payload = _extract_json_object(response.content)
    _reject_raw_provider_payload(payload)
    parsed_output = _parsed_planner_output(
        payload,
        agent_id=agent_id,
        tick_id=tick_id,
        decision_id=decision_id,
    )
    return {
        "provider_result_id": f"provider_result:{decision_id}",
        "provider_status": "completed",
        "provider": _safe_provider_name(response),
        "model": _safe_model_name(response),
        "finish_reason": _safe_string(getattr(response, "finish_reason", "")),
        "usage": _safe_usage(getattr(response, "usage", {})),
        "agent_id": agent_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "raw_prompt_quarantined": True,
        "raw_response_quarantined": True,
        "parsed_planner_output": parsed_output,
        "planner_output_summary": {
            "planner_run_id": parsed_output["planner_run_id"],
            "selected_step": parsed_output["decision"]["step"],
            "agent_id": agent_id,
            "tick_id": tick_id,
            "decision_id": decision_id,
            "provider": _safe_provider_name(response),
            "model": _safe_model_name(response),
        },
    }


def _build_planner_messages(
    *,
    control: dict[str, Any],
    default_context: dict[str, Any] | None,
    agent_id: str,
    tick_id: str,
    decision_id: str,
) -> list[dict[str, str]]:
    payload = {
        "agent_id": agent_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "control": _safe_control(control),
        "default_context": safe_agent_loop_default_context(default_context),
        "rules": [
            "Return only a JSON object.",
            "Choose exactly one available step from control.next_actions.",
            "Use default_context.memory before selecting query_memory.",
            "Choose query_memory only when default_context.memory is insufficient.",
            "Do not execute tools or mutate state.",
            "Do not include raw prompt, raw response, messages, stdout, or artifact content.",
        ],
        "required_json_shape": {
            "planner_run_id": "string",
            "agent_id": agent_id,
            "tick_id": tick_id,
            "decision_id": decision_id,
            "basis": {
                "run_id": control.get("run_id"),
                "last_event_id": control.get("last_event_id"),
            },
            "decision": {
                "step": "one of control.next_actions",
                "request": "object",
            },
            "rationale": "short low-sensitive string",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You are an Isotope Agent loop planner. Select one symbolic "
                "planner decision. You never execute actions directly."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def _safe_control(control: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": control.get("run_id"),
        "phase": control.get("phase"),
        "last_event_id": control.get("last_event_id"),
        "next_actions": list(control.get("next_actions", [])),
        "pending_approvals": int(control.get("pending_approvals", 0)),
    }


def _parsed_planner_output(
    payload: dict[str, Any],
    *,
    agent_id: str,
    tick_id: str,
    decision_id: str,
) -> dict[str, Any]:
    planner_run_id = _payload_string(payload, "planner_run_id")
    _validate_optional_match(payload, "agent_id", agent_id)
    _validate_optional_match(payload, "tick_id", tick_id)
    _validate_optional_match(payload, "decision_id", decision_id)
    basis = payload.get("basis")
    if not isinstance(basis, dict):
        raise ValueError("planner basis must be a dict")
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        raise ValueError("planner decision must be a dict")
    step = _payload_string(decision, "step")
    request = decision.get("request", {})
    if not isinstance(request, dict):
        raise ValueError("planner decision request must be a dict")
    return {
        "planner_run_id": planner_run_id,
        "agent_id": agent_id,
        "tick_id": tick_id,
        "decision_id": decision_id,
        "basis": deepcopy(basis),
        "decision": {
            "step": step,
            "request": deepcopy(request),
        },
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("planner provider returned empty response")
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        try:
            payload = _first_json_object(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError("planner provider response must contain a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("planner provider response must be a JSON object")
    return payload


def _first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise json.JSONDecodeError("no JSON object", text, 0)


def _advance_tick_budget(tick_budget: dict[str, Any] | None) -> dict[str, Any] | None:
    if tick_budget is None:
        return None
    advanced = deepcopy(tick_budget)
    ticks_used = advanced.get("ticks_used", 0)
    if isinstance(ticks_used, bool) or not isinstance(ticks_used, int):
        return advanced
    advanced["ticks_used"] = ticks_used + 1
    return advanced


def _validate_optional_match(payload: dict[str, Any], field_name: str, expected: str) -> None:
    value = payload.get(field_name)
    if value is None:
        return
    if value != expected:
        raise ValueError(f"planner field {field_name} does not match tick context")


def _payload_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    return _require_string(value, field_name)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _reject_raw_provider_payload(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = RAW_PROVIDER_FIELDS.intersection(value)
        if forbidden:
            raise ValueError("raw planner provider payload is not accepted")
        for nested in value.values():
            _reject_raw_provider_payload(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_raw_provider_payload(nested)


def _safe_usage(usage: Any) -> dict[str, Any]:
    if not isinstance(usage, dict):
        return {}
    return {
        str(key): value
        for key, value in usage.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }


def _safe_provider_name(response: LLMResponse) -> str:
    return _safe_string(getattr(response, "provider", "unknown")) or "unknown"


def _safe_model_name(response: LLMResponse) -> str:
    return _safe_string(getattr(response, "model", "unknown")) or "unknown"


def _safe_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safety(*, max_tokens: int) -> dict[str, Any]:
    return {
        "real_llm_provider": True,
        "provider_executes_actions": False,
        "raw_prompt_quarantined": True,
        "raw_response_quarantined": True,
        "bounded": True,
        "max_tokens": max_tokens,
    }
