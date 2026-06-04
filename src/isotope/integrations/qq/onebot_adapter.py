"""OneBot/NapCat adapter for platform-neutral social messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ...features.social import (
    SocialMessage,
    SocialMessagePart,
    SocialReplyAction,
    SocialReplyRef,
    SocialSendChunk,
    SocialSendFeedback,
    SocialSender,
)


@dataclass(frozen=True)
class OneBotConnectionState:
    connected: bool
    pending_events: int
    seen_message_count: int
    api_sequence: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "pending_events": self.pending_events,
            "seen_message_count": self.seen_message_count,
            "api_sequence": self.api_sequence,
        }


@dataclass
class OneBotAdapter:
    client: Any
    adapter_name: str = "onebot"
    _seen_message_ids: set[str] = field(default_factory=set)

    def normalize_event(self, event: dict[str, Any]) -> SocialMessage | None:
        if not isinstance(event, dict):
            raise ValueError("event must be a dict")
        message_id = _required_text(event.get("message_id"), "message_id")
        if message_id in self._seen_message_ids:
            return None
        self._seen_message_ids.add(message_id)
        message_type = _required_text(event.get("message_type"), "message_type")
        if message_type not in {"group", "private"}:
            raise ValueError("message_type must be group or private")
        group_id = _optional_text(event.get("group_id")) if message_type == "group" else None
        sender_id = _required_text(event.get("user_id"), "user_id")
        parts, mentions, reply_to = _parts_from_segments(event.get("message", ()))
        return SocialMessage(
            message_id=message_id,
            platform="qq",
            adapter=self.adapter_name,
            chat_type=message_type,
            group_id=group_id,
            sender=SocialSender(
                user_id=sender_id,
                display_name=_sender_name(event),
                roles=_sender_roles(event),
            ),
            timestamp=_timestamp(event.get("time")),
            text=_raw_text(parts, event),
            parts=parts,
            mentions=mentions,
            reply_to=reply_to,
            raw_event_ref=f"onebot://message/{message_id}",
        )

    def normalize_history(self, events: tuple[dict[str, Any], ...]) -> tuple[SocialMessage, ...]:
        if not isinstance(events, tuple):
            raise ValueError("events must be a tuple")
        messages: list[SocialMessage] = []
        for event in events:
            message = self.normalize_event(event)
            if message is not None:
                messages.append(message)
        return tuple(messages)

    def receive_next(self) -> SocialMessage | None:
        event = self.client.receive_event()
        if event is None:
            return None
        return self.normalize_event(event)

    def send_action(self, action: SocialReplyAction) -> SocialSendFeedback:
        if not isinstance(action, SocialReplyAction):
            raise ValueError("action must be a SocialReplyAction")
        segments = _segments_from_action(action)
        try:
            if action.target.chat_type == "group":
                result = self.client.send_group_msg(
                    group_id=action.target.group_id or "",
                    message=segments,
                )
            else:
                result = self.client.send_private_msg(
                    user_id=action.target.user_id or "",
                    message=segments,
                )
        except Exception as exc:  # pragma: no cover - fake tests assert returned feedback.
            return SocialSendFeedback(status="failed", platform_error=str(exc))
        message_id = _required_text(result.get("message_id"), "send message_id")
        return SocialSendFeedback(
            status="sent",
            sent_message_ids=(message_id,),
            chunks=(
                SocialSendChunk(
                    message_id=message_id,
                    parts=action.parts,
                    rendered_preview=_render_preview(action.parts),
                ),
            ),
            recent_messages_after_send=(
                {
                    "message_id": message_id,
                    "sender": "bot",
                    "preview": _render_preview(action.parts),
                },
            ),
        )

    def connection_state(self) -> OneBotConnectionState:
        client_state_fn = getattr(self.client, "connection_state", None)
        if callable(client_state_fn):
            client_state = client_state_fn()
            payload = (
                client_state.to_public_dict()
                if hasattr(client_state, "to_public_dict")
                else dict(client_state)
            )
            return OneBotConnectionState(
                connected=bool(payload.get("connected", False)),
                pending_events=int(payload.get("pending_events", 0)),
                seen_message_count=len(self._seen_message_ids),
                api_sequence=int(payload.get("api_sequence", 0)),
            )
        queued = getattr(self.client, "queued_events", ())
        return OneBotConnectionState(
            connected=bool(getattr(self.client, "connected", False)),
            pending_events=len(queued) if isinstance(queued, list) else 0,
            seen_message_count=len(self._seen_message_ids),
        )


def _parts_from_segments(
    value: object,
) -> tuple[tuple[SocialMessagePart, ...], tuple[str, ...], SocialReplyRef | None]:
    if not isinstance(value, list):
        raise ValueError("message segments must be a list")
    parts: list[SocialMessagePart] = []
    mentions: list[str] = []
    reply_to: SocialReplyRef | None = None
    for segment in value:
        if not isinstance(segment, dict):
            raise ValueError("message segment must be a dict")
        part = _part_from_segment(segment)
        parts.append(part)
        if part.kind == "mention" and part.user_id is not None:
            mentions.append(part.user_id)
        if part.kind == "reply" and reply_to is None:
            reply_to = SocialReplyRef(
                message_id=part.platform_data["reply_id"],
                sender_id="unknown",
            )
    if not parts:
        parts.append(SocialMessagePart(kind="raw", platform_data={"empty_message": True}))
    return tuple(parts), tuple(mentions), reply_to


def _part_from_segment(segment: dict[str, Any]) -> SocialMessagePart:
    kind = segment.get("type")
    data = segment.get("data", {})
    if not isinstance(data, dict):
        data = {}
    if kind == "text":
        return SocialMessagePart(kind="text", text=str(data.get("text", "")))
    if kind == "at":
        user_id = _required_text(data.get("qq"), "at.qq")
        return SocialMessagePart(kind="mention", text=f"@{user_id}", user_id=user_id)
    if kind == "face":
        face_id = _required_text(data.get("id"), "face.id")
        return SocialMessagePart(kind="qq_face", platform_data={"face_id": face_id})
    if kind == "image":
        media_ref = _media_ref(data)
        if data.get("sub_type") == "sticker":
            return SocialMessagePart(kind="sticker", media_ref=media_ref, platform_data=dict(data))
        return SocialMessagePart(kind="image", media_ref=media_ref, platform_data=dict(data))
    if kind == "reply":
        reply_id = _required_text(data.get("id"), "reply.id")
        return SocialMessagePart(kind="reply", platform_data={"reply_id": reply_id})
    if kind == "file":
        return SocialMessagePart(kind="file", media_ref=_media_ref(data), platform_data=dict(data))
    return SocialMessagePart(kind="raw", platform_data={"segment": dict(segment)})


def _segments_from_action(action: SocialReplyAction) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    if action.reply_to_message_id is not None:
        segments.append({"type": "reply", "data": {"id": action.reply_to_message_id}})
    for part in action.parts:
        if part.kind == "text":
            segments.append({"type": "text", "data": {"text": part.text}})
        elif part.kind == "mention":
            segments.append({"type": "at", "data": {"qq": part.user_id or part.text}})
        elif part.kind == "qq_face":
            face_id = str(part.platform_data.get("face_id", part.text))
            segments.append({"type": "face", "data": {"id": face_id}})
        elif part.kind == "sticker":
            segments.append(
                {
                    "type": "image",
                    "data": {"file": part.media_ref or "", "sub_type": "sticker"},
                }
            )
        elif part.kind == "image":
            segments.append({"type": "image", "data": {"file": part.media_ref or ""}})
        elif part.kind == "reply":
            reply_id = str(part.platform_data.get("reply_id", part.text))
            segments.append({"type": "reply", "data": {"id": reply_id}})
        elif part.kind == "file":
            segments.append({"type": "file", "data": {"file": part.media_ref or ""}})
        else:
            segments.append({"type": "text", "data": {"text": part.text or f"[{part.kind}]"}})
    return segments


def _sender_name(event: dict[str, Any]) -> str:
    sender = event.get("sender", {})
    if isinstance(sender, dict):
        name = sender.get("nickname") or sender.get("card")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return _required_text(event.get("user_id"), "user_id")


def _sender_roles(event: dict[str, Any]) -> tuple[str, ...]:
    sender = event.get("sender", {})
    if isinstance(sender, dict) and isinstance(sender.get("role"), str):
        return (sender["role"],)
    return ()


def _timestamp(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _raw_text(parts: tuple[SocialMessagePart, ...], event: dict[str, Any]) -> str:
    visible = "".join(part.text for part in parts if part.kind == "text").strip()
    if visible:
        return visible
    raw = event.get("raw_message")
    if isinstance(raw, str):
        return raw
    return ""


def _media_ref(data: dict[str, Any]) -> str:
    for key in ("url", "file", "path"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("media segment must include url, file, or path")


def _required_text(value: object, field_name: str) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value, "optional text")


def _render_preview(parts: tuple[SocialMessagePart, ...]) -> str:
    rendered: list[str] = []
    for part in parts:
        if part.kind == "text":
            rendered.append(part.text)
        elif part.media_ref:
            rendered.append(f"[{part.kind}: {part.media_ref}]")
        elif part.user_id:
            rendered.append(f"[{part.kind}: {part.user_id}]")
        else:
            rendered.append(f"[{part.kind}]")
    return "".join(rendered).strip()
