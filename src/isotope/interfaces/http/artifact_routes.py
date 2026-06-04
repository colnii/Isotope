"""Artifact route handlers for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from ...platform.schemas.refs import ResourceRef
from .types import HttpResponse


class HttpArtifactRouteMixin:
    """Handle artifact summary and content route guards."""

    def _dispatch_artifact_route(
        self,
        method: str,
        parts: list[str],
        json_body: dict[str, Any] | None,
    ) -> HttpResponse | None:
        if method == "GET" and len(parts) == 3 and parts[0] == "artifacts" and parts[2] == "summary":
            summary = self._find_artifact_summary(parts[1])
            if summary is None:
                return self._error(404, "not_found", "artifact not found")
            return self._json(200, summary)
        if method == "GET" and len(parts) == 3 and parts[0] == "artifacts" and parts[2] == "content":
            return self._artifact_content(parts[1], json_body)
        return None

    def _artifact_content(self, artifact_id: str, json_body: dict[str, Any] | None) -> HttpResponse:
        body = json_body if isinstance(json_body, dict) else {}
        raw_ref = body.get("ref")
        if raw_ref is None:
            raw_ref = self._find_artifact_ref(artifact_id)
        try:
            ref = self._resource_ref(raw_ref)
            if ref.artifact_id != artifact_id:
                return self._error(400, "bad_request", "artifact id does not match request ref")
            retrieval = self.artifact_content_retrieval_service or self.server.retrieval
            return self._json(
                200,
                retrieval.get_artifact_content(
                    ref,
                    grants=body.get("grants", {"artifact": {"read": "full"}}),
                    caller_context=body.get(
                        "caller_context",
                        {"caller": "http_api", "run_id": ref.run_id},
                    ),
                    purpose=body.get("purpose", "http artifact content retrieval"),
                ),
            )
        except PermissionError as exc:
            return self._error(403, "forbidden", str(exc), capability="artifact_content")
        except (FileNotFoundError, TypeError, ValueError) as exc:
            return self._error(400, "bad_request", str(exc), capability="artifact_content")

    def _find_artifact_ref(self, artifact_id: str) -> dict[str, Any] | None:
        for path in sorted(self.root_path.glob(f"runs/*/artifacts/{artifact_id}.json")):
            summary = self._find_artifact_summary(artifact_id)
            if summary is not None and isinstance(summary.get("ref"), dict):
                return summary["ref"]
            run_id = path.parent.parent.name
            return {
                "ref_type": "artifact",
                "scope": "run",
                "run_id": run_id,
                "artifact_id": artifact_id,
            }
        return None

    def _resource_ref(self, raw_ref: Any) -> ResourceRef:
        if not isinstance(raw_ref, dict):
            raise ValueError("artifact content requires a structured ref")
        return ResourceRef(
            ref_type=str(raw_ref.get("ref_type") or ""),
            scope=str(raw_ref.get("scope") or ""),
            run_id=str(raw_ref.get("run_id") or ""),
            artifact_id=str(raw_ref.get("artifact_id") or ""),
        )
