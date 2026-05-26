"""Terminal backend request construction and policy validation."""

from __future__ import annotations

import copy
from typing import Any

from isotope.platform.schemas.actions import ActionProposal, PolicyDecision

from .backend_types import (
    ALLOWED_CAPTURE_KINDS,
    SUPPORTED_BACKEND_PROTOCOL_VERSION,
    TerminalBackendConfig,
    TerminalBackendNotConfiguredError,
    TerminalBackendOutputArtifact,
    TerminalBackendProtocolError,
    TerminalBackendRequest,
    TerminalBackendResult,
    _dict_field,
    _non_empty_string,
)


def build_terminal_backend_request(
    *,
    proposal: ActionProposal,
    decision: PolicyDecision,
    execution_id: str,
    workspace_binding: dict[str, Any],
    basis_event_ids: list[str],
    approval_status: str = "approved",
    command_request: dict[str, Any] | None = None,
    artifact_policy: dict[str, Any] | None = None,
    backend_config: TerminalBackendConfig | dict[str, Any] | None = None,
) -> TerminalBackendRequest:
    if not isinstance(proposal, ActionProposal):
        raise TypeError("proposal must be an ActionProposal")
    if not isinstance(decision, PolicyDecision):
        raise TypeError("decision must be a PolicyDecision")
    if decision.proposal_id != proposal.proposal_id:
        raise ValueError("decision proposal_id must match proposal")
    if approval_status == "pending":
        raise PermissionError("pending approval must not call backend")
    if decision.outcome == "denied":
        raise PermissionError("denied decision must not call backend")
    if decision.outcome not in {"approved", "modified"}:
        raise PermissionError("unsupported decision outcome for terminal backend")

    grants_snapshot = copy.deepcopy(decision.grants)
    budget = copy.deepcopy(grants_snapshot.get("budget", {}))
    if not isinstance(budget, dict):
        raise ValueError("decision grants budget must be a dict")
    backend_config_payload = _coerce_backend_config(backend_config)
    _validate_backend_config_is_usable(backend_config_payload)
    artifact_policy_payload = _validate_artifact_policy(artifact_policy or _default_artifact_policy())
    resolved_command_request = copy.deepcopy(command_request or _command_request_from_proposal(proposal))
    _validate_backend_command_policy(resolved_command_request, backend_config_payload)

    return TerminalBackendRequest(
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
        command_request=resolved_command_request,
        budget=budget,
        artifact_policy=artifact_policy_payload,
        basis_event_ids=list(basis_event_ids),
        backend_config=copy.deepcopy(backend_config_payload),
    )


def default_terminal_backend_config() -> TerminalBackendConfig:
    return TerminalBackendConfig(
        backend_id="unspecified_backend",
        backend_version="unspecified",
        protocol_version=SUPPORTED_BACKEND_PROTOCOL_VERSION,
        mode="external_local",
    )


