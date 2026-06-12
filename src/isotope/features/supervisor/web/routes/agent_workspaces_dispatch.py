"""Thin HTTP dispatch helpers for desktop Agent Workspace endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...agent_group.workspace import api as workspace_api
from . import agent_workspaces as routes


ERROR_CODE = "codex_supervisor_web_error"


def handle_agent_workspace_get(
    handler: Any,
    *,
    path: str,
    query: str,
    root_path: Path,
) -> bool:
    if path == "/desktop/agent-workspaces":
        handler._send_json(
            workspace_api.list_workspaces_payload(
                handler.server.codex_home,
                root_path=root_path,
            )
        )
        return True
    workspace_id = routes.agent_workspace_codex_sessions_id_from_path(path)
    if workspace_id is not None:
        try:
            scope = routes.parse_codex_session_scope(query)
            payload = workspace_api.codex_sessions_payload(
                handler.server.codex_home,
                workspace_id=workspace_id,
                scope=scope,
            )
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=400)
            return True
        handler._send_json(payload)
        return True
    workspace_id = routes.agent_workspace_id_from_path(path)
    if workspace_id is not None:
        try:
            payload = workspace_api.workspace_payload(
                handler.server.codex_home,
                workspace_id,
            )
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=404)
            return True
        handler._send_json(payload)
        return True
    return False


def handle_agent_workspace_post(handler: Any, *, path: str) -> bool:
    workspace_id = routes.agent_workspace_channels_id_from_path(path)
    if workspace_id is not None:
        return _handle_create_channel(handler, workspace_id)
    member_ids = routes.channel_members_path_ids(path)
    if member_ids is not None:
        return _handle_member_action(handler, member_ids)
    chat_ids = routes.conversation_chat_path_ids(path)
    if chat_ids is not None:
        return _handle_chat(handler, chat_ids)
    control_ids = routes.conversation_control_path_ids(path)
    if control_ids is not None:
        return _handle_control(handler, control_ids)
    return False


def _handle_create_channel(handler: Any, workspace_id: str) -> bool:
    try:
        payload = routes.parse_workspace_channel_payload(handler._read_json_body())
        result = workspace_api.create_channel_payload(
            handler.server.codex_home,
            workspace_id=workspace_id,
            name=payload["name"],
            topic=payload["topic"],
        )
    except ValueError as exc:
        _send_error(handler, str(exc), status_code=400)
        return True
    handler._send_json(result)
    return True


def _handle_member_action(
    handler: Any,
    member_ids: tuple[str, str, str | None],
) -> bool:
    workspace_id, channel_id, member_id = member_ids
    try:
        body = handler._read_json_body()
        if member_id is None:
            payload = routes.parse_channel_member_payload(body)
            result = workspace_api.add_channel_member_payload(
                handler.server.codex_home,
                workspace_id=workspace_id,
                channel_id=channel_id,
                **payload,
            )
        else:
            result = _member_update_or_remove(handler, member_ids, body)
    except ValueError as exc:
        _send_error(handler, str(exc), status_code=400)
        return True
    handler._send_json(result)
    return True


def _member_update_or_remove(
    handler: Any,
    member_ids: tuple[str, str, str | None],
    body: object,
) -> dict[str, Any]:
    workspace_id, channel_id, member_id = member_ids
    if member_id is None or not isinstance(body, dict):
        raise ValueError("member action payload must be an object")
    action = body.get("action")
    if action == "remove":
        return workspace_api.remove_channel_member_payload(
            handler.server.codex_home,
            workspace_id=workspace_id,
            channel_id=channel_id,
            member_id=member_id,
        )
    if action != "update":
        raise ValueError("member action must be update or remove")
    payload = routes.parse_workspace_member_update_payload(body)
    return workspace_api.update_channel_member_payload(
        handler.server.codex_home,
        workspace_id=workspace_id,
        channel_id=channel_id,
        member_id=member_id,
        send_policy=payload["send_policy"],
        status=payload["status"],
        role=payload["role"],
        goal=payload["goal"],
    )


def _handle_chat(handler: Any, ids: tuple[str, str]) -> bool:
    workspace_id, conversation_id = ids
    try:
        payload = routes.parse_workspace_chat_payload(handler._read_json_body())
        result = workspace_api.conversation_chat_payload(
            handler.server.codex_home,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message=payload["message"],
            mode=payload["mode"],
        )
    except ValueError as exc:
        _send_error(handler, str(exc), status_code=400)
        return True
    handler._send_json(result)
    return True


def _handle_control(handler: Any, ids: tuple[str, str]) -> bool:
    workspace_id, conversation_id = ids
    try:
        payload = routes.parse_workspace_control_payload(handler._read_json_body())
        result = workspace_api.conversation_control_payload(
            handler.server.codex_home,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            intent=str(payload["intent"]),
            target=str(payload["target"]),
            target_member_id=payload["target_member_id"],
            reason=str(payload["reason"]),
        )
    except ValueError as exc:
        _send_error(handler, str(exc), status_code=400)
        return True
    handler._send_json(result)
    return True


def _send_error(handler: Any, message: str, *, status_code: int) -> None:
    handler._send_json(
        {
            "status": "error",
            "error": {
                "code": ERROR_CODE,
                "message": message,
            },
        },
        status_code=status_code,
    )
