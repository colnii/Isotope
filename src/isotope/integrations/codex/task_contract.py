"""Codex task adapter protocol data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...platform.schemas.refs import ResourceRef


ALLOWED_CODEX_TASK_STATUSES = {"completed", "failed", "cancelled", "timeout"}
ALLOWED_CODEX_CAPTURE_KINDS = {"transcript", "diff", "changed_files", "summary"}
SUPPORTED_CODEX_TASK_PROTOCOL_VERSION = "codex-task-adapter.v0.1"
SUPPORTED_CODEX_TASK_MODES = {"agent_cli_task"}


class CodexTaskProtocolError(RuntimeError):
    """Structured failure for Codex task adapter protocol violations."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "codex_task_protocol_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = reason_code
        self.structured_details = dict(details or {})


class CodexTaskExecutionError(RuntimeError):
    """Structured failure reported by a Codex task adapter run."""

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


class CodexTaskNotConfiguredError(RuntimeError):
    """Structured failure when a selected Codex task adapter is absent."""

    def __init__(
        self,
        message: str = "codex task adapter is not configured",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_reason_code = "codex_task_adapter_not_configured"
        self.structured_details = dict(details or {})


@dataclass(frozen=True)
class CodexTaskConfig:
    adapter_id: str
    adapter_version: str
    protocol_version: str = SUPPORTED_CODEX_TASK_PROTOCOL_VERSION
    mode: str = "agent_cli_task"
    configured: bool = True

    def __post_init__(self) -> None:
        _non_empty_string("adapter_id", self.adapter_id)
        _non_empty_string("adapter_version", self.adapter_version)
        _non_empty_string("protocol_version", self.protocol_version)
        _non_empty_string("mode", self.mode)
        if self.mode not in SUPPORTED_CODEX_TASK_MODES:
            raise ValueError("codex task adapter mode is not supported")
        if not isinstance(self.configured, bool):
            raise ValueError("configured must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "protocol_version": self.protocol_version,
            "mode": self.mode,
            "configured": self.configured,
        }


@dataclass(frozen=True)
class CodexTaskRequest:
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
    task_request: dict[str, Any]
    budget: dict[str, Any]
    artifact_policy: dict[str, Any]
    basis_event_ids: list[str]
    adapter_config: dict[str, Any] = field(default_factory=dict)

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
        _validate_task_request(self.task_request)
        _dict_field("budget", self.budget)
        _dict_field("artifact_policy", self.artifact_policy)
        _string_list("basis_event_ids", self.basis_event_ids)
        _dict_field("adapter_config", self.adapter_config)


@dataclass(frozen=True)
class CodexTaskOutputArtifact:
    artifact_type: str
    summary: str
    content: str

    def __post_init__(self) -> None:
        _non_empty_string("artifact_type", self.artifact_type)
        _non_empty_string("summary", self.summary)
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")


@dataclass
class CodexTaskResult:
    adapter_session_id: str
    status: str
    started_at: str
    finished_at: str
    summary: str
    output_artifacts: list[CodexTaskOutputArtifact | dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[ResourceRef | Any] = field(default_factory=list)
    reason_code: str = "codex_task_completed"
    retryable: bool = False
    resource_usage: dict[str, Any] = field(default_factory=dict)
    reported_grants: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _non_empty_string("adapter_session_id", self.adapter_session_id)
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
class CodexTaskRunResult:
    adapter_session_id: str
    status: str
    summary: str
    artifact_refs: list[ResourceRef]
    reason_code: str
    retryable: bool
    resource_usage: dict[str, Any]
    adapter_summary: dict[str, Any] = field(default_factory=dict)


def default_codex_task_config() -> CodexTaskConfig:
    return CodexTaskConfig(
        adapter_id="unspecified_codex_adapter",
        adapter_version="unspecified",
        protocol_version=SUPPORTED_CODEX_TASK_PROTOCOL_VERSION,
        mode="agent_cli_task",
    )


def _coerce_adapter_config(value: CodexTaskConfig | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return default_codex_task_config().to_dict()
    if isinstance(value, CodexTaskConfig):
        return value.to_dict()
    if isinstance(value, dict):
        return CodexTaskConfig(
            adapter_id=value["adapter_id"],
            adapter_version=value["adapter_version"],
            protocol_version=value.get("protocol_version", SUPPORTED_CODEX_TASK_PROTOCOL_VERSION),
            mode=value.get("mode", "agent_cli_task"),
            configured=value.get("configured", True),
        ).to_dict()
    raise TypeError("codex task adapter config must be structured")


def _validate_task_request(task_request: dict[str, Any]) -> None:
    _dict_field("task_request", task_request)
    if task_request.get("kind") != "codex_prompt":
        raise ValueError("task_request.kind must be codex_prompt")
    _non_empty_string("task_request.prompt", task_request.get("prompt"))


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
