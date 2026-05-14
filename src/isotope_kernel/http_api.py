"""In-process HTTP API boundary for the v0.2 minimal surface.

This module is a test-client style facade. It does not open sockets and does
not commit the project to a web framework.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .errors import KernelError
from .server import InProcessServer


@dataclass(frozen=True)
class HttpResponse:
    """Small response shape for in-process API tests."""

    status_code: int
    body: dict[str, Any] | list[dict[str, Any]]

    def json(self) -> dict[str, Any] | list[dict[str, Any]]:
        return self.body


class HttpApiApp:
    """Minimal in-process HTTP-like app for the kernel runtime boundary."""

    _ROUTES: tuple[tuple[str, str], ...] = (
        ("GET", "/health"),
        ("POST", "/sessions"),
        ("POST", "/sessions/{session_id}/runs"),
        ("POST", "/runs/{run_id}/input"),
        ("POST", "/runs/{run_id}/agent-loop-step"),
        ("GET", "/runs/{run_id}"),
        ("GET", "/runs/{run_id}/agent-loop-control"),
        ("GET", "/runs/{run_id}/agent-loop-tick-policy"),
        ("GET", "/runs/{run_id}/events"),
        ("GET", "/artifacts/{artifact_id}/summary"),
    )
    _CODEX_TASK_ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/runs/{run_id}/codex-tasks"),
    )
    _LLM_PROVIDER_ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/tool-calls"),
        ("POST", "/runs/{run_id}/llm/tool-result-followups"),
    )
    _LLM_PRODUCT_CHAT_ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/chat-turns"),
    )
    _DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/memory/query", "memory_query"),
        ("POST", "/external-ingestion", "external_ingestion"),
        ("GET", "/runs/{run_id}/events/stream", "sse_stream"),
        ("POST", "/runs/{run_id}/approvals", "approval_api"),
        ("GET", "/artifacts/{artifact_id}/content", "artifact_content"),
    )
    _CODEX_TASK_DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/codex-tasks", "codex_task"),
    )
    _LLM_PROVIDER_DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/tool-calls", "llm_provider_tool_call"),
        (
            "POST",
            "/runs/{run_id}/llm/tool-result-followups",
            "llm_provider_tool_result_followup",
        ),
    )
    _LLM_PRODUCT_CHAT_DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/chat-turns", "llm_product_chat_route"),
    )

    def __init__(
        self,
        root_path: Path | str,
        *,
        allow_artifact_content: bool = False,
        artifact_content_retrieval_service: Any | None = None,
        server: InProcessServer | None = None,
        enable_codex_task_route: bool = False,
        enable_llm_provider_route: bool = False,
        enable_llm_product_chat_route: bool = False,
        llm_tool_call_provider: Any | None = None,
        llm_tool_names: tuple[str, ...] = ("codex_task",),
    ):
        self.root_path = Path(root_path)
        self.server = server if server is not None else InProcessServer(self.root_path)
        self.allow_artifact_content = allow_artifact_content
        self.artifact_content_retrieval_service = artifact_content_retrieval_service
        self.enable_codex_task_route = enable_codex_task_route
        self.enable_llm_provider_route = enable_llm_provider_route
        self.enable_llm_product_chat_route = enable_llm_product_chat_route
        self.llm_tool_call_provider = llm_tool_call_provider
        self.llm_tool_names = self._validate_llm_tool_names(llm_tool_names)
        self._idempotency_cache: dict[str, dict[str, Any]] = {}

    def routes(self) -> list[tuple[str, str]]:
        return list(self._active_routes())

    def list_routes(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "routes": [
                {
                    "method": method,
                    "path": route,
                    "status": "supported",
                }
                for method, route in self._active_routes()
            ],
        }

    def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> HttpResponse:
        method = method.upper()
        try:
            idempotency_key = self._extract_idempotency_key(json)
        except ValueError as exc:
            return self._error(400, "bad_request", str(exc))

        body_fingerprint = self._body_fingerprint(json) if idempotency_key is not None else None
        if idempotency_key is not None:
            replay_or_conflict = self._idempotency_replay_or_conflict(
                idempotency_key,
                method,
                path,
                body_fingerprint,
            )
            if replay_or_conflict is not None:
                return replay_or_conflict

        response = self._dispatch_request(method, path, json)
        if idempotency_key is not None and 200 <= response.status_code < 300:
            self._idempotency_cache[idempotency_key] = {
                "method": method,
                "path": path,
                "body_fingerprint": body_fingerprint,
                "response": self._copy_response(response),
            }
        return response

    def _dispatch_request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
    ) -> HttpResponse:
        parts = self._split_path(path)
        allowed_methods = self._allowed_methods(parts) if parts else set()

        if parts and allowed_methods and method not in allowed_methods:
            return self._error(
                405,
                "method_not_allowed",
                "method not allowed",
                allowed_methods=sorted(allowed_methods),
            )

        if method == "GET" and self._route_matches("/artifacts/{artifact_id}/content", parts):
            return self._artifact_content_guard()

        deferred_capability = self._deferred_capability(method, parts)
        if deferred_capability is not None:
            return self._error(
                501,
                "not_enabled",
                f"{deferred_capability} is not enabled",
                capability=deferred_capability,
            )

        try:
            if method == "GET" and parts == ["routes"]:
                return self._json(200, self.list_routes())
            if method == "GET" and parts == ["health"]:
                return self._json(200, {"status": "ok"})
            if method == "POST" and parts == ["sessions"]:
                return self._json(201, self.server.create_session())
            if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "runs":
                body = self._require_body(json_body, required_fields=("goal",))
                if parts[1] not in self.server._sessions:
                    return self._kernel_error_response(
                        KernelError(
                            "session not found",
                            code="unknown_session",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"session_id": parts[1]},
                        )
                    )
                return self._json(
                    201,
                    self.server.create_run(parts[1], goal=body["goal"]),
                )
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "input":
                body = self._require_body(json_body, required_fields=("text",))
                if not self._run_exists(parts[1]):
                    return self._kernel_error_response(
                        KernelError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                requires_approval = False
                if isinstance(json_body, dict):
                    requires_approval = json_body.get("requires_approval", False)
                result = self.server.submit_input(
                    parts[1],
                    text=body["text"],
                    requires_approval=requires_approval,
                )
                return self._json(200, self._submit_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-step"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self.server.run_agent_loop_step(parts[1], json_body))
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "codex-tasks":
                if not self._run_exists(parts[1]):
                    return self._kernel_error_response(
                        KernelError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                body = self._require_body(json_body, required_fields=("prompt",))
                intent = {
                    "action": "delegate_agent_task",
                    "tool": "codex_task",
                    "prompt": body["prompt"],
                    "summary": self._optional_summary(json_body),
                }
                result = self.server.submit_action(
                    parts[1],
                    intent,
                    requires_approval=True,
                    complete_run=self._optional_complete_run(json_body),
                )
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._submit_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "llm"
                and parts[3] == "tool-calls"
            ):
                if not self._run_exists(parts[1]):
                    return self._kernel_error_response(
                        KernelError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                if self.llm_tool_call_provider is None:
                    return self._error(
                        501,
                        "not_enabled",
                        "llm_provider_tool_call is not enabled",
                        capability="llm_provider_tool_call",
                    )
                body = self._require_llm_provider_body(json_body)
                from .llm_provider import submit_llm_tool_call

                result = submit_llm_tool_call(
                    self,
                    parts[1],
                    self.llm_tool_call_provider,
                    body["messages"],
                    max_tokens=body["max_tokens"],
                    tool_names=self.llm_tool_names,
                    complete_run=body["complete_run"],
                )
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._llm_provider_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "llm"
                and parts[3] == "tool-result-followups"
            ):
                if not self._run_exists(parts[1]):
                    return self._kernel_error_response(
                        KernelError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                if self.llm_tool_call_provider is None:
                    return self._error(
                        501,
                        "not_enabled",
                        "llm_provider_tool_result_followup is not enabled",
                        capability="llm_provider_tool_result_followup",
                    )
                body = self._require_llm_tool_result_followup_body(json_body)
                from .llm_provider import submit_llm_tool_result_followup

                result = submit_llm_tool_result_followup(
                    self,
                    parts[1],
                    self.llm_tool_call_provider,
                    body["messages"],
                    body["llm_result"],
                    body["tool_execution_result"],
                    max_tokens=body["max_tokens"],
                    tool_names=self.llm_tool_names,
                    complete_run=body["complete_run"],
                )
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._llm_provider_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "llm"
                and parts[3] == "chat-turns"
            ):
                if not self._run_exists(parts[1]):
                    return self._kernel_error_response(
                        KernelError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                if self.llm_tool_call_provider is None:
                    return self._error(
                        501,
                        "not_enabled",
                        "llm_product_chat_route is not enabled",
                        capability="llm_product_chat_route",
                    )
                body = self._require_llm_product_chat_body(json_body)
                from .llm_provider import submit_llm_chat_turn

                result = submit_llm_chat_turn(
                    self,
                    parts[1],
                    self.llm_tool_call_provider,
                    body["messages"],
                    body.get("llm_result"),
                    body.get("tool_execution_result"),
                    max_tokens=body["max_tokens"],
                    tool_names=self.llm_tool_names,
                    complete_run=body["complete_run"],
                )
                result["turn_kind"] = body["turn_kind"]
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._llm_product_chat_result_to_dict(result))
            if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "approvals":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(
                    200,
                    {
                        "status": "ok",
                        "pending_approvals": self.server.get_pending_approvals(parts[1]),
                    },
                )
            if (
                method == "GET"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "approvals"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                try:
                    approval = self.server.get_approval(parts[1], parts[3])
                except ValueError as exc:
                    if "unknown approval" in str(exc):
                        return self._error(404, "not_found", "approval not found")
                    raise
                return self._json(200, {"status": "ok", "approval": approval})
            if (
                method == "POST"
                and len(parts) == 5
                and parts[0] == "runs"
                and parts[2] == "approvals"
                and parts[4] == "resolve"
            ):
                if not self._approval_known_for_run(parts[3], parts[1]):
                    return self._error(404, "not_found", "approval not found")
                result = self.server.resolve_approval(parts[3], json_body)
                if result.get("run_state") is not None and result["run_state"].run_id != parts[1]:
                    return self._error(404, "not_found", "approval not found")
                return self._json(200, self._submit_result_to_dict(result))
            if method == "GET" and len(parts) == 2 and parts[0] == "runs":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self._run_state_to_dict(self.server.get_run_state(parts[1])))
            if (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-control"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self.server.get_agent_loop_control(parts[1]))
            if (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-tick-policy"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                controls = self._agent_loop_tick_policy_controls(json_body)
                return self._json(200, self.server.get_agent_loop_tick_policy(parts[1], **controls))
            if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "events":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, [event.to_dict() for event in self.server.get_events(parts[1])])
            if method == "GET" and len(parts) == 3 and parts[0] == "artifacts" and parts[2] == "summary":
                summary = self._find_artifact_summary(parts[1])
                if summary is None:
                    return self._error(404, "not_found", "artifact not found")
                return self._json(200, summary)
        except PermissionError as exc:
            return self._error(403, "forbidden", str(exc))
        except KernelError as exc:
            return self._kernel_error_response(exc)
        except (FileNotFoundError, ValueError) as exc:
            message = str(exc)
            if "unknown approval" in message:
                return self._error(404, "not_found", "approval not found")
            if "already resolved" in message or "conflict" in message:
                return self._error(409, "approval_already_resolved", message)
            return self._error(400, "bad_request", str(exc))

        return self._error(404, "not_found", "route not found")

    def _artifact_content_guard(self) -> HttpResponse:
        if not self.allow_artifact_content:
            return self._content_not_enabled()
        if self.artifact_content_retrieval_service is None:
            return self._content_not_enabled()

        # The explicit enablement guard exists before opening the route. A later
        # slice must wire RetrievalService.get_artifact_content(...) and its
        # ResourceRef / grants / caller_context / purpose checks here.
        return self._content_not_enabled()

    def _content_not_enabled(self) -> HttpResponse:
        return self._error(
            501,
            "not_enabled",
            "artifact_content is not enabled",
            capability="artifact_content",
        )

    def _agent_loop_tick_policy_controls(self, json_body: dict[str, Any] | None) -> dict[str, Any]:
        if json_body is None:
            return {}
        if not isinstance(json_body, dict):
            raise ValueError("request body must be an object")
        allowed = {"tick_budget", "user_pause"}
        unknown = sorted(set(json_body) - allowed)
        if unknown:
            raise ValueError(f"unsupported agent loop tick policy fields: {', '.join(unknown)}")
        return {
            key: deepcopy(value)
            for key, value in json_body.items()
            if key in allowed
        }

    def _deferred_capability(self, method: str, parts: list[str]) -> str | None:
        for deferred_method, route, capability in self._deferred_routes():
            if method == deferred_method and self._route_matches(route, parts):
                return capability
        return None

    def _active_routes(self) -> tuple[tuple[str, str], ...]:
        routes = self._ROUTES
        if self.enable_codex_task_route:
            routes += self._CODEX_TASK_ROUTES
        if self.enable_llm_provider_route:
            routes += self._LLM_PROVIDER_ROUTES
        if self.enable_llm_product_chat_route:
            routes += self._LLM_PRODUCT_CHAT_ROUTES
        return routes

    def _deferred_routes(self) -> tuple[tuple[str, str, str], ...]:
        routes = self._DEFERRED_ROUTES
        if not self.enable_codex_task_route:
            routes += self._CODEX_TASK_DEFERRED_ROUTES
        if not self.enable_llm_provider_route:
            routes += self._LLM_PROVIDER_DEFERRED_ROUTES
        if not self.enable_llm_product_chat_route:
            routes += self._LLM_PRODUCT_CHAT_DEFERRED_ROUTES
        return routes

    def _find_artifact_summary(self, artifact_id: str) -> dict[str, Any] | None:
        runs_root = self.root_path / "runs"
        if not runs_root.exists():
            return None
        for event_path in sorted(runs_root.glob("*/events.jsonl")):
            run_id = event_path.parent.name
            for event in self.server.event_store.list_events(run_id):
                if event.event_type != "artifact.created":
                    continue
                artifact = event.payload.get("artifact")
                if not isinstance(artifact, dict):
                    continue
                ref = artifact.get("ref")
                if not isinstance(ref, dict) or ref.get("artifact_id") != artifact_id:
                    continue
                return {
                    "ref": dict(ref),
                    "artifact_type": artifact["artifact_type"],
                    "summary": artifact["summary"],
                    "provenance": dict(artifact["provenance"]),
                }
        return None

    def _submit_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": result["status"],
            "run_state": self._run_state_to_dict(result["run_state"]),
        }
        if result.get("proposal_id"):
            body["proposal_id"] = result["proposal_id"]
        if result.get("decision_id"):
            body["decision_id"] = result["decision_id"]
        if result.get("approval_id"):
            body["approval_id"] = result["approval_id"]
        artifact_ref = result.get("artifact_ref")
        if artifact_ref is not None:
            body["artifact_ref"] = artifact_ref.to_dict()
        if result.get("execution_id"):
            body["execution_id"] = result["execution_id"]
        if result.get("tool_execution_status"):
            body["tool_execution_status"] = result["tool_execution_status"]
        return body

    def _llm_provider_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        tool_result = result.get("tool_result")
        if not isinstance(tool_result, dict):
            tool_result = {}
        body: dict[str, Any] = {
            "status": result.get("status"),
            "provider_status": result.get("provider_status"),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "finish_reason": result.get("finish_reason"),
            "usage": self._safe_metadata_dict(result.get("usage")),
            "tool_name": result.get("tool_name"),
            "provider_tool_call_id": result.get("provider_tool_call_id"),
            "requires_approval": result.get("requires_approval"),
        }
        for key in (
            "previous_provider_tool_call_id",
            "tool_result_status",
            "tool_result_artifact_ref",
            "submission_status",
        ):
            if key in result:
                body[key] = deepcopy(result[key])
        for key in (
            "approval_id",
            "proposal_id",
            "decision_id",
            "execution_id",
            "tool_execution_status",
            "artifact_ref",
            "run_state",
        ):
            if key in tool_result:
                body[key] = deepcopy(tool_result[key])
        if "assistant_message" in result:
            body["assistant_message"] = deepcopy(result["assistant_message"])
        return body

    def _llm_product_chat_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        body = self._llm_provider_result_to_dict(result)
        body["turn_kind"] = result.get("turn_kind")
        return body

    def _run_state_to_dict(self, state: Any) -> dict[str, Any]:
        return asdict(state)

    def _json(
        self,
        status_code: int,
        body: dict[str, Any] | list[dict[str, Any]],
    ) -> HttpResponse:
        return HttpResponse(status_code=status_code, body=body)

    def _error(
        self,
        status_code: int,
        code: str,
        message: str,
        **details: Any,
    ) -> HttpResponse:
        nested_details = dict(details.pop("details", {}))
        if code == "not_enabled":
            details.setdefault("category", "not_enabled")
            details.setdefault("retryable", False)
            nested_details.update({key: value for key, value in details.items() if key == "capability"})
        error: dict[str, Any] = {
            "code": code,
            "message": message,
        }
        error.update(details)
        if nested_details:
            error["details"] = nested_details
        return self._json(
            status_code,
            {
                "status": code,
                "error": error,
            },
        )

    def _kernel_error_response(self, error: KernelError) -> HttpResponse:
        status_code = error.http_status or 400
        status = self._status_for_kernel_error(error, status_code)
        return self._json(
            status_code,
            {
                "status": status,
                "error": {
                    "code": error.code,
                    "message": str(error),
                    "category": error.category,
                    "retryable": error.retryable,
                    "details": dict(error.details),
                },
            },
        )

    def _status_for_kernel_error(self, error: KernelError, status_code: int) -> str:
        if error.category in {"conflict", "not_enabled"}:
            return error.category
        if status_code == 404:
            return "not_found"
        if status_code == 400:
            return "bad_request"
        return error.category

    def _extract_idempotency_key(self, body: Any) -> str | None:
        if not isinstance(body, dict) or "idempotency_key" not in body:
            return None
        key = body["idempotency_key"]
        if not isinstance(key, str) or not key:
            raise ValueError("idempotency_key must be a non-empty string")
        return key

    def _validate_llm_tool_names(self, tool_names: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(tool_names, tuple) or not tool_names:
            raise ValueError("llm_tool_names must be a non-empty tuple")
        cleaned: list[str] = []
        for index, tool_name in enumerate(tool_names):
            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError(f"llm_tool_names[{index}] must be a non-empty string")
            cleaned.append(tool_name)
        return tuple(cleaned)

    def _body_fingerprint(self, body: Any) -> str:
        return json.dumps(body, sort_keys=True, separators=(",", ":"), default=repr)

    def _idempotency_replay_or_conflict(
        self,
        key: str,
        method: str,
        path: str,
        body_fingerprint: str | None,
    ) -> HttpResponse | None:
        entry = self._idempotency_cache.get(key)
        if entry is None:
            return None
        if entry["method"] != method or entry["path"] != path:
            return self._error(
                409,
                "idempotency_conflict",
                "idempotency key was already used for a different method or path",
            )
        if entry["body_fingerprint"] != body_fingerprint:
            return self._error(
                409,
                "idempotency_conflict",
                "idempotency key was already used with a different request body",
            )
        return self._copy_response(entry["response"])

    def _copy_response(self, response: HttpResponse) -> HttpResponse:
        return HttpResponse(status_code=response.status_code, body=deepcopy(response.body))

    def _split_path(self, path: str) -> list[str]:
        if not isinstance(path, str) or not path.startswith("/"):
            return []
        return [part for part in path.split("/") if part]

    def _allowed_methods(self, parts: list[str]) -> set[str]:
        methods: set[str] = set()
        for method, route in self._active_routes():
            if self._route_matches(route, parts):
                methods.add(method)
        return methods

    def _route_matches(self, route: str, parts: list[str]) -> bool:
        route_parts = self._split_path(route)
        if len(route_parts) != len(parts):
            return False
        return all(
            expected == actual or (expected.startswith("{") and expected.endswith("}"))
            for expected, actual in zip(route_parts, parts, strict=True)
        )

    def _require_body(self, body: Any, required_fields: tuple[str, ...]) -> dict[str, str]:
        if not isinstance(body, dict):
            raise KernelError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        validated: dict[str, str] = {}
        for field in required_fields:
            value = body.get(field)
            if not isinstance(value, str) or not value:
                raise KernelError(
                    f"missing required request field: {field}",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": field},
                )
            validated[field] = value
        return validated

    def _require_llm_provider_body(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise KernelError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        messages = self._require_llm_messages(body.get("messages"))
        max_tokens = body.get("max_tokens", 512)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise KernelError(
                "max_tokens must be a positive integer",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "max_tokens"},
            )
        complete_run = self._optional_complete_run(body)
        return {"messages": messages, "max_tokens": max_tokens, "complete_run": complete_run}

    def _require_llm_tool_result_followup_body(self, body: Any) -> dict[str, Any]:
        provider_body = self._require_llm_provider_body(body)
        if not isinstance(body, dict):
            raise KernelError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        llm_result = self._require_object_field(body, "llm_result")
        tool_execution_result = self._require_object_field(body, "tool_execution_result")
        return {
            **provider_body,
            "llm_result": llm_result,
            "tool_execution_result": tool_execution_result,
        }

    def _require_llm_product_chat_body(self, body: Any) -> dict[str, Any]:
        provider_body = self._require_llm_provider_body(body)
        if not isinstance(body, dict):
            raise KernelError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        max_tool_steps = body.get("max_tool_steps", 1)
        if not isinstance(max_tool_steps, int) or max_tool_steps != 1:
            raise KernelError(
                "max_tool_steps must be exactly 1 for product chat route first slice",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "max_tool_steps"},
            )
        has_llm_result = "llm_result" in body
        has_tool_execution_result = "tool_execution_result" in body
        if has_llm_result != has_tool_execution_result:
            raise KernelError(
                "llm_result and tool_execution_result must be provided together",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "tool_result_context"},
            )
        if has_llm_result:
            return {
                **provider_body,
                "turn_kind": "tool_result_followup",
                "llm_result": self._require_object_field(body, "llm_result"),
                "tool_execution_result": self._require_object_field(body, "tool_execution_result"),
            }
        return {**provider_body, "turn_kind": "initial"}

    def _require_object_field(self, body: dict[str, Any], field: str) -> dict[str, Any]:
        value = body.get(field)
        if not isinstance(value, dict) or not value:
            raise KernelError(
                f"{field} must be a non-empty JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": field},
            )
        return deepcopy(value)

    def _require_llm_messages(self, messages: Any) -> list[dict[str, str]]:
        if not isinstance(messages, list) or not messages:
            raise KernelError(
                "messages must be a non-empty list",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "messages"},
            )
        validated: list[dict[str, str]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise KernelError(
                    "message must be a JSON object",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": f"messages[{index}]"},
                )
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant", "tool"}:
                raise KernelError(
                    "message role must be system, user, assistant, or tool",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": f"messages[{index}].role"},
                )
            if not isinstance(content, str) or not content.strip():
                raise KernelError(
                    "message content must be a non-empty string",
                    code="invalid_request",
                    category="validation",
                    retryable=False,
                    http_status=400,
                    details={"field": f"messages[{index}].content"},
                )
            validated.append({"role": role, "content": content})
        return validated

    def _optional_summary(self, body: Any) -> str:
        if not isinstance(body, dict):
            raise KernelError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        requires_approval = body.get("requires_approval", True)
        if requires_approval is not True:
            raise KernelError(
                "codex_task route always requires approval",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "requires_approval"},
            )
        summary = body.get("summary", "HTTP Codex task")
        if not isinstance(summary, str) or not summary:
            raise KernelError(
                "summary must be a non-empty string",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "summary"},
            )
        return summary

    def _optional_complete_run(self, body: Any) -> bool:
        if not isinstance(body, dict):
            raise KernelError(
                "request body must be a JSON object",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "body"},
            )
        complete_run = body.get("complete_run", True)
        if not isinstance(complete_run, bool):
            raise KernelError(
                "complete_run must be a boolean",
                code="invalid_request",
                category="validation",
                retryable=False,
                http_status=400,
                details={"field": "complete_run"},
            )
        return complete_run

    def _safe_metadata_dict(self, values: Any) -> dict[str, Any]:
        if not isinstance(values, dict):
            return {}
        return {
            key: value
            for key, value in values.items()
            if isinstance(key, str)
            and (isinstance(value, (str, int, float, bool)) or value is None)
        }

    def _run_exists(self, run_id: str) -> bool:
        return run_id in self.server._runs or self.server.event_store.event_path(run_id).exists()

    def _approval_known_for_run(self, approval_id: str, run_id: str) -> bool:
        pending = self.server._pending_approvals.get(approval_id)
        if pending is not None:
            return pending.get("run_id") == run_id
        resolved = self.server._resolved_approvals.get(approval_id)
        if resolved is None:
            return False
        state = resolved.get("run_state")
        return getattr(state, "run_id", None) == run_id


def create_http_app(
    root_path: Path | str,
    *,
    allow_artifact_content: bool = False,
    artifact_content_retrieval_service: Any | None = None,
) -> HttpApiApp:
    return HttpApiApp(
        root_path=root_path,
        allow_artifact_content=allow_artifact_content,
        artifact_content_retrieval_service=artifact_content_retrieval_service,
    )


def create_codex_cli_http_app(
    root_path: Path | str,
    *,
    config,
    checkpoint_store: Any | None = None,
    process_runner: Any | None = None,
    executable_resolver: Any | None = None,
) -> HttpApiApp:
    from .codex_server import create_codex_cli_server

    kwargs: dict[str, Any] = {}
    if process_runner is not None:
        kwargs["process_runner"] = process_runner
    if executable_resolver is not None:
        kwargs["executable_resolver"] = executable_resolver
    server = create_codex_cli_server(
        root_path,
        config=config,
        checkpoint_store=checkpoint_store,
        **kwargs,
    )
    return HttpApiApp(
        root_path=root_path,
        server=server,
        enable_codex_task_route=True,
    )


def create_llm_provider_http_app(
    root_path: Path | str,
    *,
    config,
    provider: Any,
    checkpoint_store: Any | None = None,
    process_runner: Any | None = None,
    executable_resolver: Any | None = None,
    tool_names: tuple[str, ...] = ("codex_task",),
) -> HttpApiApp:
    from .codex_server import create_codex_cli_server

    kwargs: dict[str, Any] = {}
    if process_runner is not None:
        kwargs["process_runner"] = process_runner
    if executable_resolver is not None:
        kwargs["executable_resolver"] = executable_resolver
    server = create_codex_cli_server(
        root_path,
        config=config,
        checkpoint_store=checkpoint_store,
        **kwargs,
    )
    return HttpApiApp(
        root_path=root_path,
        server=server,
        enable_codex_task_route=True,
        enable_llm_provider_route=True,
        llm_tool_call_provider=provider,
        llm_tool_names=tool_names,
    )


def create_llm_product_chat_http_app(
    root_path: Path | str,
    *,
    config,
    provider: Any,
    checkpoint_store: Any | None = None,
    process_runner: Any | None = None,
    executable_resolver: Any | None = None,
    tool_names: tuple[str, ...] = ("codex_task",),
) -> HttpApiApp:
    from .codex_server import create_codex_cli_server

    kwargs: dict[str, Any] = {}
    if process_runner is not None:
        kwargs["process_runner"] = process_runner
    if executable_resolver is not None:
        kwargs["executable_resolver"] = executable_resolver
    server = create_codex_cli_server(
        root_path,
        config=config,
        checkpoint_store=checkpoint_store,
        **kwargs,
    )
    return HttpApiApp(
        root_path=root_path,
        server=server,
        enable_codex_task_route=True,
        enable_llm_product_chat_route=True,
        llm_tool_call_provider=provider,
        llm_tool_names=tool_names,
    )
