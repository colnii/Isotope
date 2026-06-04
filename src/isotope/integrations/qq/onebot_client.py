"""Small OneBot client surface used by the QQ adapter tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeOneBotClient:
    fail_send: bool = False
    queued_events: list[dict[str, Any]] = field(default_factory=list)
    sent_group_messages: list[dict[str, Any]] = field(default_factory=list)
    sent_private_messages: list[dict[str, Any]] = field(default_factory=list)
    connected: bool = True

    def queue_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise ValueError("event must be a dict")
        self.queued_events.append(dict(event))

    def receive_event(self) -> dict[str, Any] | None:
        if not self.queued_events:
            return None
        return self.queued_events.pop(0)

    def send_group_msg(
        self,
        *,
        group_id: str,
        message: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.fail_send:
            raise RuntimeError("OneBot send failed")
        payload = {"group_id": group_id, "message": _copy_segments(message)}
        self.sent_group_messages.append(payload)
        return {
            "status": "ok",
            "message_id": f"onebot_group_{len(self.sent_group_messages)}",
        }

    def send_private_msg(
        self,
        *,
        user_id: str,
        message: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if self.fail_send:
            raise RuntimeError("OneBot send failed")
        payload = {"user_id": user_id, "message": _copy_segments(message)}
        self.sent_private_messages.append(payload)
        return {
            "status": "ok",
            "message_id": f"onebot_private_{len(self.sent_private_messages)}",
        }


def _copy_segments(message: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(message, list):
        raise ValueError("message must be a list")
    copied: list[dict[str, Any]] = []
    for segment in message:
        if not isinstance(segment, dict):
            raise ValueError("message segments must be dicts")
        copied.append(
            {
                "type": segment.get("type"),
                "data": dict(segment.get("data", {})),
            }
        )
    return copied
