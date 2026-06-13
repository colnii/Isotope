"""Thin HTTP dispatch helpers for desktop long-task endpoints."""

from __future__ import annotations

from typing import Any

from isotope.features.supervisor.long_task.runtime import (
    create_long_task,
    list_long_tasks,
    pause_long_task,
    resume_long_task,
    status_long_task,
    stop_long_task,
)

from . import long_tasks as routes


def handle_long_task_get(handler: Any, *, path: str) -> bool:
    if path == "/desktop/long-tasks":
        handler._send_json(list_long_tasks(handler.server.codex_home))
        return True
    task_id = routes.desktop_long_task_id_from_path(path)
    if task_id is not None:
        try:
            handler._send_json(status_long_task(handler.server.codex_home, task_id))
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=404)
        return True
    return False


def handle_long_task_post(handler: Any, *, path: str) -> bool:
    if path == "/desktop/long-tasks":
        try:
            payload = routes.parse_long_task_create_payload(handler._read_json_body())
            handler._send_json(
                create_long_task(handler.server.codex_home, goal=payload["goal"])
            )
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=400)
        return True
    task_id = routes.desktop_long_task_control_id_from_path(path)
    if task_id is not None:
        try:
            payload = routes.parse_long_task_control_payload(handler._read_json_body())
            if payload["control"] == "pause":
                result = pause_long_task(
                    handler.server.codex_home,
                    task_id,
                    reason=payload["reason"],
                )
            elif payload["control"] == "resume":
                result = resume_long_task(
                    handler.server.codex_home,
                    task_id,
                    reason=payload["reason"],
                )
            else:
                result = stop_long_task(
                    handler.server.codex_home,
                    task_id,
                    reason=payload["reason"],
                )
            handler._send_json(result)
        except ValueError as exc:
            _send_error(handler, str(exc), status_code=400)
        return True
    return False


def _send_error(handler: Any, message: str, *, status_code: int) -> None:
    handler._send_json(
        {
            "status": "error",
            "error": {
                "code": "codex_supervisor_web_error",
                "message": message,
            },
        },
        status_code=status_code,
    )
