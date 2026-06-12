"""Thin HTTP dispatch helpers for desktop Agent Workspace endpoints."""

from __future__ import annotations

import time
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
    workspace_id = routes.agent_workspace_events_id_from_path(path)
    if workspace_id is not None:
        _handle_workspace_events(handler, workspace_id)
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
    workspace_id = routes.agent_workspace_id_from_path(path)
    if workspace_id is not None:
        return _handle_update_workspace(handler, workspace_id)
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


def _handle_update_workspace(handler: Any, workspace_id: str) -> bool:
    try:
        payload = routes.parse_workspace_update_payload(handler._read_json_body())
        result = workspace_api.update_workspace_payload(
            handler.server.codex_home,
            workspace_id=workspace_id,
            title=payload["title"],
            root_path=payload["root_path"],
        )
    except ValueError as exc:
        _send_error(handler, str(exc), status_code=400)
        return True
    handler._send_json(result)
    return True


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


def _handle_workspace_events(handler: Any, workspace_id: str) -> None:
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream; charset=utf-8")
    handler.send_header("cache-control", "no-store")
    handler.send_header("connection", "keep-alive")
    handler._send_cors_headers()
    handler.end_headers()
    handler._write_sse("ready", {"status": "ok", "workspace_id": workspace_id})
    try:
        payload = workspace_api.workspace_payload(handler.server.codex_home, workspace_id)
    except ValueError as exc:
        handler._write_sse(
            "error",
            {"status": "error", "code": ERROR_CODE, "message": str(exc)},
        )
        return
    previous_signature = _workspace_event_signature(payload)
    if not _safe_write_sse(handler, "workspace_update", payload):
        return
    last_heartbeat = time.monotonic()
    while True:
        time.sleep(1.0)
        if time.monotonic() - last_heartbeat >= 15:
            if not _safe_write_sse(
                handler,
                "heartbeat",
                {"status": "ok", "workspace_id": workspace_id},
            ):
                return
            last_heartbeat = time.monotonic()
        try:
            payload = workspace_api.workspace_payload(handler.server.codex_home, workspace_id)
        except ValueError as exc:
            _safe_write_sse(
                handler,
                "error",
                {"status": "error", "code": ERROR_CODE, "message": str(exc)},
            )
            return
        signature = _workspace_event_signature(payload)
        if signature == previous_signature:
            continue
        previous_signature = signature
        if not _safe_write_sse(handler, "workspace_update", payload):
            return


def _safe_write_sse(handler: Any, event: str, payload: dict[str, Any]) -> bool:
    try:
        handler._write_sse(event, payload)
    except OSError:
        return False
    return True


def _workspace_event_signature(payload: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    workspace = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    return (
        (str(workspace.get("updated_at") or ""),),
        tuple(
            f"{item.get('channel_id')}:{item.get('updated_at')}"
            for item in payload.get("channels") or []
            if isinstance(item, dict)
        ),
        tuple(
            f"{item.get('dm_id')}:{item.get('updated_at')}"
            for item in payload.get("direct_messages") or []
            if isinstance(item, dict)
        ),
        tuple(
            f"{item.get('member_id')}:{item.get('updated_at')}"
            for item in payload.get("members") or []
            if isinstance(item, dict)
        ),
        tuple(
            str(item.get("message_id") or "")
            for item in payload.get("messages") or []
            if isinstance(item, dict)
        ),
        tuple(
            _control_event_signature(item)
            for item in payload.get("controls") or []
            if isinstance(item, dict)
        ),
    )


def _control_event_signature(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return str(payload.get("control_id") or event.get("event_id") or "")


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
