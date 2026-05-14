"""Codex-as-tool adapter contract for future agent CLI task execution."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ...models import ActionProposal, PolicyDecision
from ...refs import ResourceRef


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


class CodexTaskAdapter:
    """Adapter boundary around a future Codex CLI task backend."""

    def __init__(
        self,
        *,
        artifact_store,
        backend,
        adapter_config: CodexTaskConfig | dict[str, Any] | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.backend = backend
        self.adapter_config = _coerce_adapter_config(adapter_config)

    def prepare_and_run(
        self,
        *,
        proposal: ActionProposal,
        decision: PolicyDecision,
        execution_id: str,
        workspace_binding: dict[str, Any],
        basis_event_ids: list[str],
        approval_status: str = "approved",
        task_request: dict[str, Any] | None = None,
        artifact_policy: dict[str, Any] | None = None,
    ) -> CodexTaskRunResult:
        request = build_codex_task_request(
            proposal=proposal,
            decision=decision,
            execution_id=execution_id,
            workspace_binding=workspace_binding,
            basis_event_ids=basis_event_ids,
            approval_status=approval_status,
            task_request=task_request,
            artifact_policy=artifact_policy,
            adapter_config=self.adapter_config,
        )
        result = self._normalize_result(self.backend.run(request))
        return self._accept_result(request, result)

    def _accept_result(
        self,
        request: CodexTaskRequest,
        result: CodexTaskResult,
    ) -> CodexTaskRunResult:
        if result.status not in ALLOWED_CODEX_TASK_STATUSES:
            raise CodexTaskProtocolError(
                "codex task adapter returned unknown status",
                details={"status": result.status},
            )
        if result.reported_grants is not None and result.reported_grants != request.grants:
            raise CodexTaskProtocolError(
                "codex task adapter cannot report widened grants",
                details={"adapter_session_id": result.adapter_session_id},
            )

        output_artifacts = [_coerce_output_artifact(item) for item in result.output_artifacts]
        for output in output_artifacts:
            if _summary_contains_full_content(result.summary, output.content):
                raise CodexTaskProtocolError(
                    "codex task summary exposes artifact content",
                    details={"adapter_session_id": result.adapter_session_id},
                )
        _validate_output_artifacts_match_policy(output_artifacts, request.artifact_policy)

        artifact_refs: list[ResourceRef] = []
        for index, ref in enumerate(result.artifact_refs):
            artifact_refs.append(self._validate_adapter_artifact_ref(ref, index=index))
        for output in output_artifacts:
            artifact = self.artifact_store.create_artifact(
                run_id=request.run_id,
                execution_id=request.execution_id,
                artifact_type=output.artifact_type,
                summary=output.summary,
                content=output.content,
                proposal_id=request.proposal_id,
                decision_id=request.decision_id,
            )
            artifact_refs.append(artifact.ref)

        return CodexTaskRunResult(
            adapter_session_id=result.adapter_session_id,
            status=result.status,
            summary=result.summary,
            artifact_refs=artifact_refs,
            reason_code=result.reason_code,
            retryable=result.retryable,
            resource_usage=dict(result.resource_usage),
            adapter_summary=_low_sensitive_adapter_summary(request, result),
        )

    def _normalize_result(self, raw_result: Any) -> CodexTaskResult:
        if isinstance(raw_result, CodexTaskResult):
            return raw_result
        if isinstance(raw_result, dict):
            try:
                return CodexTaskResult(
                    adapter_session_id=raw_result["adapter_session_id"],
                    status=raw_result["status"],
                    started_at=raw_result["started_at"],
                    finished_at=raw_result["finished_at"],
                    summary=raw_result["summary"],
                    output_artifacts=list(raw_result.get("output_artifacts", [])),
                    artifact_refs=list(raw_result.get("artifact_refs", [])),
                    reason_code=raw_result["reason_code"],
                    retryable=raw_result["retryable"],
                    resource_usage=dict(raw_result.get("resource_usage", {})),
                    reported_grants=raw_result.get("reported_grants"),
                )
            except KeyError as exc:
                raise CodexTaskProtocolError(
                    "codex task adapter result missing required field",
                    details={"field": str(exc)},
                ) from exc
        raise CodexTaskProtocolError("codex task adapter result must be structured")

    def _validate_adapter_artifact_ref(self, ref: Any, *, index: int) -> ResourceRef:
        if not isinstance(ref, ResourceRef):
            raise CodexTaskProtocolError(
                "codex task artifact_ref must be a structured ResourceRef",
                details={"index": index},
            )
        if ref.ref_type != "artifact":
            raise CodexTaskProtocolError(
                "codex task artifact_ref must be an artifact ResourceRef",
                details={"index": index},
            )
        try:
            self.artifact_store.get_metadata(ref)
        except Exception as exc:
            raise CodexTaskProtocolError(
                "codex task artifact_ref must already exist in artifact store",
                details={"index": index, "artifact_id": ref.artifact_id},
            ) from exc
        return ref


def build_codex_task_request(
    *,
    proposal: ActionProposal,
    decision: PolicyDecision,
    execution_id: str,
    workspace_binding: dict[str, Any],
    basis_event_ids: list[str],
    approval_status: str = "approved",
    task_request: dict[str, Any] | None = None,
    artifact_policy: dict[str, Any] | None = None,
    adapter_config: CodexTaskConfig | dict[str, Any] | None = None,
) -> CodexTaskRequest:
    if not isinstance(proposal, ActionProposal):
        raise TypeError("proposal must be an ActionProposal")
    if not isinstance(decision, PolicyDecision):
        raise TypeError("decision must be a PolicyDecision")
    if decision.proposal_id != proposal.proposal_id:
        raise ValueError("decision proposal_id must match proposal")
    if approval_status == "pending":
        raise PermissionError("pending approval must not call codex task adapter")
    if decision.outcome == "denied":
        raise PermissionError("denied decision must not call codex task adapter")
    if decision.outcome not in {"approved", "modified"}:
        raise PermissionError("unsupported decision outcome for codex task adapter")

    grants_snapshot = copy.deepcopy(decision.grants)
    budget = copy.deepcopy(grants_snapshot.get("budget", {}))
    if not isinstance(budget, dict):
        raise ValueError("decision grants budget must be a dict")
    adapter_config_payload = _coerce_adapter_config(adapter_config)
    _validate_adapter_config_is_usable(adapter_config_payload)
    artifact_policy_payload = _validate_artifact_policy(artifact_policy or _default_artifact_policy())
    resolved_task_request = copy.deepcopy(task_request or _task_request_from_proposal(proposal))

    return CodexTaskRequest(
        run_id=proposal.run_id,
        proposal_id=proposal.proposal_id,
        decision_id=decision.decision_id,
        execution_id=_non_empty_string("execution_id", execution_id),
        policy_profile_id=decision.policy_profile_id,
        policy_version=decision.policy_version,
        registry_id=proposal.registry_id,
        registry_version=proposal.registry_version,
        grants=grants_snapshot,
        workspace_binding=copy.deepcopy(workspace_binding),
        task_request=resolved_task_request,
        budget=budget,
        artifact_policy=artifact_policy_payload,
        basis_event_ids=list(basis_event_ids),
        adapter_config=copy.deepcopy(adapter_config_payload),
    )


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


def _validate_adapter_config_is_usable(config: dict[str, Any]) -> None:
    if config.get("configured") is not True:
        raise CodexTaskNotConfiguredError(details={"adapter_id": config.get("adapter_id")})
    protocol_version = config.get("protocol_version")
    if protocol_version != SUPPORTED_CODEX_TASK_PROTOCOL_VERSION:
        raise CodexTaskProtocolError(
            "codex task adapter protocol version is not supported",
            details={
                "protocol_version": protocol_version,
                "supported_protocol_versions": [SUPPORTED_CODEX_TASK_PROTOCOL_VERSION],
            },
        )


def _task_request_from_proposal(proposal: ActionProposal) -> dict[str, Any]:
    prompt = proposal.payload.get("prompt")
    if isinstance(prompt, str) and prompt:
        return {"kind": "codex_prompt", "prompt": prompt}
    raise ValueError("codex task request requires prompt")


def _default_artifact_policy() -> dict[str, Any]:
    return {
        "capture": ["transcript", "diff", "changed_files", "summary"],
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def _validate_artifact_policy(value: dict[str, Any]) -> dict[str, Any]:
    policy = _default_artifact_policy()
    policy.update(copy.deepcopy(_dict_field("artifact_policy", value)))
    capture = policy.get("capture")
    if not isinstance(capture, list) or not capture:
        raise CodexTaskProtocolError(
            "codex task artifact policy capture must be a non-empty list",
            reason_code="codex_task_artifact_policy_denied",
        )
    for index, kind in enumerate(capture):
        if not isinstance(kind, str) or kind not in ALLOWED_CODEX_CAPTURE_KINDS:
            raise CodexTaskProtocolError(
                "codex task artifact policy capture kind is not supported",
                reason_code="codex_task_artifact_policy_denied",
                details={"index": index, "capture_kind": kind},
            )
    if policy.get("full_content_in_events") is not False:
        raise CodexTaskProtocolError(
            "codex task full content in events is not allowed",
            reason_code="codex_task_artifact_policy_denied",
        )
    if policy.get("full_content_in_read_model") is not False:
        raise CodexTaskProtocolError(
            "codex task full content in read model is not allowed",
            reason_code="codex_task_artifact_policy_denied",
        )
    return policy


def _validate_output_artifacts_match_policy(
    output_artifacts: list[CodexTaskOutputArtifact],
    artifact_policy: dict[str, Any],
) -> None:
    allowed = set(artifact_policy.get("capture", []))
    for index, output in enumerate(output_artifacts):
        capture_kind = _capture_kind_from_artifact_type(output.artifact_type)
        if capture_kind not in allowed:
            raise CodexTaskProtocolError(
                "codex task output artifact is not allowed by artifact policy",
                reason_code="codex_task_artifact_policy_denied",
                details={
                    "index": index,
                    "artifact_type": output.artifact_type,
                    "capture_kind": capture_kind,
                },
            )


def _capture_kind_from_artifact_type(artifact_type: str) -> str:
    if artifact_type.startswith("codex_task_"):
        return artifact_type.removeprefix("codex_task_")
    return artifact_type


def _low_sensitive_adapter_summary(
    request: CodexTaskRequest,
    result: CodexTaskResult,
) -> dict[str, Any]:
    config = request.adapter_config
    return {
        "adapter_id": config["adapter_id"],
        "adapter_version": config["adapter_version"],
        "protocol_version": config["protocol_version"],
        "mode": config["mode"],
        "status": result.status,
        "reason_code": result.reason_code,
    }


def _coerce_output_artifact(value: CodexTaskOutputArtifact | dict[str, Any]) -> CodexTaskOutputArtifact:
    if isinstance(value, CodexTaskOutputArtifact):
        return value
    if isinstance(value, dict):
        try:
            return CodexTaskOutputArtifact(
                artifact_type=value["artifact_type"],
                summary=value["summary"],
                content=value["content"],
            )
        except KeyError as exc:
            raise CodexTaskProtocolError(
                "codex task output artifact missing required field",
                details={"field": str(exc)},
            ) from exc
    raise CodexTaskProtocolError("codex task output artifact must be structured")


def _validate_task_request(task_request: dict[str, Any]) -> None:
    _dict_field("task_request", task_request)
    if task_request.get("kind") != "codex_prompt":
        raise ValueError("task_request.kind must be codex_prompt")
    _non_empty_string("task_request.prompt", task_request.get("prompt"))


def _validate_workspace_binding(binding: dict[str, Any]) -> None:
    _dict_field("workspace_binding", binding)
    _non_empty_string("workspace_binding.workspace_id", binding.get("workspace_id"))
    _non_empty_string("workspace_binding.mode", binding.get("mode"))


def _summary_contains_full_content(summary: str, content: str) -> bool:
    return bool(content) and len(content) >= 8 and content in summary


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


__all__ = [
    "CodexTaskAdapter",
    "CodexTaskConfig",
    "CodexTaskExecutionError",
    "CodexTaskNotConfiguredError",
    "CodexTaskOutputArtifact",
    "CodexTaskProtocolError",
    "CodexTaskRequest",
    "CodexTaskResult",
    "CodexTaskRunResult",
    "build_codex_task_request",
    "default_codex_task_config",
]
