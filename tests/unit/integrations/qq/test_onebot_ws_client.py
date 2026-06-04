from __future__ import annotations

import json
from typing import Any

import pytest

from isotope.integrations.qq.onebot_ws_client import OneBotWebSocketClient


class FakeWebSocket:
    def __init__(self, frames: list[dict[str, Any]]):
        self.frames = [json.dumps(frame, ensure_ascii=False) for frame in frames]
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self, *, timeout: float | None = None) -> str:
        if not self.frames:
            raise TimeoutError(f"no frame within {timeout}s")
        return self.frames.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeConnector:
    def __init__(self, websocket: FakeWebSocket):
        self.websocket = websocket
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        url: str,
        *,
        additional_headers: dict[str, str] | None = None,
    ) -> FakeWebSocket:
        self.calls.append(
            {
                "url": url,
                "additional_headers": dict(additional_headers or {}),
            }
        )
        return self.websocket


def _group_event(message_id: int = 123) -> dict[str, Any]:
    return {
        "post_type": "message",
        "message_id": message_id,
        "message_type": "group",
        "group_id": 99999,
        "user_id": 10001,
        "sender": {"nickname": "小林", "role": "member"},
        "time": 1780560000,
        "message": [{"type": "text", "data": {"text": "hello"}}],
    }


def test_onebot_websocket_client_receives_event_frame() -> None:
    websocket = FakeWebSocket([_group_event()])
    connector = FakeConnector(websocket)
    client = OneBotWebSocketClient(
        "ws://127.0.0.1:3001",
        connector=connector,
        access_token="secret",
    )

    event = client.receive_event()

    assert event == _group_event()
    assert connector.calls == [
        {
            "url": "ws://127.0.0.1:3001",
            "additional_headers": {"Authorization": "Bearer secret"},
        }
    ]
    assert client.connection_state().connected is True
    assert client.connection_state().pending_events == 0


def test_onebot_websocket_client_sends_group_msg_and_matches_echo() -> None:
    websocket = FakeWebSocket(
        [
            _group_event(124),
            {
                "status": "ok",
                "retcode": 0,
                "data": {"message_id": 5678},
                "echo": "isotope-onebot-1",
            },
        ]
    )
    client = OneBotWebSocketClient("ws://127.0.0.1:3001", connector=FakeConnector(websocket))

    result = client.send_group_msg(
        group_id="99999",
        message=[{"type": "text", "data": {"text": "收到"}}],
    )

    assert result == {"status": "ok", "message_id": "5678"}
    assert websocket.sent == [
        {
            "action": "send_group_msg",
            "params": {
                "group_id": "99999",
                "message": [{"type": "text", "data": {"text": "收到"}}],
            },
            "echo": "isotope-onebot-1",
        }
    ]
    assert client.connection_state().pending_events == 1
    assert client.receive_event() == _group_event(124)


def test_onebot_websocket_client_sends_private_msg() -> None:
    websocket = FakeWebSocket(
        [
            {
                "status": "ok",
                "retcode": 0,
                "data": {"message_id": "private-1"},
                "echo": "isotope-onebot-1",
            }
        ]
    )
    client = OneBotWebSocketClient("ws://127.0.0.1:3001", connector=FakeConnector(websocket))

    result = client.send_private_msg(
        user_id="10001",
        message=[{"type": "text", "data": {"text": "私聊收到"}}],
    )

    assert result == {"status": "ok", "message_id": "private-1"}
    assert websocket.sent[0]["action"] == "send_private_msg"
    assert websocket.sent[0]["params"]["user_id"] == "10001"
    assert client.connection_state().api_sequence == 1


def test_onebot_websocket_client_api_timeout_is_actionable() -> None:
    websocket = FakeWebSocket([])
    client = OneBotWebSocketClient(
        "ws://127.0.0.1:3001",
        connector=FakeConnector(websocket),
        request_timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError, match="send_group_msg response timed out"):
        client.send_group_msg(
            group_id="99999",
            message=[{"type": "text", "data": {"text": "收到"}}],
        )


def test_onebot_websocket_client_close_closes_connection() -> None:
    websocket = FakeWebSocket([_group_event()])
    client = OneBotWebSocketClient("ws://127.0.0.1:3001", connector=FakeConnector(websocket))

    assert client.receive_event() == _group_event()
    client.close()

    assert websocket.closed is True
    assert client.connection_state().connected is False
