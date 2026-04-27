"""Retrieval service boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from .refs import ResourceRef


class RetrievalService:
    """Minimal artifact-summary retrieval boundary for the v0.1 slice."""

    def __init__(self, artifact_store):
        self.artifact_store = artifact_store

    def get_artifact_summary(self, ref: ResourceRef, grants: dict) -> dict:
        if not isinstance(ref, ResourceRef):
            raise TypeError("artifact summary retrieval requires a structured ResourceRef")
        if grants.get("artifact", {}).get("read") != "summary":
            raise PermissionError("artifact summary read is not granted")

        metadata = self.artifact_store.get_metadata(ref.artifact_id)
        return {
            "ref": ref.to_dict(),
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
        }
