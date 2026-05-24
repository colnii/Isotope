"""Screen backend request construction and policy validation."""

from __future__ import annotations

import copy
from typing import Any

from isotope.platform.schemas.actions import ActionProposal, PolicyDecision

from .screen_backend_types import (
    ALLOWED_CAPTURE_KINDS,
    SUPPORTED_SCREEN_PROTOCOL_VERSION,
    ScreenAction,
    ScreenBackendConfig,
    ScreenBackendNotConfiguredError,
    ScreenBackendOutputArtifact,
    ScreenBackendProtocolError,
    ScreenBackendRequest,
    ScreenBackendResult,
    ScreenTargetSelector,
    _dict_field,
    _non_empty_string,
)


def build_screen_backend_request(
    *,
    proposal: ActionProposal,
    decision: PolicyDecision,
    execution_id: str,
    workspace_binding: dict[str, Any],
    basis_event_ids: list[str],
    approval_status: str = "approved",
    backend_config: ScreenBackendConfig | dict[str, Any] | None = None,
) -> ScreenBackendRequest:
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
        raise PermissionError("unsupported decision outcome for screen backend")

    grants_snapshot = copy.deepcopy(decision.grants)
    screen_grants = _screen_grant_from(grants_snapshot)
    budget = copy.deepcopy(grants_snapshot.get("budget", {}))
    if not isinstance(budget, dict):
        raise ValueError("decision grants budget must be a dict")

    backend_config_payload = _coerce_backend_config(backend_config)
    _validate_backend_config_is_usable(backend_config_payload)
    artifact_policy = _validate_artifact_policy(
        screen_grants.get("artifact_policy", _default_artifact_policy())
    )

    tool_name = proposal.payload.get("tool")
    if tool_name == "screen_observe":
        operation = "observe"
    elif tool_name == "screen_control":
        operation = "control"
    else:
        raise ValueError("screen backend request requires screen tool")

    target_selector = _target_selector_from_payload(proposal.payload.get("target_selector"))
    mode = _non_empty_string("mode", proposal.payload.get("mode", "non_intrusive"))
    capture = _capture_from_payload(proposal.payload.get("capture"), artifact_policy)
    execution_mode = proposal.payload.get("execution_mode")
    actions = _actions_from_payload(proposal.payload.get("actions", []))

    if operation == "observe":
        if screen_grants.get("observe") is not True:
            raise ScreenBackendProtocolError(
                "screen observe is not granted",
                reason_code="screen_grant_missing",
            )
        execution_mode = None
        actions = []
    else:
        if screen_grants.get("control") is not True:
            raise ScreenBackendProtocolError(
                "screen control is not granted",
                reason_code="screen_grant_missing",
            )
        _validate_action_policy(
            execution_mode=execution_mode,
            actions=actions,
            action_policy=screen_grants.get("action_policy", {}),
        )

    return ScreenBackendRequest(
        run_id=proposal.run_id,
        proposal_id=proposal.proposal_id,
        decision_id=decision.decision_id,
        execution_id=_non_empty_string("execution_id", execution_id),
        tool_name=tool_name,
        operation=operation,
        policy_profile_id=decision.policy_profile_id,
        policy_version=decision.policy_version,
        registry_id=proposal.registry_id,
        registry_version=proposal.registry_version,
        grants=grants_snapshot,
        workspace_binding=copy.deepcopy(workspace_binding),
        target_selector=target_selector,
        mode=mode,
        capture=capture,
        execution_mode=execution_mode if isinstance(execution_mode, str) else None,
        actions=actions,
        budget=budget,
        artifact_policy=artifact_policy,
        basis_event_ids=list(basis_event_ids),
        backend_config=copy.deepcopy(backend_config_payload),
    )


def default_screen_backend_config() -> ScreenBackendConfig:
    return ScreenBackendConfig(
        backend_id="unspecified_screen_backend",
        backend_version="unspecified",
        protocol_version=SUPPORTED_SCREEN_PROTOCOL_VERSION,
        mode="external_local",
    )


