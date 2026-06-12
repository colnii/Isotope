"""Route parsing helpers for desktop Agent Workspace endpoints."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote


WORKSPACE_PREFIX = "/desktop/agent-workspaces/"


def agent_workspace_id_from_path(path: str) -> str | None:
    if not path.startswith(WORKSPACE_PREFIX):
        return None
    rest = path[len(WORKSPACE_PREFIX) :]
    if "/" in rest or not rest:
        return None
    return unquote(rest)


def agent_workspace_codex_sessions_id_from_path(path: str) -> str | None:
    suffix = "/codex-sessions"
    if not path.startswith(WORKSPACE_PREFIX) or not path.endswith(suffix):
        return None
    workspace_id = path[len(WORKSPACE_PREFIX) : -len(suffix)]
    if "/" in workspace_id or not workspace_id:
        return None
    return unquote(workspace_id)


def agent_workspace_channels_id_from_path(path: str) -> str | None:
    suffix = "/channels"
    if not path.startswith(WORKSPACE_PREFIX) or not path.endswith(suffix):
        return None
    workspace_id = path[len(WORKSPACE_PREFIX) : -len(suffix)]
    if "/" in workspace_id or not workspace_id:
        return None
    return unquote(workspace_id)


def channel_members_path_ids(path: str) -> tuple[str, str, str | None] | None:
    return _workspace_nested_ids(
        path,
        marker="/channels/",
        suffix="/members",
        allow_child=True,
    )


def conversation_chat_path_ids(path: str) -> tuple[str, str] | None:
    parsed = _workspace_nested_ids(
        path,
        marker="/conversations/",
        suffix="/chat",
        allow_child=False,
    )
    return None if parsed is None else (parsed[0], parsed[1])


def conversation_control_path_ids(path: str) -> tuple[str, str] | None:
    parsed = _workspace_nested_ids(
        path,
        marker="/conversations/",
        suffix="/control",
        allow_child=False,
    )
    return None if parsed is None else (parsed[0], parsed[1])


def parse_codex_session_scope(query: str) -> str:
    params = parse_qs(query)
    scope = (params.get("scope") or ["cwd"])[0]
    if scope not in {"cwd", "all"}:
        raise ValueError("scope must be cwd or all")
    return scope


def parse_channel_member_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    send_policy = _required_string(value.get("send_policy"), "send_policy")
    if send_policy not in {"auto", "confirm", "draft_only"}:
        raise ValueError("send_policy must be auto, confirm, or draft_only")
    return {
        "display_name": _required_string(value.get("display_name"), "display_name"),
        "role": _required_string(value.get("role"), "role"),
        "goal": _optional_string(value.get("goal")) or "",
        "send_policy": send_policy,
        "resume_session_id": _optional_string(value.get("resume_session_id")),
        "source_path": _optional_string(value.get("source_path")),
        "managed_record_id": _optional_string(value.get("managed_record_id")),
    }


def parse_workspace_chat_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    message = _required_string(value.get("message"), "message")
    mode = _required_string(value.get("mode"), "mode")
    if mode not in {"queue", "interrupt"}:
        raise ValueError("mode must be queue or interrupt")
    return {"message": message, "mode": mode}


def parse_workspace_channel_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    return {
        "name": _required_string(value.get("name"), "name"),
        "topic": _optional_string(value.get("topic")) or "",
    }


def parse_workspace_control_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    intent = _required_string(value.get("intent"), "intent")
    target = _required_string(value.get("target"), "target")
    if intent not in {"queue", "interrupt", "terminate"}:
        raise ValueError("intent must be queue, interrupt, or terminate")
    if target not in {"current_run", "member"}:
        raise ValueError("target must be current_run or member")
    target_member_id = _optional_string(value.get("target_member_id"))
    if target == "member" and not target_member_id:
        raise ValueError("target_member_id is required for member target")
    return {
        "intent": intent,
        "target": target,
        "target_member_id": target_member_id,
        "reason": _required_string(value.get("reason"), "reason"),
    }


def parse_workspace_member_update_payload(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    send_policy = _optional_string(value.get("send_policy"))
    if send_policy is not None and send_policy not in {
        "auto",
        "confirm",
        "draft_only",
    }:
        raise ValueError("send_policy must be auto, confirm, or draft_only")
    status = _optional_string(value.get("status"))
    if status is not None and status not in {
        "active",
        "running",
        "idle",
        "needs_user",
        "terminated",
        "blocked",
        "archived",
    }:
        raise ValueError("status is not supported")
    return {
        "send_policy": send_policy,
        "status": status,
        "role": _optional_string(value.get("role")),
        "goal": _optional_string(value.get("goal")),
    }


def _workspace_nested_ids(
    path: str,
    *,
    marker: str,
    suffix: str,
    allow_child: bool,
) -> tuple[str, str, str | None] | None:
    if not path.startswith(WORKSPACE_PREFIX):
        return None
    rest = path[len(WORKSPACE_PREFIX) :]
    if marker not in rest:
        return None
    workspace_id, remainder = rest.split(marker, 1)
    if not workspace_id:
        return None
    if allow_child:
        if remainder.endswith(suffix):
            child = remainder[: -len(suffix)]
            if "/" in child or not child:
                return None
            return (unquote(workspace_id), unquote(child), None)
        marker_with_slash = f"{suffix}/"
        if marker_with_slash not in remainder:
            return None
        parent, child = remainder.split(marker_with_slash, 1)
        if "/" in parent or "/" in child or not parent or not child:
            return None
        return (unquote(workspace_id), unquote(parent), unquote(child))
    if not remainder.endswith(suffix):
        return None
    parent = remainder[: -len(suffix)]
    if "/" in parent or not parent:
        return None
    return (unquote(workspace_id), unquote(parent), None)


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
