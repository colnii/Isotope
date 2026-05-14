"""Opt-in live smoke helper for the Codex CLI backend boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .workspace.artifacts import ArtifactStore
from .codex_cli import CodexCliBackend, CodexCliBackendConfig
from .codex_task import (
    SUPPORTED_CODEX_TASK_PROTOCOL_VERSION,
    CodexTaskAdapter,
    CodexTaskNotConfiguredError,
)
from .models import ActionProposal, PolicyDecision
from .refs import ResourceRef


DEFAULT_CODEX_LIVE_SMOKE_PROMPT = (
    "Reply exactly ISOTOPE_LIVE_CODEX_SMOKE_OK. "
    "Do not modify files."
)
DEFAULT_CODEX_LIVE_SMOKE_TIMEOUT_SECONDS = 45
DEFAULT_CODEX_LIVE_SMOKE_MAX_OUTPUT_BYTES = 65536
CODEX_LIVE_SMOKE_RUN_ID = "run_codex_live_smoke"


@dataclass(frozen=True)
class CodexLiveSmokeConfig:
    enabled: bool = False
    executable: str = "codex"
    workspace_root: str | None = None
    codex_home: str | None = None
    timeout_seconds: int = DEFAULT_CODEX_LIVE_SMOKE_TIMEOUT_SECONDS
    prompt: str = DEFAULT_CODEX_LIVE_SMOKE_PROMPT
    max_output_bytes: int = DEFAULT_CODEX_LIVE_SMOKE_MAX_OUTPUT_BYTES
    inherit_proxy_env: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a bool")
        _non_empty_string("executable", self.executable)
        if self.workspace_root is not None:
            _non_empty_string("workspace_root", self.workspace_root)
        if self.codex_home is not None:
            _non_empty_string("codex_home", self.codex_home)
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        _non_empty_string("prompt", self.prompt)
        if not isinstance(self.max_output_bytes, int) or self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be a positive integer")
        if not isinstance(self.inherit_proxy_env, bool):
            raise ValueError("inherit_proxy_env must be a bool")


def run_codex_live_smoke(
    root: Path | str,
    *,
    config: CodexLiveSmokeConfig | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Run a deliberate local Codex CLI smoke and return only a low-sensitive summary."""

    resolved_config = config or CodexLiveSmokeConfig()
    if not isinstance(resolved_config, CodexLiveSmokeConfig):
        raise TypeError("config must be a CodexLiveSmokeConfig")
    if not resolved_config.enabled:
        return {
            "status": "skipped",
            "reason_code": "codex_live_smoke_not_enabled",
            "artifact_count": 0,
            "artifact_refs": [],
        }

    smoke_root = Path(root)
    workspace_root = Path(resolved_config.workspace_root or smoke_root / "workspace")
    workspace_root.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore(smoke_root)
    proposal = _proposal(resolved_config)
    decision = _decision(proposal, resolved_config)

    try:
        effective_backend = backend or CodexCliBackend(
            CodexCliBackendConfig(
                executable=resolved_config.executable,
                workspace_root=str(workspace_root),
                codex_home=resolved_config.codex_home,
                max_output_bytes=resolved_config.max_output_bytes,
                skip_git_repo_check=True,
                inherit_proxy_env=resolved_config.inherit_proxy_env,
            )
        )
        result = CodexTaskAdapter(
            artifact_store=store,
            backend=effective_backend,
            adapter_config={
                "adapter_id": "codex_cli",
                "adapter_version": "live-smoke.v0.1",
                "protocol_version": SUPPORTED_CODEX_TASK_PROTOCOL_VERSION,
                "mode": "agent_cli_task",
            },
        ).prepare_and_run(
            proposal=proposal,
            decision=decision,
            execution_id="exec_codex_live_smoke",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_codex_live_smoke_approved"],
        )
    except CodexTaskNotConfiguredError as exc:
        return {
            "status": "not_configured",
            "reason_code": exc.error_reason_code,
            "artifact_count": 0,
            "artifact_refs": [],
        }

    return {
        "status": result.status,
        "reason_code": result.reason_code,
        "artifact_count": len(result.artifact_refs),
        "artifact_refs": [_ref_to_dict(ref) for ref in result.artifact_refs],
        "adapter_summary": dict(result.adapter_summary),
        "resource_usage": _safe_resource_usage(result.resource_usage),
    }


def diagnose_codex_live_smoke(
    root: Path | str,
    *,
    config: CodexLiveSmokeConfig | None = None,
    backend: Any | None = None,
) -> dict[str, Any]:
    """Run the smoke and add a low-sensitive diagnosis for common local failures."""

    smoke_root = Path(root)
    result = run_codex_live_smoke(smoke_root, config=config, backend=backend)
    diagnosed = dict(result)
    diagnosed["diagnosis"] = _diagnosis_for(smoke_root, result)
    return diagnosed


def _proposal(config: CodexLiveSmokeConfig) -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_codex_live_smoke",
        run_id=CODEX_LIVE_SMOKE_RUN_ID,
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="delegate_agent_task",
        payload={
            "tool": "codex_task",
            "prompt": config.prompt,
            "summary": "run opt-in Codex CLI live smoke",
        },
        requested_capabilities={
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": config.timeout_seconds},
        },
        registry_id="default",
        registry_version="v0.2",
    )


