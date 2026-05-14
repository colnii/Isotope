"""Terminal backend adapter and local runner for application agents."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.tools.terminal import cap_terminal_output, terminal_grant_from, validate_argv
from isotope_kernel.models import ActionProposal, PolicyDecision
from isotope_kernel.refs import ResourceRef


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


class TerminalBackendAdapter:
    """Adapter that enforces Isotope's boundary around a terminal backend."""

    def __init__(
        self,
        *,
        artifact_store,
        backend,
        backend_config: TerminalBackendConfig | dict[str, Any] | None = None,
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
        command_request: dict[str, Any] | None = None,
        artifact_policy: dict[str, Any] | None = None,
    ) -> TerminalBackendRunResult:
        request = build_terminal_backend_request(
            proposal=proposal,
            decision=decision,
            execution_id=execution_id,
            workspace_binding=workspace_binding,
            basis_event_ids=basis_event_ids,
            approval_status=approval_status,
            command_request=command_request,
            artifact_policy=artifact_policy,
            backend_config=self.backend_config,
        )
        result = self._normalize_result(self.backend.run(request))
        return self._accept_result(request, result)

    def _accept_result(
        self,
        request: TerminalBackendRequest,
        result: TerminalBackendResult,
    ) -> TerminalBackendRunResult:
        if result.status not in ALLOWED_BACKEND_STATUSES:
            raise TerminalBackendProtocolError(
                "terminal backend returned unknown status",
                details={"status": result.status},
            )
        if result.reported_grants is not None and result.reported_grants != request.grants:
            raise TerminalBackendProtocolError(
                "terminal backend cannot report widened grants",
                details={"backend_session_id": result.backend_session_id},
            )

        output_artifacts = [_coerce_output_artifact(item) for item in result.output_artifacts]
        for output in output_artifacts:
            if _summary_contains_full_content(result.summary, output.content):
                raise TerminalBackendProtocolError(
                    "terminal backend summary exposes artifact content",
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

        return TerminalBackendRunResult(
            backend_session_id=result.backend_session_id,
            status=result.status,
            summary=result.summary,
            artifact_refs=artifact_refs,
            exit_code=result.exit_code,
            reason_code=result.reason_code,
            retryable=result.retryable,
            resource_usage=dict(result.resource_usage),
            backend_summary=_low_sensitive_backend_summary(request, result),
        )

    def _normalize_result(self, raw_result: Any) -> TerminalBackendResult:
        if isinstance(raw_result, TerminalBackendResult):
            return raw_result
        if isinstance(raw_result, dict):
            try:
                return TerminalBackendResult(
                    backend_session_id=raw_result["backend_session_id"],
                    status=raw_result["status"],
                    started_at=raw_result["started_at"],
                    finished_at=raw_result["finished_at"],
                    summary=raw_result["summary"],
                    output_artifacts=list(raw_result.get("output_artifacts", [])),
                    artifact_refs=list(raw_result.get("artifact_refs", [])),
                    exit_code=raw_result.get("exit_code"),
                    reason_code=raw_result["reason_code"],
                    retryable=raw_result["retryable"],
                    resource_usage=dict(raw_result.get("resource_usage", {})),
                    reported_grants=raw_result.get("reported_grants"),
                )
            except KeyError as exc:
                raise TerminalBackendProtocolError(
                    "terminal backend result missing required field",
                    details={"field": str(exc)},
                ) from exc
        raise TerminalBackendProtocolError("terminal backend result must be structured")

    def _validate_backend_artifact_ref(self, ref: Any, *, index: int) -> ResourceRef:
        if not isinstance(ref, ResourceRef):
            raise TerminalBackendProtocolError(
                "terminal backend artifact_ref must be a structured ResourceRef",
                details={"index": index},
            )
        if ref.ref_type != "artifact":
            raise TerminalBackendProtocolError(
                "terminal backend artifact_ref must be an artifact ResourceRef",
                details={"index": index},
            )
        try:
            self.artifact_store.get_metadata(ref)
        except Exception as exc:
            raise TerminalBackendProtocolError(
                "terminal backend artifact_ref must already exist in artifact store",
                details={"index": index, "artifact_id": ref.artifact_id},
            ) from exc
        return ref


class LinuxSystemTerminalRunner:
    """Run approved argv requests on the local Linux system terminal."""

    def __init__(self, execution_root: Path):
        self.execution_root = Path(execution_root).resolve()

    def run(self, request: TerminalBackendRequest) -> TerminalBackendResult:
        if not isinstance(request, TerminalBackendRequest):
            raise TypeError("LinuxSystemTerminalRunner.run requires a TerminalBackendRequest")
        if request.command_request.get("kind") != "exec_argv":
            raise ValueError("linux system terminal runner only supports exec_argv")
        command = validate_argv(request.command_request.get("argv"))
        terminal_grant = terminal_grant_from(request.grants)
        _ensure_linux_system_terminal_grant(command, terminal_grant)
        timeout_seconds = _timeout_seconds(request.budget)
        max_output_bytes = _max_output_bytes(terminal_grant)

        cwd = self._prepare_cwd()
        started_at = _utc_now()
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                env=_sanitized_env(),
                text=True,
                capture_output=True,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, truncated = cap_terminal_output(
                _timeout_text(exc.stdout),
                _timeout_text(exc.stderr),
                max_output_bytes=max_output_bytes,
            )
            return _system_runner_result(
                request=request,
                command=command,
                cwd=cwd,
                status="timeout",
                reason_code="terminal_system_runner_timeout",
                stdout=stdout,
                stderr=stderr,
                truncated=truncated,
                max_output_bytes=max_output_bytes,
                exit_code=None,
                timed_out=True,
                timeout_seconds=timeout_seconds,
                retryable=True,
                started_at=started_at,
                finished_at=_utc_now(),
            )

        stdout, stderr, truncated = cap_terminal_output(
            completed.stdout,
            completed.stderr,
            max_output_bytes=max_output_bytes,
        )
        status = "completed" if completed.returncode == 0 else "failed"
        reason_code = (
            "terminal_system_runner_completed"
            if completed.returncode == 0
            else "terminal_system_runner_exit_nonzero"
        )
        return _system_runner_result(
            request=request,
            command=command,
            cwd=cwd,
            status=status,
            reason_code=reason_code,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            max_output_bytes=max_output_bytes,
            exit_code=completed.returncode,
            timed_out=False,
            timeout_seconds=timeout_seconds,
            retryable=False,
            started_at=started_at,
            finished_at=_utc_now(),
        )

    def _prepare_cwd(self) -> Path:
        self.execution_root.mkdir(parents=True, exist_ok=True)
        return self.execution_root


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


def _system_runner_result(
    *,
    request: TerminalBackendRequest,
    command: list[str],
    cwd: Path,
    status: str,
    reason_code: str,
    stdout: str,
    stderr: str,
    truncated: bool,
    max_output_bytes: int,
    exit_code: int | None,
    timed_out: bool,
    timeout_seconds: int,
    retryable: bool,
    started_at: str,
    finished_at: str,
) -> TerminalBackendResult:
    summary_status = "failed" if status == "timeout" else status
    return TerminalBackendResult(
        backend_session_id=f"linux_system_terminal_{request.execution_id}",
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=f"linux system terminal {summary_status}: {command[0]}",
        output_artifacts=[
            TerminalBackendOutputArtifact(
                artifact_type="terminal_backend_transcript",
                summary="linux system terminal transcript captured",
                content=json.dumps(
                    {
                        "argv": command,
                        "cwd": str(cwd),
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "truncated": truncated,
                        "max_output_bytes": max_output_bytes,
                        "shell": False,
                        "timed_out": timed_out,
                        "timeout_seconds": timeout_seconds,
                    },
                    sort_keys=True,
                ),
            )
        ],
        exit_code=exit_code,
        reason_code=reason_code,
        retryable=retryable,
        resource_usage={},
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


def _summary_contains_full_content(summary: str, content: str) -> bool:
    return bool(content) and len(content) >= 8 and content in summary


def _ensure_linux_system_terminal_grant(command: list[str], terminal_grant: dict[str, Any]) -> None:
    if terminal_grant.get("shell") is not False:
        raise ValueError("linux system terminal runner requires shell=False")
    if terminal_grant.get("argv_policy") != "allowlist":
        raise ValueError("linux system terminal runner requires argv allowlist policy")
    allowed = terminal_grant.get("allowed_commands", [])
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise ValueError("linux system terminal runner allowed_commands grant is malformed")
    if command[0] not in set(allowed):
        raise PermissionError("linux system terminal command is not allowed by grants")


def _timeout_seconds(budget: dict[str, Any]) -> int:
    value = budget.get("seconds")
    if not isinstance(value, int) or value < 0:
        raise ValueError("linux system terminal runner requires budget.seconds")
    return value


def _max_output_bytes(terminal_grant: dict[str, Any]) -> int:
    value = terminal_grant.get("max_output_bytes", 4096)
    if not isinstance(value, int) or value <= 0:
        raise ValueError("linux system terminal runner requires positive max_output_bytes")
    return value


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sanitized_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    "LinuxSystemTerminalRunner",
    "TerminalBackendAdapter",
    "TerminalBackendConfig",
    "TerminalBackendExecutionError",
    "TerminalBackendNotConfiguredError",
    "TerminalBackendOutputArtifact",
    "TerminalBackendProtocolError",
    "TerminalBackendRequest",
    "TerminalBackendResult",
    "TerminalBackendRunResult",
    "build_terminal_backend_request",
    "default_terminal_backend_config",
]
