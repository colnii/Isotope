"""Desktop long-task route helpers."""

from __future__ import annotations

from urllib.parse import unquote


LONG_TASK_PREFIX = "/desktop/long-tasks/"


def desktop_long_task_id_from_path(path: str) -> str | None:
    if not path.startswith(LONG_TASK_PREFIX):
        return None
    task_id = unquote(path[len(LONG_TASK_PREFIX) :])
    if "/" in task_id or not task_id:
        return None
    return task_id


def desktop_long_task_control_id_from_path(path: str) -> str | None:
    suffix = "/control"
    if not path.startswith(LONG_TASK_PREFIX) or not path.endswith(suffix):
        return None
    task_id = unquote(path[len(LONG_TASK_PREFIX) : -len(suffix)])
    if "/" in task_id or not task_id:
        return None
    return task_id


def parse_long_task_create_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    goal = _required_string(value.get("goal"), "goal")
    return {"goal": goal}


def parse_long_task_control_payload(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    control = _required_string(value.get("control"), "control")
    reason = _required_string(value.get("reason"), "reason")
    if control not in {"pause", "resume", "stop"}:
        raise ValueError("control must be pause, resume, or stop")
    return {"control": control, "reason": reason}


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()
