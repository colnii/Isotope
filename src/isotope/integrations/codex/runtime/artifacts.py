"""Artifact payload helpers for Codex runtime projections."""

from __future__ import annotations

from typing import Any

from .projection import CodexRuntimeProjection


def codex_runtime_summary_artifact_payload(
    projection: CodexRuntimeProjection,
) -> dict[str, Any]:
    if not isinstance(projection, CodexRuntimeProjection):
        raise TypeError("projection must be a CodexRuntimeProjection")
    return {
        "kind": "codex_runtime_summary",
        "summary": projection.summary.to_dict(),
        "events": [event.to_dict() for event in projection.events],
    }
