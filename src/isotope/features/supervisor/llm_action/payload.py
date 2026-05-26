"""LLM action JSON payload parsing and field validation helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from .llm_pool import _clip_text


def extract_json_object(text: str) -> dict[str, Any]:
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


def normalize_llm_action_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("kind"), str):
        return payload
    action = payload.get("action")
    if not isinstance(action, str) or not action.strip():
        return payload
    normalized = dict(payload)
    normalized["kind"] = action.strip()
    return normalized


def required_payload_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"LLM action field is required: {field}")
    return value.strip()


def optional_payload_string(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def required_payload_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"LLM action field must be bool: {field}")
    return value


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