def _decision(proposal: ActionProposal, config: CodexLiveSmokeConfig) -> PolicyDecision:
    return PolicyDecision(
        decision_id="dec_codex_live_smoke",
        proposal_id=proposal.proposal_id,
        outcome="approved",
        grants={
            "tools": ["codex_task"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": config.timeout_seconds},
            "codex_task": {"adapter_required": True},
        },
        reason_codes=[],
        policy_profile_id="default",
        policy_version="v0.2",
    )


def _workspace_binding() -> dict[str, Any]:
    return {
        "workspace_id": "workspace_codex_live_smoke",
        "mode": "shared_ro",
        "lease_status": "active",
        "root_ref": "workspace://run_codex_live_smoke/shared_ro",
    }


def _diagnosis_for(root: Path, result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    artifact_captured = bool(result.get("artifact_count"))
    process_started = artifact_captured or status in {"completed", "failed", "timeout"}
    if status == "skipped":
        return _diagnosis(
            category="not_enabled",
            process_started=False,
            artifact_captured=False,
            summary="live smoke is disabled",
            next_step="enable the smoke explicitly when a real Codex check is intended",
        )
    if status == "not_configured":
        return _diagnosis(
            category="codex_cli_not_configured",
            process_started=False,
            artifact_captured=False,
            summary="local codex command is not available",
            next_step="install or configure the Codex CLI before running live smoke",
        )

    transcript_text = _transcript_text(root, result)
    lowered = transcript_text.lower()
    if status == "completed":
        return _diagnosis(
            category="ready",
            process_started=process_started,
            artifact_captured=artifact_captured,
            summary="local codex completed the smoke",
            next_step="keep this as a dev-only check until product route tests exist",
        )
    if _looks_like_auth_failure(lowered):
        return _diagnosis(
            category="auth_unavailable",
            process_started=process_started,
            artifact_captured=artifact_captured,
            summary="local codex started but auth was unavailable",
            next_step="check Codex login or auth state before product wiring",
        )
    if _looks_like_network_failure(lowered):
        return _diagnosis(
            category="network_unreachable",
            process_started=process_started,
            artifact_captured=artifact_captured,
            summary="local codex started but could not reach the service",
            next_step="check proxy or network settings before product wiring",
        )
    if "unexpected argument" in lowered:
        return _diagnosis(
            category="cli_argument_mismatch",
            process_started=process_started,
            artifact_captured=artifact_captured,
            summary="local codex rejected the generated CLI arguments",
            next_step="sync CodexCliBackend argv shape with the installed Codex CLI",
        )
    if "not inside a trusted directory" in lowered:
        return _diagnosis(
            category="workspace_not_trusted",
            process_started=process_started,
            artifact_captured=artifact_captured,
            summary="local codex rejected the temporary workspace",
            next_step="use the explicit temporary-workspace git check bypass only for smoke tests",
        )
    if status == "timeout":
        return _diagnosis(
            category="timeout",
            process_started=process_started,
            artifact_captured=artifact_captured,
            summary="local codex did not finish before the smoke timeout",
            next_step="inspect the transcript artifact and adjust network/auth before route wiring",
        )
    return _diagnosis(
        category="codex_cli_failed",
        process_started=process_started,
        artifact_captured=artifact_captured,
        summary="local codex failed with an unclassified result",
        next_step="inspect the transcript artifact before widening the integration",
    )


def _diagnosis(
    *,
    category: str,
    process_started: bool,
    artifact_captured: bool,
    summary: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "process_started": process_started,
        "artifact_captured": artifact_captured,
        "summary": summary,
        "next_step": next_step,
    }


def _transcript_text(root: Path, result: dict[str, Any]) -> str:
    refs = result.get("artifact_refs")
    if not isinstance(refs, list) or not refs:
        return ""
    first_ref = refs[0]
    if not isinstance(first_ref, dict):
        return ""
    try:
        content = ArtifactStore(root).get_content(ResourceRef(**first_ref))
    except Exception:
        return ""
    try:
        data = json.loads(content)
    except JSONDecodeError:
        return content
    if not isinstance(data, dict):
        return content
    parts = []
    for key in ("stdout", "stderr", "exit_code"):
        value = data.get(key)
        if value is not None:
            parts.append(str(value))
    return "\n".join(parts)


def _looks_like_auth_failure(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "401",
            "unauthorized",
            "login required",
            "not logged in",
            "authentication",
            "auth",
        )
    )


def _looks_like_network_failure(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "network unreachable",
            "failed to connect to websocket",
            "http/request failed",
            "error sending request",
            "stream disconnected before completion",
        )
    )


def _ref_to_dict(ref: ResourceRef) -> dict[str, str]:
    if not isinstance(ref, ResourceRef):
        raise TypeError("artifact ref must be a ResourceRef")
    return ref.to_dict()


def _safe_resource_usage(resource_usage: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "exit_code",
        "timeout_seconds",
        "duration_ms",
        "stdout_bytes",
        "stderr_bytes",
        "truncated",
    }
    return {
        key: value
        for key, value in resource_usage.items()
        if key in allowed_keys and isinstance(value, (bool, int, type(None)))
    }


def _non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


__all__ = [
    "CODEX_LIVE_SMOKE_RUN_ID",
    "DEFAULT_CODEX_LIVE_SMOKE_MAX_OUTPUT_BYTES",
    "DEFAULT_CODEX_LIVE_SMOKE_PROMPT",
    "DEFAULT_CODEX_LIVE_SMOKE_TIMEOUT_SECONDS",
    "CodexLiveSmokeConfig",
    "diagnose_codex_live_smoke",
    "run_codex_live_smoke",
]
