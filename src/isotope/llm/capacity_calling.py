"""LLM-backed capacity selection and argument-filling prototype."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..platform.errors import IsotopeError
from .provider import LLMResponse


_SAFE_CONTRACT_KEYS = {"type", "description", "enum", "items", "properties", "required"}


class CapacityCallingProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class CapacityCallSelection:
    kind: str
    status: str
    capacity_id: str
    arguments: dict[str, Any]
    missing_inputs: list[str]
    confidence: float
    rationale: str
    provider: str
    model: str
    finish_reason: str
    usage: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "capacity_id": self.capacity_id,
            "arguments": copy.deepcopy(self.arguments),
            "missing_inputs": list(self.missing_inputs),
            "confidence": self.confidence,
            "rationale": self.rationale,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "usage": copy.deepcopy(self.usage),
        }


def select_capacity_call(
    provider: CapacityCallingProvider,
    *,
    goal: str,
    capacities: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    max_tokens: int = 512,
) -> CapacityCallSelection:
    """Ask an LLM to select one offered capacity and fill its arguments.

    This helper returns a call plan only. It does not run the selected capacity.
    """

    clean_goal = _require_non_empty_string("goal", goal)
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ValueError("max_tokens must be a positive integer")

    safe_capacities = [_safe_capacity_manifest(capacity) for capacity in capacities]
    if not safe_capacities:
        raise ValueError("capacities must contain at least one capacity")
    offered = {capacity["capacity_id"]: capacity for capacity in safe_capacities}

    try:
        response = provider.generate(
            _build_messages(goal=clean_goal, capacities=safe_capacities),
            max_tokens=max_tokens,
        )
    except IsotopeError:
        raise
    except ValueError as exc:
        raise _invalid_response(provider, "provider rejected capacity-calling request") from exc
    except RuntimeError as exc:
        raise IsotopeError(
            "capacity-calling provider request failed",
            code="llm_capacity_provider_failed",
            category="internal",
            retryable=True,
            http_status=502,
            details={"provider": _safe_provider_name(provider)},
        ) from exc

    payload = _extract_json_object(response.content, provider=provider)
    capacity_id = _payload_string(payload, "capacity_id", provider=provider)
    if capacity_id not in offered:
        raise IsotopeError(
            "provider selected a capacity that was not offered",
            code="llm_capacity_unoffered",
            category="not_enabled",
            retryable=False,
            http_status=501,
            details={"capacity_id": capacity_id},
        )

    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        raise _invalid_response(provider, "capacity arguments must be a JSON object")
    _validate_argument_keys(arguments, capacity=offered[capacity_id], provider=provider)
    confidence = _payload_confidence(payload, provider=provider)
    rationale = _payload_optional_string(payload, "rationale")
    required_inputs = _required_inputs(offered[capacity_id])
    missing_inputs = [
        name
        for name in required_inputs
        if name not in arguments or arguments[name] is None or arguments[name] == ""
    ]

    return CapacityCallSelection(
        kind="capacity_call_selection",
        status="missing_inputs" if missing_inputs else "ready_to_call",
        capacity_id=capacity_id,
        arguments=copy.deepcopy(arguments),
        missing_inputs=missing_inputs,
        confidence=confidence,
        rationale=rationale,
        provider=response.provider,
        model=response.model,
        finish_reason=response.finish_reason,
        usage=_safe_usage(response.usage),
    )


def _build_messages(
    *,
    goal: str,
    capacities: list[dict[str, Any]],
) -> list[dict[str, str]]:
    payload = {
        "goal": goal,
        "capacities": capacities,
        "rules": [
            "Select exactly one offered capacity_id.",
            "Fill only arguments needed by that capacity input_contract.",
            "If a required value is absent from the goal, omit that argument.",
            "Return only a JSON object and do not execute anything.",
        ],
        "required_json_shape": {
            "capacity_id": "string",
            "arguments": "object",
            "confidence": "number between 0 and 1",
            "rationale": "short low-sensitive string",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You select an Isotope capacity and fill its arguments. "
                "Return a single low-sensitive JSON object."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def _safe_capacity_manifest(capacity: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(capacity, Mapping):
        raise ValueError("capacity entries must be mappings")
    return {
        "capacity_id": _require_non_empty_string("capacity_id", capacity.get("capacity_id")),
        "title": _optional_string(capacity.get("title")),
        "description": _optional_string(capacity.get("description")),
        "domain_tags": _safe_string_list(capacity.get("domain_tags", [])),
        "input_contract": _safe_contract(capacity.get("input_contract", {})),
    }


def _safe_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _safe_contract_value(key, child)
        for key, child in value.items()
        if isinstance(key, str) and key in _SAFE_CONTRACT_KEYS
    }


def _safe_contract_value(key: str, value: Any) -> Any:
    if key == "required":
        return _safe_string_list(value)
    if key == "properties" and isinstance(value, Mapping):
        return {
            name: _safe_contract(schema)
            for name, schema in value.items()
            if isinstance(name, str) and isinstance(schema, Mapping)
        }
    if key == "items":
        return _safe_contract(value)
    if key == "enum" and isinstance(value, list):
        return [item for item in value if _is_safe_scalar(item)]
    if _is_safe_scalar(value):
        return value
    return None


def _required_inputs(capacity: Mapping[str, Any]) -> list[str]:
    input_contract = capacity.get("input_contract", {})
    required = input_contract.get("required", []) if isinstance(input_contract, Mapping) else []
    return _safe_string_list(required)


def _validate_argument_keys(
    arguments: Mapping[str, Any],
    *,
    capacity: Mapping[str, Any],
    provider: CapacityCallingProvider,
) -> None:
    input_contract = capacity.get("input_contract", {})
    properties = (
        input_contract.get("properties", {}) if isinstance(input_contract, Mapping) else {}
    )
    if not isinstance(properties, Mapping) or not properties:
        return
    allowed = {key for key in properties if isinstance(key, str)}
    unexpected = sorted(key for key in arguments if key not in allowed)
    if unexpected:
        raise _invalid_response(
            provider,
            "capacity arguments not allowed by capacity input_contract: "
            + ", ".join(unexpected),
        )
    _validate_argument_types(arguments, properties=properties, provider=provider)


def _validate_argument_types(
    arguments: Mapping[str, Any],
    *,
    properties: Mapping[str, Any],
    provider: CapacityCallingProvider,
) -> None:
    for name, value in arguments.items():
        schema = properties.get(name)
        if not isinstance(schema, Mapping):
            continue
        expected_type = schema.get("type")
        if not isinstance(expected_type, str):
            continue
        if not _matches_contract_type(value, expected_type):
            raise _invalid_response(
                provider,
                f"capacity argument {name} does not match input_contract type: "
                f"{expected_type}",
            )


def _matches_contract_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def _extract_json_object(text: str, *, provider: CapacityCallingProvider) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise _invalid_response(provider, "capacity provider returned empty response")
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
            raise _invalid_response(
                provider,
                "capacity provider response must contain a JSON object",
            ) from exc
    if not isinstance(payload, dict):
        raise _invalid_response(provider, "capacity provider response must be a JSON object")
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


def _payload_string(
    payload: Mapping[str, Any],
    key: str,
    *,
    provider: CapacityCallingProvider,
) -> str:
    try:
        return _require_non_empty_string(key, payload.get(key))
    except ValueError as exc:
        raise _invalid_response(provider, f"capacity response field {key} must be a string") from exc


def _payload_optional_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        return ""
    return value.strip()


def _payload_confidence(
    payload: Mapping[str, Any],
    *,
    provider: CapacityCallingProvider,
) -> float:
    value = payload.get("confidence")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _invalid_response(provider, "capacity confidence must be a number")
    if value < 0 or value > 1:
        raise _invalid_response(provider, "capacity confidence must be between 0 and 1")
    return float(value)


def _invalid_response(provider: CapacityCallingProvider, message: str) -> IsotopeError:
    return IsotopeError(
        message,
        code="llm_capacity_invalid_response",
        category="validation",
        retryable=False,
        http_status=400,
        details={"provider": _safe_provider_name(provider)},
    )


def _safe_provider_name(provider: CapacityCallingProvider) -> str:
    value = getattr(provider, "provider", "unknown")
    return value if isinstance(value, str) and value else "unknown"


def _safe_usage(usage: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(usage, Mapping):
        return {}
    return {str(key): value for key, value in usage.items() if _is_safe_scalar(value)}


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _optional_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _require_non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _is_safe_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


__all__ = [
    "CapacityCallingProvider",
    "CapacityCallSelection",
    "select_capacity_call",
]
