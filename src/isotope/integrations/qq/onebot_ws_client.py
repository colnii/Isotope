"""Synchronous OneBot 11 WebSocket client for NapCat live runs."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol

from .onebot_adapter import OneBotConnectionState


class _WebSocketConnection(Protocol):
    def send(self, payload: str) -> None: ...

    def recv(self, *, timeout: float | None = None) -> str: ...

    def close(self) -> None: ...


_Connector = Callable[..., _WebSocketConnection]


class OneBotWebSocketClient:
    def __init__(
        self,
        url: str,
        *,
        access_token: str | None = None,
        request_timeout_seconds: float = 5.0,
        receive_timeout_seconds: float = 30.0,
        connector: _Connector | None = None,
    ):
        if not isinstance(url, str) or not url.strip():
            raise ValueError("websocket url must be a non-empty string")
        self.url = url.strip()
        self.access_token = access_token.strip() if isinstance(access_token, str) else None
        self.request_timeout_seconds = _positive_timeout(
            request_timeout_seconds,
            "request_timeout_seconds",
        )
        self.receive_timeout_seconds = _positive_timeout(
            receive_timeout_seconds,
            "receive_timeout_seconds",
        )
        self._connector = connector
        self._connection: _WebSocketConnection | None = None
        self._queued_events: list[dict[str, Any]] = []
        self._pending_api_responses: dict[str, dict[str, Any]] = {}
        self._api_sequence = 0

    def receive_event(self) -> dict[str, Any] | None:
        if self._queued_events:
            return self._queued_events.pop(0)
        while True:
            frame = self._recv_json(timeout=self.receive_timeout_seconds)
            if _is_api_response(frame):
                echo = str(frame["echo"])
                self._pending_api_responses[echo] = frame
                continue
            return frame

    def send_group_msg(
        self,
        *,
        group_id: str,
        message: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._call_api(
            "send_group_msg",
            {
                "group_id": str(group_id),
                "message": _copy_segments(message),
            },
        )

    def send_private_msg(
        self,
        *,
        user_id: str,
        message: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._call_api(
            "send_private_msg",
            {
                "user_id": str(user_id),
                "message": _copy_segments(message),
            },
        )

    def connection_state(self) -> OneBotConnectionState:
        return OneBotConnectionState(
            connected=self._connection is not None,
            pending_events=len(self._queued_events),
            seen_message_count=0,
            api_sequence=self._api_sequence,
        )

    def connect(self) -> None:
        self._connection_or_connect()

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None

    def _call_api(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        self._api_sequence += 1
        echo = f"isotope-onebot-{self._api_sequence}"
        payload = {
            "action": action,
            "params": params,
            "echo": echo,
        }
        self._connection_or_connect().send(json.dumps(payload, ensure_ascii=False))
        response = self._take_api_response(action=action, echo=echo)
        return _normalize_api_response(action=action, response=response)

    def _take_api_response(self, *, action: str, echo: str) -> dict[str, Any]:
        if echo in self._pending_api_responses:
            return self._pending_api_responses.pop(echo)
        while True:
            try:
                frame = self._recv_json(timeout=self.request_timeout_seconds)
            except TimeoutError as exc:
                raise TimeoutError(f"{action} response timed out for echo {echo}") from exc
            if _is_api_response(frame):
                frame_echo = str(frame["echo"])
                if frame_echo == echo:
                    return frame
                self._pending_api_responses[frame_echo] = frame
                continue
            self._queued_events.append(frame)

    def _recv_json(self, *, timeout: float) -> dict[str, Any]:
        raw = self._connection_or_connect().recv(timeout=timeout)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("OneBot WebSocket frame must be a JSON object")
        return payload

    def _connection_or_connect(self) -> _WebSocketConnection:
        if self._connection is None:
            self._connection = self._connect()
        return self._connection

    def _connect(self) -> _WebSocketConnection:
        connector = self._connector or _default_connector()
        headers = (
            {"Authorization": f"Bearer {self.access_token}"}
            if self.access_token
            else None
        )
        return connector(self.url, additional_headers=headers)


def _default_connector() -> _Connector:
    try:
        from websockets.sync.client import connect
    except ImportError as exc:  # pragma: no cover - exercised through CLI dependency test.
        raise RuntimeError(
            "websockets is required for qq live-run; install isotope with runtime "
            "dependencies or run `.venv/bin/python -m pip install websockets>=15.0`"
        ) from exc
    return connect


def _positive_timeout(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive number")
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive number")
    return parsed


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


def _is_api_response(frame: dict[str, Any]) -> bool:
    return "echo" in frame and ("status" in frame or "retcode" in frame)


def _normalize_api_response(
    *,
    action: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    status = str(response.get("status", ""))
    retcode = response.get("retcode", 0 if status == "ok" else None)
    if status != "ok" or retcode not in (0, "0", None):
        raise RuntimeError(f"{action} failed: {json.dumps(response, ensure_ascii=False)}")
    data = response.get("data", {})
    if not isinstance(data, dict):
        data = {}
    message_id = data.get("message_id")
    if message_id is None:
        raise RuntimeError(f"{action} response missing message_id")
    return {
        "status": "ok",
        "message_id": str(message_id),
    }
