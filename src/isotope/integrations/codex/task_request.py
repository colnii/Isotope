"""Codex task request construction and artifact policy helpers."""

from __future__ import annotations

import copy
from typing import Any

from ...platform.schemas.actions import ActionProposal, PolicyDecision
from .task_contract import (
    ALLOWED_CODEX_CAPTURE_KINDS,
    SUPPORTED_CODEX_TASK_PROTOCOL_VERSION,
    CodexTaskConfig,
    CodexTaskNotConfiguredError,
    CodexTaskProtocolError,
    CodexTaskRequest,
    _coerce_adapter_config,
    _dict_field,
    _non_empty_string,
)


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
