"""Parse Supervisor conversation provider output into decision objects."""

from __future__ import annotations

import json
import re
from typing import Any


_DECISION_KINDS = {
    "direct_answer",
    "call_capability",
    "call_capabilities",
    "report_capability_gap",
}


def parse_decision(content: str) -> dict[str, Any]:
    stripped = _require_text(content, "provider response")
    payload = _json_object(stripped)
    if payload is None:
        payload = _embedded_decision_object(stripped)
    if payload is None:
        return _direct_answer(stripped, parse_status="non_json")
    if _decision_kind(payload) not in _DECISION_KINDS:
        return _direct_answer(stripped)
    return dict(payload)


def _json_object(content: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _embedded_decision_object(content: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", content):
        try:
            payload, _end = decoder.raw_decode(content[match.start() :])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if _decision_kind(payload) in _DECISION_KINDS:
            return payload
    return None


def _decision_kind(payload: dict[str, Any]) -> str:
    kind = payload.get("kind")
    return kind if isinstance(kind, str) else ""


def _direct_answer(content: str, *, parse_status: str | None = None) -> dict[str, Any]:
    answer: dict[str, Any] = {"kind": "direct_answer", "answer": content}
    if parse_status is not None:
        answer["_parse_status"] = parse_status
    return answer


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
