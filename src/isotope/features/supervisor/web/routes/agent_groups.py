"""Desktop Agent Group Chat route helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote


def agent_group_id_from_path(path: str) -> str | None:
    prefix = "/desktop/agent-groups/"
    if not path.startswith(prefix):
        return None
    group_id = unquote(path[len(prefix) :])
    if "/" in group_id or not group_id:
        return None
    return group_id


def agent_group_child_id_from_path(path: str, *, suffix: str) -> str | None:
    prefix = "/desktop/agent-groups/"
    full_suffix = f"/{suffix.strip('/')}"
    if not path.startswith(prefix) or not path.endswith(full_suffix):
        return None
    group_id = unquote(path[len(prefix) : -len(full_suffix)])
    if "/" in group_id or not group_id:
        return None
    return group_id


def codex_session_id_from_transcript_path(path: str) -> str | None:
    prefix = "/desktop/codex-sessions/"
    suffix = "/transcript"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    session_id = unquote(path[len(prefix) : -len(suffix)])
    if "/" in session_id or not session_id:
        return None
    return session_id


def parse_agent_group_chat_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    message = _required_string(value.get("message"), "message")
    mode = _required_string(value.get("mode"), "mode")
    if mode not in {"queue", "interrupt"}:
        raise ValueError("mode must be queue or interrupt")
    return {"message": message, "mode": mode}


def parse_agent_group_control_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    intent = _required_string(value.get("intent"), "intent")
    target = _required_string(value.get("target"), "target")
    target_member_id = _optional_string(value.get("target_member_id"))
    reason = _required_string(value.get("reason"), "reason")
    if intent not in {"queue", "interrupt", "terminate"}:
        raise ValueError("intent must be queue, interrupt, or terminate")
    if target not in {"current_run", "member"}:
        raise ValueError("target must be current_run or member")
    if target == "member" and not target_member_id:
        raise ValueError("target_member_id is required for member target")
    return {
        "intent": intent,
        "target": target,
        "target_member_id": target_member_id,
        "reason": reason,
    }


def parse_codex_transcript_query(query: str) -> dict[str, int | bool]:
    params = parse_qs(query)
    return {
        "offset": _query_int(params, "offset", default=0),
        "limit": _query_int(params, "limit", default=200),
        "include_raw": _query_bool(params, "include_raw", default=False),
        "latest": _query_bool(params, "latest", default=False),
    }


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _query_int(params: dict[str, list[str]], field: str, *, default: int) -> int:
    values = params.get(field)
    raw = values[0] if values else None
    if raw is None or raw == "":
        return default
    try:
        number = int(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < 0:
        raise ValueError(f"{field} must be zero or positive")
    return number


def _query_bool(params: dict[str, list[str]], field: str, *, default: bool) -> bool:
    values = params.get(field)
    raw = values[0].strip().lower() if values else ""
    if not raw:
        return default
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    raise ValueError(f"{field} must be a boolean")
