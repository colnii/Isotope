"""Artifact route handlers for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from .types import HttpResponse


class HttpArtifactRouteMixin:
    """Handle artifact summary and content route guards."""

    def _dispatch_artifact_route(
        self,
        method: str,
        parts: list[str],
        json_body: dict[str, Any] | None,
    ) -> HttpResponse | None:
        del json_body
        if method == "GET" and len(parts) == 3 and parts[0] == "artifacts" and parts[2] == "summary":
            summary = self._find_artifact_summary(parts[1])
            if summary is None:
                return self._error(404, "not_found", "artifact not found")
            return self._json(200, summary)
        return None

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
