"""Adapter that enforces Isotope boundaries around screen backends."""

from __future__ import annotations

from typing import Any

from isotope.platform.schemas.actions import ActionProposal, PolicyDecision
from isotope.platform.schemas.refs import ResourceRef

from .backend_policy import (
    _coerce_backend_config,
    _coerce_output_artifact,
    _low_sensitive_backend_summary,
    _summary_contains_full_content,
    _validate_output_artifacts_match_policy,
    build_screen_backend_request,
)
from .backend_types import (
    ALLOWED_SCREEN_BACKEND_STATUSES,
    ScreenBackendConfig,
    ScreenBackendProtocolError,
    ScreenBackendRequest,
    ScreenBackendResult,
    ScreenBackendRunResult,
)


class ScreenBackendAdapter:
    """Adapter that enforces Isotope's boundary around a screen backend."""

    def __init__(
        self,
        *,
        artifact_store,
        backend,
        backend_config: ScreenBackendConfig | dict[str, Any] | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.backend = backend
        self.backend_config = _coerce_backend_config(backend_config)

    def prepare_and_run(
        self,
        *,
        proposal: ActionProposal,
        decision: PolicyDecision,
        execution_id: str,
        workspace_binding: dict[str, Any],
        basis_event_ids: list[str],
        approval_status: str = "approved",
    ) -> ScreenBackendRunResult:
        request = build_screen_backend_request(
            proposal=proposal,
            decision=decision,
            execution_id=execution_id,
            workspace_binding=workspace_binding,
            basis_event_ids=basis_event_ids,
            approval_status=approval_status,
            backend_config=self.backend_config,
        )
        result = self._normalize_result(self.backend.run(request))
        return self._accept_result(request, result)

    def _accept_result(
        self,
        request: ScreenBackendRequest,
        result: ScreenBackendResult,
    ) -> ScreenBackendRunResult:
        if result.status not in ALLOWED_SCREEN_BACKEND_STATUSES:
            raise ScreenBackendProtocolError(
                "screen backend returned unknown status",
                details={"status": result.status},
            )
        if result.reported_grants is not None and result.reported_grants != request.grants:
            raise ScreenBackendProtocolError(
                "screen backend cannot report widened grants",
                details={"backend_session_id": result.backend_session_id},
            )

        output_artifacts = [_coerce_output_artifact(item) for item in result.output_artifacts]
        for output in output_artifacts:
            if _summary_contains_full_content(result.summary, output.content):
                raise ScreenBackendProtocolError(
                    "screen backend summary exposes artifact content",
                    details={"backend_session_id": result.backend_session_id},
                )
        _validate_output_artifacts_match_policy(output_artifacts, request.artifact_policy)

        artifact_refs: list[ResourceRef] = []
        for index, ref in enumerate(result.artifact_refs):
            artifact_refs.append(self._validate_backend_artifact_ref(ref, index=index))
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

        return ScreenBackendRunResult(
            backend_session_id=result.backend_session_id,
            status=result.status,
            summary=result.summary,
            artifact_refs=artifact_refs,
            reason_code=result.reason_code,
            retryable=result.retryable,
            resource_usage=dict(result.resource_usage),
            backend_summary=_low_sensitive_backend_summary(request, result),
        )

    def _normalize_result(self, raw_result: Any) -> ScreenBackendResult:
        if isinstance(raw_result, ScreenBackendResult):
            return raw_result
        if isinstance(raw_result, dict):
            try:
                return ScreenBackendResult(
                    backend_session_id=raw_result["backend_session_id"],
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
                raise ScreenBackendProtocolError(
                    "screen backend result missing required field",
                    details={"field": str(exc)},
                ) from exc
        raise ScreenBackendProtocolError("screen backend result must be structured")

    def _validate_backend_artifact_ref(self, ref: Any, *, index: int) -> ResourceRef:
        if not isinstance(ref, ResourceRef):
            raise ScreenBackendProtocolError(
                "screen backend artifact_ref must be a structured ResourceRef",
                details={"index": index},
            )
        if ref.ref_type != "artifact":
            raise ScreenBackendProtocolError(
                "screen backend artifact_ref must be an artifact ResourceRef",
                details={"index": index},
            )
        try:
            self.artifact_store.get_metadata(ref)
        except Exception as exc:
            raise ScreenBackendProtocolError(
                "screen backend artifact_ref must already exist in artifact store",
                details={"index": index, "artifact_id": ref.artifact_id},
            ) from exc
        return ref


__all__ = ["ScreenBackendAdapter"]
