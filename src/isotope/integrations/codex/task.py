"""Codex-as-tool adapter contract for future agent CLI task execution."""

from __future__ import annotations

from typing import Any

from ...platform.schemas.actions import ActionProposal, PolicyDecision
from ...platform.schemas.refs import ResourceRef
from .task_contract import (
    ALLOWED_CODEX_CAPTURE_KINDS,
    ALLOWED_CODEX_TASK_STATUSES,
    SUPPORTED_CODEX_TASK_PROTOCOL_VERSION,
    CodexTaskConfig,
    CodexTaskExecutionError,
    CodexTaskNotConfiguredError,
    CodexTaskOutputArtifact,
    CodexTaskProtocolError,
    CodexTaskRequest,
    CodexTaskResult,
    CodexTaskRunResult,
    _coerce_adapter_config,
    default_codex_task_config,
)
from .task_request import build_codex_task_request


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


def _summary_contains_full_content(summary: str, content: str) -> bool:
    return bool(content) and len(content) >= 8 and content in summary


__all__ = [
    "SUPPORTED_CODEX_TASK_PROTOCOL_VERSION",
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
