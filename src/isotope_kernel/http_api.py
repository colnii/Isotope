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
        ("GET", "/runs/{run_id}"),
        ("GET", "/runs/{run_id}/events"),
        ("GET", "/artifacts/{artifact_id}/summary"),
    )
    _DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/memory/query", "memory_query"),
        ("POST", "/external-ingestion", "external_ingestion"),
        ("GET", "/runs/{run_id}/events/stream", "sse_stream"),
        ("POST", "/runs/{run_id}/approvals", "approval_api"),
        ("GET", "/artifacts/{artifact_id}/content", "artifact_content"),
    )

    def __init__(
        self,
        root_path: Path | str,
        *,
        allow_artifact_content: bool = False,
        artifact_content_retrieval_service: Any | None = None,
    ):
        self.root_path = Path(root_path)
        self.server = InProcessServer(self.root_path)
        self.allow_artifact_content = allow_artifact_content
        self.artifact_content_retrieval_service = artifact_content_retrieval_service
        self._idempotency_cache: dict[str, dict[str, Any]] = {}

    def routes(self) -> list[tuple[str, str]]:
        return list(self._ROUTES)

    def list_routes(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "routes": [
                {
                    "method": method,
                    "path": route,
                    "status": "supported",
                }
                for method, route in self._ROUTES
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
                    return self._error(404, "not_found", "session not found")
                return self._json(
                    201,
                    self.server.create_run(parts[1], goal=body["goal"]),
                )
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "input":
                body = self._require_body(json_body, required_fields=("text",))
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                result = self.server.submit_input(parts[1], text=body["text"])
                return self._json(200, self._submit_result_to_dict(result))
            if method == "GET" and len(parts) == 2 and parts[0] == "runs":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self._run_state_to_dict(self.server.get_run_state(parts[1])))
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
        except (FileNotFoundError, ValueError) as exc:
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

    def _deferred_capability(self, method: str, parts: list[str]) -> str | None:
        for deferred_method, route, capability in self._DEFERRED_ROUTES:
            if method == deferred_method and self._route_matches(route, parts):
                return capability
        return None

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
        artifact_ref = result.get("artifact_ref")
        if artifact_ref is not None:
            body["artifact_ref"] = artifact_ref.to_dict()
        if result.get("execution_id"):
            body["execution_id"] = result["execution_id"]
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
        error: dict[str, Any] = {
            "code": code,
            "message": message,
        }
        error.update(details)
        return self._json(
            status_code,
            {
                "status": code,
                "error": error,
            },
        )

    def _extract_idempotency_key(self, body: Any) -> str | None:
        if not isinstance(body, dict) or "idempotency_key" not in body:
            return None
        key = body["idempotency_key"]
        if not isinstance(key, str) or not key:
            raise ValueError("idempotency_key must be a non-empty string")
        return key

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
        for method, route in self._ROUTES:
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
            raise ValueError("request body must be a JSON object")
        validated: dict[str, str] = {}
        for field in required_fields:
            value = body.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be a non-empty string")
            validated[field] = value
        return validated

    def _run_exists(self, run_id: str) -> bool:
        return run_id in self.server._runs or self.server.event_store.event_path(run_id).exists()


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