def _coerce_backend_config(value: TerminalBackendConfig | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return default_terminal_backend_config().to_dict()
    if isinstance(value, TerminalBackendConfig):
        return value.to_dict()
    if isinstance(value, dict):
        return TerminalBackendConfig(
            backend_id=value["backend_id"],
            backend_version=value["backend_version"],
            protocol_version=value.get("protocol_version", SUPPORTED_BACKEND_PROTOCOL_VERSION),
            mode=value.get("mode", "external_local"),
            configured=value.get("configured", True),
            allow_backend_native_task=value.get("allow_backend_native_task", False),
        ).to_dict()
    raise TypeError("terminal backend config must be structured")


def _validate_backend_config_is_usable(config: dict[str, Any]) -> None:
    if config.get("configured") is not True:
        raise TerminalBackendNotConfiguredError(details={"backend_id": config.get("backend_id")})
    protocol_version = config.get("protocol_version")
    if protocol_version != SUPPORTED_BACKEND_PROTOCOL_VERSION:
        raise TerminalBackendProtocolError(
            "terminal backend protocol version is not supported",
            details={
                "protocol_version": protocol_version,
                "supported_protocol_versions": [SUPPORTED_BACKEND_PROTOCOL_VERSION],
            },
        )


def _validate_backend_command_policy(
    command_request: dict[str, Any],
    backend_config: dict[str, Any],
) -> None:
    if command_request.get("kind") == "backend_native_task" and not backend_config.get("allow_backend_native_task"):
        raise TerminalBackendProtocolError(
            "backend_native_task requires an explicit terminal backend policy gate",
            reason_code="terminal_backend_request_denied",
            details={"backend_id": backend_config.get("backend_id")},
        )


def _command_request_from_proposal(proposal: ActionProposal) -> dict[str, Any]:
    argv = proposal.payload.get("argv")
    if isinstance(argv, list):
        return {"kind": "exec_argv", "argv": list(argv)}
    backend_task = proposal.payload.get("backend_native_task")
    if isinstance(backend_task, dict):
        return {"kind": "backend_native_task", "task": copy.deepcopy(backend_task)}
    raise ValueError("terminal backend command_request requires argv or backend_native_task")


def _default_artifact_policy() -> dict[str, Any]:
    return {
        "capture": ["stdout", "stderr", "transcript", "diff", "changed_files"],
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def _validate_artifact_policy(value: dict[str, Any]) -> dict[str, Any]:
    policy = _default_artifact_policy()
    policy.update(copy.deepcopy(_dict_field("artifact_policy", value)))
    capture = policy.get("capture")
    if not isinstance(capture, list) or not capture:
        raise TerminalBackendProtocolError(
            "terminal backend artifact policy capture must be a non-empty list",
            reason_code="terminal_backend_artifact_policy_denied",
        )
    for index, kind in enumerate(capture):
        if not isinstance(kind, str) or kind not in ALLOWED_CAPTURE_KINDS:
            raise TerminalBackendProtocolError(
                "terminal backend artifact policy capture kind is not supported",
                reason_code="terminal_backend_artifact_policy_denied",
                details={"index": index, "capture_kind": kind},
            )
    if policy.get("full_content_in_events") is not False:
        raise TerminalBackendProtocolError(
            "terminal backend full content in events is not allowed",
            reason_code="terminal_backend_artifact_policy_denied",
        )
    if policy.get("full_content_in_read_model") is not False:
        raise TerminalBackendProtocolError(
            "terminal backend full content in read model is not allowed",
            reason_code="terminal_backend_artifact_policy_denied",
        )
    return policy


def _validate_output_artifacts_match_policy(
    output_artifacts: list[TerminalBackendOutputArtifact],
    artifact_policy: dict[str, Any],
) -> None:
    allowed = set(artifact_policy.get("capture", []))
    for index, output in enumerate(output_artifacts):
        capture_kind = _capture_kind_from_artifact_type(output.artifact_type)
        if capture_kind not in allowed:
            raise TerminalBackendProtocolError(
                "terminal backend output artifact is not allowed by artifact policy",
                reason_code="terminal_backend_artifact_policy_denied",
                details={
                    "index": index,
                    "artifact_type": output.artifact_type,
                    "capture_kind": capture_kind,
                },
            )


def _capture_kind_from_artifact_type(artifact_type: str) -> str:
    if artifact_type.startswith("terminal_backend_"):
        return artifact_type.removeprefix("terminal_backend_")
    return artifact_type


def _low_sensitive_backend_summary(
    request: TerminalBackendRequest,
    result: TerminalBackendResult,
) -> dict[str, Any]:
    config = request.backend_config
    return {
        "backend_id": config["backend_id"],
        "backend_version": config["backend_version"],
        "protocol_version": config["protocol_version"],
        "mode": config["mode"],
        "status": result.status,
        "reason_code": result.reason_code,
    }


def _coerce_output_artifact(value: TerminalBackendOutputArtifact | dict[str, Any]) -> TerminalBackendOutputArtifact:
    if isinstance(value, TerminalBackendOutputArtifact):
        return value
    if isinstance(value, dict):
        try:
            return TerminalBackendOutputArtifact(
                artifact_type=value["artifact_type"],
                summary=value["summary"],
                content=value["content"],
            )
        except KeyError as exc:
            raise TerminalBackendProtocolError(
                "terminal backend output artifact missing required field",
                details={"field": str(exc)},
            ) from exc
    raise TerminalBackendProtocolError("terminal backend output artifact must be structured")


def _summary_contains_full_content(summary: str, content: str) -> bool:
    return bool(content) and len(content) >= 8 and content in summary
