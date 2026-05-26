"""Shared screen backend contracts and validation primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isotope.platform.schemas.refs import ResourceRef


SUPPORTED_SCREEN_PROTOCOL_VERSION = "screen-backend.v0.1"
SUPPORTED_BACKEND_MODES = {"external_local"}
ALLOWED_SCREEN_BACKEND_STATUSES = {
    "captured",
    "metadata_only",
    "planned",
    "completed",
    "failed",
    "not_observable",
    "ambiguous_target",
}
ALLOWED_CAPTURE_KINDS = {
    "screenshot",
    "metadata",
    "control_plan",
    "control_result",
    "diagnostic",
}
ALLOWED_SCREEN_ACTION_TYPES = {
    "move",
    "button_down",
    "button_up",
    "click",
    "wheel",
    "key_down",
    "key_up",
    "key_press",
}
SUPPORTED_SCREEN_MODES = {"manual", "assist", "auto", "non_intrusive", "interactive"}
SUPPORTED_EXECUTION_MODES = {"dry_run", "execute"}


class ScreenBackendProtocolError(RuntimeError):
    """Structured failure for screen backend protocol violations."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "screen_backend_protocol_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = reason_code
        self.structured_details = dict(details or {})


class ScreenBackendExecutionError(RuntimeError):
    """Structured failure reported by a screen backend run."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = reason_code
        self.structured_details = dict(details or {})


class ScreenBackendNotConfiguredError(RuntimeError):
    """Structured failure when a real screen backend is required but absent."""

    def __init__(
        self,
        message: str = "screen backend is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = "screen_backend_not_configured"
        self.structured_details = dict(details or {})


@dataclass(frozen=True)
class ScreenBackendConfig:
    backend_id: str
    backend_version: str
    protocol_version: str = SUPPORTED_SCREEN_PROTOCOL_VERSION
    mode: str = "external_local"
    configured: bool = True

    def __post_init__(self) -> None:
        _non_empty_string("backend_id", self.backend_id)
        _non_empty_string("backend_version", self.backend_version)
        _non_empty_string("protocol_version", self.protocol_version)
        _non_empty_string("mode", self.mode)
        if self.mode not in SUPPORTED_BACKEND_MODES:
            raise ValueError("screen backend mode is not supported")
        if not isinstance(self.configured, bool):
            raise ValueError("configured must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "protocol_version": self.protocol_version,
            "mode": self.mode,
            "configured": self.configured,
        }


@dataclass(frozen=True)
class ScreenTargetSelector:
    kind: str
    selector: dict[str, Any]

    def __post_init__(self) -> None:
        _non_empty_string("kind", self.kind)
        if self.kind != "window":
            raise ValueError("screen target kind is not supported")
        _dict_field("selector", self.selector)
        if not self.selector:
            raise ValueError("screen target selector must include at least one selector field")
        allowed = {"app", "title_contains", "window_id"}
        for key, value in self.selector.items():
            if key not in allowed:
                raise ValueError(f"screen target selector field is not supported: {key}")
            _non_empty_string(f"selector.{key}", value)


@dataclass(frozen=True)
class ScreenAction:
    type: str
    x: int | None = None
    y: int | None = None
    button: str | None = None
    key: str | None = None
    delta_x: int | None = None
    delta_y: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        _non_empty_string("type", self.type)
        if self.type not in ALLOWED_SCREEN_ACTION_TYPES:
            raise ValueError("screen action type is not supported")
        for field_name in ("x", "y", "delta_x", "delta_y", "duration_ms"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, int):
                raise ValueError(f"screen action {field_name} must be an int")
        if self.button is not None:
            _non_empty_string("button", self.button)
        if self.key is not None:
            _non_empty_string("key", self.key)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScreenAction":
        _dict_field("screen action", value)
        supported_fields = {
            "type",
            "x",
            "y",
            "button",
            "key",
            "delta_x",
            "delta_y",
            "duration_ms",
        }
        return cls(**{key: value[key] for key in supported_fields if key in value})

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.type}
        for field_name in ("x", "y", "button", "key", "delta_x", "delta_y", "duration_ms"):
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        return result


@dataclass(frozen=True)
class ScreenBackendRequest:
    run_id: str
    proposal_id: str
    decision_id: str
    execution_id: str
    tool_name: str
    operation: str
    policy_profile_id: str
    policy_version: str
    registry_id: str
    registry_version: str
    grants: dict[str, Any]
    workspace_binding: dict[str, Any]
    target_selector: ScreenTargetSelector
    mode: str
    capture: list[str]
    execution_mode: str | None
    actions: list[ScreenAction]
    budget: dict[str, Any]
    artifact_policy: dict[str, Any]
    basis_event_ids: list[str]
    backend_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "proposal_id",
            "decision_id",
            "execution_id",
            "tool_name",
            "operation",
            "policy_profile_id",
            "policy_version",
            "registry_id",
            "registry_version",
            "mode",
        ):
            _non_empty_string(field_name, getattr(self, field_name))
        if self.operation not in {"observe", "control"}:
            raise ValueError("screen operation is not supported")
        if self.mode not in SUPPORTED_SCREEN_MODES:
            raise ValueError("screen mode is not supported")
        _dict_field("grants", self.grants)
        _validate_workspace_binding(self.workspace_binding)
        if not isinstance(self.target_selector, ScreenTargetSelector):
            raise ValueError("target_selector must be a ScreenTargetSelector")
        _capture_list("capture", self.capture)
        if self.execution_mode is not None and self.execution_mode not in SUPPORTED_EXECUTION_MODES:
            raise ValueError("screen execution_mode is not supported")
        if not isinstance(self.actions, list):
            raise ValueError("actions must be a list")
        for index, action in enumerate(self.actions):
            if not isinstance(action, ScreenAction):
                raise ValueError(f"actions[{index}] must be a ScreenAction")
        _dict_field("budget", self.budget)
        _dict_field("artifact_policy", self.artifact_policy)
        _string_list("basis_event_ids", self.basis_event_ids)
        _dict_field("backend_config", self.backend_config)


@dataclass(frozen=True)
class ScreenBackendOutputArtifact:
    artifact_type: str
    summary: str
    content: str

    def __post_init__(self) -> None:
        _non_empty_string("artifact_type", self.artifact_type)
        _non_empty_string("summary", self.summary)
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")


@dataclass
class ScreenBackendResult:
    backend_session_id: str
    status: str
    started_at: str
    finished_at: str
    summary: str
    output_artifacts: list[ScreenBackendOutputArtifact | dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[ResourceRef | Any] = field(default_factory=list)
    reason_code: str = "screen_backend_completed"
    retryable: bool = False
    resource_usage: dict[str, Any] = field(default_factory=dict)
    reported_grants: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _non_empty_string("backend_session_id", self.backend_session_id)
        _non_empty_string("status", self.status)
        _non_empty_string("started_at", self.started_at)
        _non_empty_string("finished_at", self.finished_at)
        _non_empty_string("summary", self.summary)
        _non_empty_string("reason_code", self.reason_code)
        if not isinstance(self.output_artifacts, list):
            raise ValueError("output_artifacts must be a list")
        if not isinstance(self.artifact_refs, list):
            raise ValueError("artifact_refs must be a list")
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a bool")
        _dict_field("resource_usage", self.resource_usage)
        if self.reported_grants is not None:
            _dict_field("reported_grants", self.reported_grants)


@dataclass(frozen=True)
class ScreenBackendRunResult:
    backend_session_id: str
    status: str
    summary: str
    artifact_refs: list[ResourceRef]
    reason_code: str
    retryable: bool
    resource_usage: dict[str, Any]
    backend_summary: dict[str, Any] = field(default_factory=dict)


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _dict_field(field_name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return value


def _string_list(field_name: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name}[{index}] must be a non-empty string")


def _capture_list(field_name: str, value: Any) -> None:
    _string_list(field_name, value)
    for index, item in enumerate(value):
        if item not in ALLOWED_CAPTURE_KINDS:
            raise ValueError(f"{field_name}[{index}] is not a supported capture kind")


def _validate_workspace_binding(binding: dict[str, Any]) -> None:
    _dict_field("workspace_binding", binding)
    _non_empty_string("workspace_binding.workspace_id", binding.get("workspace_id"))
    _non_empty_string("workspace_binding.mode", binding.get("mode"))


def _reason_code(value: str) -> None:
    _non_empty_string("reason_code", value)
    if value != value.lower() or not value.replace("_", "").isalnum():
        raise ValueError("reason_code must be a stable identifier")
