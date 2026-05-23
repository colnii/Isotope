"""Shared terminal backend contracts and validation primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isotope.platform.schemas.refs import ResourceRef


ALLOWED_BACKEND_STATUSES = {"completed", "failed", "cancelled", "timeout"}
ALLOWED_CAPTURE_KINDS = {"stdout", "stderr", "transcript", "diff", "changed_files"}
SUPPORTED_BACKEND_PROTOCOL_VERSION = "terminal-backend.v0.2"
SUPPORTED_BACKEND_MODES = {"external_local"}


class TerminalBackendProtocolError(RuntimeError):
    """Structured failure for terminal backend protocol violations."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "terminal_backend_protocol_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = reason_code
        self.structured_details = dict(details or {})


class TerminalBackendExecutionError(RuntimeError):
    """Structured failure reported by a terminal backend run."""

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


class TerminalBackendNotConfiguredError(RuntimeError):
    """Structured failure when a real terminal backend is required but absent."""

    def __init__(
        self,
        message: str = "terminal backend is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = "terminal_backend_not_configured"
        self.structured_details = dict(details or {})


@dataclass(frozen=True)
class TerminalBackendConfig:
    backend_id: str
    backend_version: str
    protocol_version: str = SUPPORTED_BACKEND_PROTOCOL_VERSION
    mode: str = "external_local"
    configured: bool = True
    allow_backend_native_task: bool = False

    def __post_init__(self) -> None:
        _non_empty_string("backend_id", self.backend_id)
        _non_empty_string("backend_version", self.backend_version)
        _non_empty_string("protocol_version", self.protocol_version)
        _non_empty_string("mode", self.mode)
        if self.mode not in SUPPORTED_BACKEND_MODES:
            raise ValueError("terminal backend mode is not supported")
        if not isinstance(self.configured, bool):
            raise ValueError("configured must be a bool")
        if not isinstance(self.allow_backend_native_task, bool):
            raise ValueError("allow_backend_native_task must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "protocol_version": self.protocol_version,
            "mode": self.mode,
            "configured": self.configured,
            "allow_backend_native_task": self.allow_backend_native_task,
        }


@dataclass(frozen=True)
class TerminalBackendRequest:
    run_id: str
    proposal_id: str
    decision_id: str
    execution_id: str
    policy_profile_id: str
    policy_version: str
    registry_id: str
    registry_version: str
    grants: dict[str, Any]
    workspace_binding: dict[str, Any]
    command_request: dict[str, Any]
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
            "policy_profile_id",
            "policy_version",
            "registry_id",
            "registry_version",
        ):
            _non_empty_string(field_name, getattr(self, field_name))
        _dict_field("grants", self.grants)
        _validate_workspace_binding(self.workspace_binding)
        _validate_command_request(self.command_request)
        _dict_field("budget", self.budget)
        _dict_field("artifact_policy", self.artifact_policy)
        _string_list("basis_event_ids", self.basis_event_ids)
        _dict_field("backend_config", self.backend_config)


@dataclass(frozen=True)
class TerminalBackendOutputArtifact:
    artifact_type: str
    summary: str
    content: str

    def __post_init__(self) -> None:
        _non_empty_string("artifact_type", self.artifact_type)
        _non_empty_string("summary", self.summary)
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")


@dataclass
class TerminalBackendResult:
    backend_session_id: str
    status: str
    started_at: str
    finished_at: str
    summary: str
    output_artifacts: list[TerminalBackendOutputArtifact | dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[ResourceRef | Any] = field(default_factory=list)
    exit_code: int | None = None
    reason_code: str = "terminal_backend_completed"
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
        if self.exit_code is not None and not isinstance(self.exit_code, int):
            raise ValueError("exit_code must be an int or None")
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a bool")
        _dict_field("resource_usage", self.resource_usage)
        if self.reported_grants is not None:
            _dict_field("reported_grants", self.reported_grants)


@dataclass(frozen=True)
class TerminalBackendRunResult:
    backend_session_id: str
    status: str
    summary: str
    artifact_refs: list[ResourceRef]
    exit_code: int | None
    reason_code: str
    retryable: bool
    resource_usage: dict[str, Any]
    backend_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminalBackendFailure:
    reason_code: str
    message: str
    retryable: bool
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _reason_code(self.reason_code)
        _non_empty_string("message", self.message)
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a bool")
        _dict_field("details", self.details)


@dataclass(frozen=True)
class TerminalBackendCancelResult:
    status: str
    summary: str
    reason_code: str
    retryable: bool
    basis_event_ids: list[str]



def _validate_command_request(command_request: dict[str, Any]) -> None:
    _dict_field("command_request", command_request)
    kind = command_request.get("kind")
    if kind == "exec_argv":
        argv = command_request.get("argv")
        if not isinstance(argv, list) or not argv:
            raise ValueError("command_request.argv must be a non-empty list")
        for index, item in enumerate(argv):
            if not isinstance(item, str) or not item:
                raise ValueError(f"command_request.argv[{index}] must be a non-empty string")
        return
    if kind == "backend_native_task":
        _dict_field("command_request.task", command_request.get("task"))
        return
    raise ValueError("command_request.kind must be exec_argv or backend_native_task")




def _validate_workspace_binding(binding: dict[str, Any]) -> None:
    _dict_field("workspace_binding", binding)
    _non_empty_string("workspace_binding.workspace_id", binding.get("workspace_id"))
    _non_empty_string("workspace_binding.mode", binding.get("mode"))



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


def _reason_code(value: str) -> None:
    _non_empty_string("reason_code", value)
    if value != value.lower() or not value.replace("_", "").isalnum():
        raise ValueError("reason_code must be a stable identifier")
