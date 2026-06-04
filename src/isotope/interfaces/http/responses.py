"""Response, error, and idempotency helpers for the HTTP facade."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ...platform.errors import IsotopeError
from .types import HttpResponse


class HttpResponseMixin:
    """Build response bodies and manage idempotency replay."""

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
        if code == "unavailable":
            details.setdefault("category", "unavailable")
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

    def _isotope_error_response(self, error: IsotopeError) -> HttpResponse:
        status_code = error.http_status or 400
        status = self._status_for_isotope_error(error, status_code)
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

    def _status_for_isotope_error(self, error: IsotopeError, status_code: int) -> str:
        if error.category in {"conflict", "unavailable"}:
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
