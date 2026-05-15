"""Artifact schema shapes for the current slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .refs import ResourceRef


@dataclass(frozen=True)
class Artifact:
    """Minimal artifact shape for the v0.1 slice."""

    artifact_id: str
    run_id: str
    ref: ResourceRef
    artifact_type: str
    summary: str
    content: str
    provenance: dict[str, Any]
    basis_refs: list[dict[str, Any]] = field(default_factory=list)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
