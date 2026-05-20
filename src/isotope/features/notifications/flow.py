"""Low-sensitive notification feature flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


FORBIDDEN_SOURCE_REF_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
    "text",
}


@dataclass(frozen=True)
class NotificationSummary:
    notification_id: str
    notification_type: str
    title: str
    unread: bool
    created_at: str
    read_at: str | None
    source_ref: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        source_ref = _copy_low_sensitive_ref(self.source_ref)
        return {
            "notification_id": self.notification_id,
            "type": self.notification_type,
            "title": self.title,
            "unread": self.unread,
            "created_at": self.created_at,
            "read_at": self.read_at,
            "source_ref": source_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotificationSummary":
        source_ref = data.get("source_ref")
        read_at = data.get("read_at")
        if read_at is not None and not isinstance(read_at, str):
            raise ValueError("notification summary requires read_at")
        if source_ref is not None and not isinstance(source_ref, dict):
            raise ValueError("notification summary requires source_ref")
        return cls(
            notification_id=_required_string(data, "notification_id"),
            notification_type=_required_string(data, "type"),
            title=_required_string(data, "title"),
            unread=_required_bool(data, "unread"),
            created_at=_required_string(data, "created_at"),
            read_at=read_at,
            source_ref=_copy_low_sensitive_ref(source_ref),
        )


class NotificationFlow:
    """Thin product flow for local notification summaries."""

    def __init__(
        self,
        root: Path | str,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ):
        self.root = Path(root)
        self._index_path = self.root / "notifications" / "index.json"
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: f"notif_{uuid4().hex}")
        self._notifications = self._load_index()

    @classmethod
    def in_process(cls, root: Path | str) -> "NotificationFlow":
        return cls(root)

    def create_notification(
        self,
        *,
        notification_type: str,
        title: str,
        source_ref: dict[str, Any] | None = None,
    ) -> NotificationSummary:
        self._reload_index()
        summary = NotificationSummary(
            notification_id=self._next_notification_id(),
            notification_type=_non_empty(notification_type, "notification_type"),
            title=_non_empty(title, "title"),
            unread=True,
            created_at=self._timestamp(),
            read_at=None,
            source_ref=_copy_low_sensitive_ref(source_ref),
        )
        self._notifications[summary.notification_id] = summary
        self._save_index()
        return _copy_summary(summary)

    def get_notification(self, notification_id: str) -> NotificationSummary:
        self._reload_index()
        try:
            return _copy_summary(self._notifications[notification_id])
        except KeyError as exc:
            raise ValueError(f"unknown notification_id: {notification_id}") from exc

    def list_notifications(
        self,
        *,
        unread: bool | None = None,
        notification_type: str | None = None,
    ) -> list[NotificationSummary]:
        self._reload_index()
        notifications = list(self._notifications.values())
        if unread is not None:
            notifications = [item for item in notifications if item.unread is unread]
        if notification_type is not None:
            notifications = [
                item for item in notifications if item.notification_type == notification_type
            ]
        return [_copy_summary(item) for item in notifications]

    def mark_read(self, notification_id: str) -> NotificationSummary:
        self._reload_index()
        current = self.get_notification(notification_id)
        if not current.unread:
            return current
        updated = NotificationSummary(
            notification_id=current.notification_id,
            notification_type=current.notification_type,
            title=current.title,
            unread=False,
            created_at=current.created_at,
            read_at=self._timestamp(),
            source_ref=_copy_low_sensitive_ref(current.source_ref),
        )
        self._notifications[updated.notification_id] = updated
        self._save_index()
        return _copy_summary(updated)

    def _next_notification_id(self) -> str:
        notification_id = self._id_factory()
        while notification_id in self._notifications:
            notification_id = self._id_factory()
        return notification_id

    def _timestamp(self) -> str:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return now.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _load_index(self) -> dict[str, NotificationSummary]:
        if not self._index_path.exists():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(f"malformed notification index: {self._index_path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("notifications"), list):
            raise ValueError(f"malformed notification index: {self._index_path}")
        notifications: dict[str, NotificationSummary] = {}
        for item in data["notifications"]:
            if not isinstance(item, dict):
                raise ValueError(f"malformed notification index: {self._index_path}")
            summary = NotificationSummary.from_dict(item)
            notifications[summary.notification_id] = summary
        return notifications

    def _reload_index(self) -> None:
        self._notifications = self._load_index()

    def _save_index(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "notifications": [
                notification.to_dict()
                for notification in self._notifications.values()
            ]
        }
        tmp_path = self._index_path.with_name(
            f".{self._index_path.name}.{uuid4().hex}.tmp"
        )
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self._index_path)


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"notification summary requires {field_name}")
    return value


def _required_bool(data: dict[str, Any], field_name: str) -> bool:
    value = data.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"notification summary requires {field_name}")
    return value


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"create notification requires {field_name}")
    return value


def _copy_low_sensitive_ref(source_ref: dict[str, Any] | None) -> dict[str, Any] | None:
    if source_ref is None:
        return None
    copied = _copy_low_sensitive_value(source_ref)
    if not isinstance(copied, dict):
        raise ValueError("source_ref must be a JSON object")
    return copied


def _validate_low_sensitive_ref(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_SOURCE_REF_KEYS.intersection(value)
        if forbidden:
            raise ValueError("source_ref must stay low-sensitive")
        for nested in value.values():
            _validate_low_sensitive_ref(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _validate_low_sensitive_ref(nested)


def _copy_low_sensitive_value(value: Any) -> Any:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_SOURCE_REF_KEYS.intersection(value)
        if forbidden:
            raise ValueError("source_ref must stay low-sensitive")
        copied: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("source_ref must be a JSON object")
            copied[key] = _copy_low_sensitive_value(nested)
        return copied
    if isinstance(value, list):
        return [_copy_low_sensitive_value(nested) for nested in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ValueError("source_ref must be JSON-compatible")


def _copy_summary(summary: NotificationSummary) -> NotificationSummary:
    return NotificationSummary.from_dict(summary.to_dict())
