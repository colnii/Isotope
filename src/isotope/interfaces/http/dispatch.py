"""Request dispatch for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from ...platform.errors import IsotopeError
from .artifact_routes import HttpArtifactRouteMixin
from .llm_routes import HttpLlmRouteMixin
from .product_routes import HttpProductRouteMixin
from .run_routes import HttpRunRouteMixin
from .types import HttpResponse


class HttpDispatchMixin(
    HttpArtifactRouteMixin,
    HttpLlmRouteMixin,
    HttpProductRouteMixin,
    HttpRunRouteMixin,
):
    """Dispatch supported HTTP-like requests to product flows and runtime calls."""

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

        try:
            if method == "POST" and parts == ["external-ingestion"]:
                body = json_body if isinstance(json_body, dict) else {}
                return self._json(200, self.server.ingest_external_input(body))
            for handler in (
                self._dispatch_product_route,
                self._dispatch_run_route,
                self._dispatch_llm_route,
                self._dispatch_artifact_route,
            ):
                response = handler(method, parts, json_body)
                if response is not None:
                    return response
        except PermissionError as exc:
            return self._error(403, "forbidden", str(exc))
        except IsotopeError as exc:
            return self._isotope_error_response(exc)
        except (FileNotFoundError, ValueError) as exc:
            message = str(exc)
            if "unknown approval" in message:
                return self._error(404, "not_found", "approval not found")
            if "already resolved" in message or "conflict" in message:
                return self._error(409, "approval_already_resolved", message)
            return self._error(400, "bad_request", str(exc))

        return self._error(404, "not_found", "route not found")
