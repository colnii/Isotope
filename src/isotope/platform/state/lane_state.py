"""Supervisor lane state schema for low-sensitive read models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SupervisorLaneState:
    """State record for one managed Supervisor lane."""

    name: str
    tmux_session: str | None
    last_status: str
    last_prompted_at: str | None = None
    prompt_count: int = 0
    last_prompt_kind: str | None = None
    continue_count: int = 0
    last_failure_reason: str | None = None
    last_failure_exit_code: int | None = None
    last_failure_stderr_summary: str | None = None
    last_failure_record_id: str | None = None
    last_failed_at: str | None = None
    failure_count: int = 0
    decision_timeout_request_id: str | None = None
    decision_timeout_alerted_at: str | None = None
    decision_timeout_seconds: int | None = None
    worker_retry_count: int = 0

    def __post_init__(self) -> None:
        _required_text(self.name, "name")
        _required_text(self.last_status, "last_status")
        _optional_text(self.tmux_session, "tmux_session")
        _optional_text(self.last_prompted_at, "last_prompted_at")
        _non_negative_int(self.prompt_count, "prompt_count")
        _optional_text(self.last_prompt_kind, "last_prompt_kind")
        _non_negative_int(self.continue_count, "continue_count")
        _optional_text(self.last_failure_reason, "last_failure_reason")
        _optional_non_negative_int(
            self.last_failure_exit_code,
            "last_failure_exit_code",
        )
        _optional_text(
            self.last_failure_stderr_summary,
            "last_failure_stderr_summary",
        )
        _optional_text(self.last_failure_record_id, "last_failure_record_id")
        _optional_text(self.last_failed_at, "last_failed_at")
        _non_negative_int(self.failure_count, "failure_count")
        _optional_text(
            self.decision_timeout_request_id,
            "decision_timeout_request_id",
        )
        _optional_text(
            self.decision_timeout_alerted_at,
            "decision_timeout_alerted_at",
        )
        _optional_non_negative_int(
            self.decision_timeout_seconds,
            "decision_timeout_seconds",
        )
        _non_negative_int(self.worker_retry_count, "worker_retry_count")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SupervisorLaneState | None:
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                name=raw.get("name"),
                tmux_session=raw.get("tmux_session"),
                last_status=raw.get("last_status"),
                last_prompted_at=raw.get("last_prompted_at"),
                prompt_count=raw.get("prompt_count"),
                last_prompt_kind=raw.get("last_prompt_kind"),
                continue_count=raw.get("continue_count", 0),
                last_failure_reason=raw.get("last_failure_reason"),
                last_failure_exit_code=raw.get("last_failure_exit_code"),
                last_failure_stderr_summary=raw.get("last_failure_stderr_summary"),
                last_failure_record_id=raw.get("last_failure_record_id"),
                last_failed_at=raw.get("last_failed_at"),
                failure_count=raw.get("failure_count", 0),
                decision_timeout_request_id=raw.get("decision_timeout_request_id"),
                decision_timeout_alerted_at=raw.get("decision_timeout_alerted_at"),
                decision_timeout_seconds=raw.get("decision_timeout_seconds"),
                worker_retry_count=raw.get("worker_retry_count", 0),
            )
        except (TypeError, ValueError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tmux_session": self.tmux_session,
            "last_status": self.last_status,
            "last_prompted_at": self.last_prompted_at,
            "prompt_count": self.prompt_count,
            "last_prompt_kind": self.last_prompt_kind,
            "continue_count": self.continue_count,
            "last_failure_reason": self.last_failure_reason,
            "last_failure_exit_code": self.last_failure_exit_code,
            "last_failure_stderr_summary": self.last_failure_stderr_summary,
            "last_failure_record_id": self.last_failure_record_id,
            "last_failed_at": self.last_failed_at,
            "failure_count": self.failure_count,
            "decision_timeout_request_id": self.decision_timeout_request_id,
            "decision_timeout_alerted_at": self.decision_timeout_alerted_at,
            "decision_timeout_seconds": self.decision_timeout_seconds,
            "worker_retry_count": self.worker_retry_count,
        }

    def to_failed_lane_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "last_failure_reason": self.last_failure_reason,
            "last_failure_exit_code": self.last_failure_exit_code,
            "last_failure_stderr_summary": self.last_failure_stderr_summary,
            "last_failure_record_id": self.last_failure_record_id,
            "last_failed_at": self.last_failed_at,
            "failure_count": self.failure_count,
            "worker_retry_count": self.worker_retry_count,
        }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value is not None and (not isinstance(value, int) or value < 0):
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value