def _coerce_backend_config(value: ScreenBackendConfig | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return default_screen_backend_config().to_dict()
    if isinstance(value, ScreenBackendConfig):
        return value.to_dict()
    if isinstance(value, dict):
        return ScreenBackendConfig(
            backend_id=value["backend_id"],
            backend_version=value["backend_version"],
            protocol_version=value.get("protocol_version", SUPPORTED_SCREEN_PROTOCOL_VERSION),
            mode=value.get("mode", "external_local"),
            configured=value.get("configured", True),
        ).to_dict()
    raise TypeError("screen backend config must be structured")


def _validate_backend_config_is_usable(config: dict[str, Any]) -> None:
    if config.get("configured") is not True:
        raise ScreenBackendNotConfiguredError(details={"backend_id": config.get("backend_id")})
    protocol_version = config.get("protocol_version")
    if protocol_version != SUPPORTED_SCREEN_PROTOCOL_VERSION:
        raise ScreenBackendProtocolError(
            "screen backend protocol version is not supported",
            details={
                "protocol_version": protocol_version,
                "supported_protocol_versions": [SUPPORTED_SCREEN_PROTOCOL_VERSION],
            },
        )


def _screen_grant_from(grants: dict[str, Any]) -> dict[str, Any]:
    screen_grants = grants.get("screen")
    if not isinstance(screen_grants, dict):
        raise ScreenBackendProtocolError(
            "screen grant is required",
            reason_code="screen_grant_missing",
        )
    return screen_grants


def _target_selector_from_payload(value: Any) -> ScreenTargetSelector:
    _dict_field("target_selector", value)
    selector = value.get("selector")
    _dict_field("target_selector.selector", selector)
    return ScreenTargetSelector(
        kind=_non_empty_string("target_selector.kind", value.get("kind")),
        selector=copy.deepcopy(selector),
    )


def _capture_from_payload(value: Any, artifact_policy: dict[str, Any]) -> list[str]:
    capture = value if value is not None else ["metadata"]
    if not isinstance(capture, list) or not capture:
        raise ValueError("screen capture must be a non-empty list")
    normalized = []
    allowed = set(artifact_policy.get("capture", []))
    for index, item in enumerate(capture):
        if not isinstance(item, str) or item not in ALLOWED_CAPTURE_KINDS:
            raise ValueError(f"screen capture[{index}] is not supported")
        if item not in allowed:
            raise ScreenBackendProtocolError(
                "screen capture kind is not allowed by artifact policy",
                reason_code="screen_artifact_policy_denied",
                details={"capture_kind": item},
            )
        normalized.append(item)
    return normalized


def _actions_from_payload(value: Any) -> list[ScreenAction]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("screen actions must be a list")
    return [
        item if isinstance(item, ScreenAction) else ScreenAction.from_dict(item)
        for item in value
    ]


def _validate_action_policy(
    *,
    execution_mode: Any,
    actions: list[ScreenAction],
    action_policy: Any,
) -> None:
    _dict_field("screen.action_policy", action_policy)
    if not isinstance(execution_mode, str):
        raise ScreenBackendProtocolError(
            "screen execution mode is required",
            reason_code="screen_action_policy_denied",
        )
    execution_modes = action_policy.get("execution_modes", [])
    if not isinstance(execution_modes, list) or execution_mode not in execution_modes:
        raise ScreenBackendProtocolError(
            "screen execution mode is not allowed",
            reason_code="screen_action_policy_denied",
            details={"execution_mode": execution_mode},
        )
    max_actions = action_policy.get("max_actions", 0)
    if not isinstance(max_actions, int) or max_actions <= 0 or len(actions) > max_actions:
        raise ScreenBackendProtocolError(
            "screen action count is not allowed",
            reason_code="screen_action_policy_denied",
            details={"action_count": len(actions), "max_actions": max_actions},
        )
    allowed_action_types = action_policy.get("allowed_action_types", [])
    if not isinstance(allowed_action_types, list):
        raise ScreenBackendProtocolError(
            "screen allowed action types are malformed",
            reason_code="screen_action_policy_denied",
        )
    allowed_buttons = action_policy.get("allowed_buttons", [])
    if not isinstance(allowed_buttons, list):
        raise ScreenBackendProtocolError(
            "screen allowed buttons are malformed",
            reason_code="screen_action_policy_denied",
        )
    for index, action in enumerate(actions):
        if action.type not in allowed_action_types:
            raise ScreenBackendProtocolError(
                "screen action type is not allowed",
                reason_code="screen_action_policy_denied",
                details={"index": index, "action_type": action.type},
            )
        if action.button is not None and action.button not in allowed_buttons:
            raise ScreenBackendProtocolError(
                "screen button is not allowed",
                reason_code="screen_action_policy_denied",
                details={"index": index, "button": action.button},
            )


def _default_artifact_policy() -> dict[str, Any]:
    return {
        "capture": ["screenshot", "metadata", "control_plan", "control_result", "diagnostic"],
        "max_screenshot_bytes": 500000,
        "max_screenshot_width": 1600,
        "max_screenshot_height": 1200,
        "full_content_in_events": False,
        "full_content_in_read_model": False,
    }


def _validate_artifact_policy(value: dict[str, Any]) -> dict[str, Any]:
    policy = _default_artifact_policy()
    policy.update(copy.deepcopy(_dict_field("artifact_policy", value)))
    capture = policy.get("capture")
    if not isinstance(capture, list) or not capture:
        raise ScreenBackendProtocolError(
            "screen artifact policy capture must be a non-empty list",
            reason_code="screen_artifact_policy_denied",
        )
    for index, kind in enumerate(capture):
        if not isinstance(kind, str) or kind not in ALLOWED_CAPTURE_KINDS:
            raise ScreenBackendProtocolError(
                "screen artifact policy capture kind is not supported",
                reason_code="screen_artifact_policy_denied",
                details={"index": index, "capture_kind": kind},
            )
    if policy.get("full_content_in_events") is not False:
        raise ScreenBackendProtocolError(
            "screen backend full content in events is not allowed",
            reason_code="screen_artifact_policy_denied",
        )
    if policy.get("full_content_in_read_model") is not False:
        raise ScreenBackendProtocolError(
            "screen backend full content in read model is not allowed",
            reason_code="screen_artifact_policy_denied",
        )
    for field_name in ("max_screenshot_bytes", "max_screenshot_width", "max_screenshot_height"):
        value = policy.get(field_name)
        if not isinstance(value, int) or value <= 0:
            raise ScreenBackendProtocolError(
                "screen artifact policy screenshot caps must be positive integers",
                reason_code="screen_artifact_policy_denied",
                details={"field": field_name},
            )
    return policy


def _validate_output_artifacts_match_policy(
    output_artifacts: list[ScreenBackendOutputArtifact],
    artifact_policy: dict[str, Any],
) -> None:
    allowed = set(artifact_policy.get("capture", []))
    for index, output in enumerate(output_artifacts):
        capture_kind = _capture_kind_from_artifact_type(output.artifact_type)
        if capture_kind not in allowed:
            raise ScreenBackendProtocolError(
                "screen backend output artifact is not allowed by artifact policy",
                reason_code="screen_artifact_policy_denied",
                details={
                    "index": index,
                    "artifact_type": output.artifact_type,
                    "capture_kind": capture_kind,
                },
            )


def _capture_kind_from_artifact_type(artifact_type: str) -> str:
    if artifact_type.startswith("screen_"):
        return artifact_type.removeprefix("screen_")
    return artifact_type


def _low_sensitive_backend_summary(
    request: ScreenBackendRequest,
    result: ScreenBackendResult,
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


def _coerce_output_artifact(value: ScreenBackendOutputArtifact | dict[str, Any]) -> ScreenBackendOutputArtifact:
    if isinstance(value, ScreenBackendOutputArtifact):
        return value
    if isinstance(value, dict):
        try:
            return ScreenBackendOutputArtifact(
                artifact_type=value["artifact_type"],
                summary=value["summary"],
                content=value["content"],
            )
        except KeyError as exc:
            raise ScreenBackendProtocolError(
                "screen backend output artifact missing required field",
                details={"field": str(exc)},
            ) from exc
    raise ScreenBackendProtocolError("screen backend output artifact must be structured")


def _summary_contains_full_content(summary: str, content: str) -> bool:
    return bool(content) and len(content) >= 8 and content in summary
