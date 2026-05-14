"""Retrieval service boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from ..platform.schemas.refs import ResourceRef


class RetrievalService:
    """Minimal artifact-summary retrieval boundary for the v0.1 slice."""

    def __init__(self, artifact_store):
        self.artifact_store = artifact_store

    def get_artifact_summary(self, ref: ResourceRef, grants: dict) -> dict:
        self._validate_artifact_ref(ref, label="artifact summary retrieval")
        artifact_grants = self._artifact_grants(
            grants,
            missing_message="artifact summary read is not granted",
        )
        if not isinstance(artifact_grants, dict) or artifact_grants.get("read") != "summary":
            raise PermissionError("artifact summary read is not granted")

        metadata = self.artifact_store.get_metadata(ref, include_provenance=True)
        return {
            "ref": ref.to_dict(),
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "provenance": dict(metadata["provenance"]),
        }

    def get_artifact_content(
        self,
        ref: ResourceRef,
        *,
        grants: dict,
        caller_context: dict,
        purpose: str,
    ) -> dict:
        self._validate_artifact_ref(ref, label="artifact full content retrieval")
        if not isinstance(caller_context, dict) or not caller_context:
            raise TypeError("caller_context must be a non-empty dict")
        if not isinstance(caller_context.get("caller"), str) or not caller_context["caller"]:
            raise ValueError("caller_context must include caller")
        if not isinstance(purpose, str) or not purpose:
            raise ValueError("purpose must be a non-empty string")

        artifact_grants = self._artifact_grants(
            grants,
            missing_message="artifact full content read is not granted",
        )
        if not isinstance(artifact_grants, dict) or artifact_grants.get("read") != "full":
            raise PermissionError("artifact full content read is not granted")

        metadata = self.artifact_store.get_metadata(ref, include_provenance=True)
        content = self.artifact_store.get_content(ref)
        return {
            "status": "ok",
            "view": "full",
            "ref": ref.to_dict(),
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "content": content,
            "provenance": dict(metadata["provenance"]),
        }

    def _validate_artifact_ref(self, ref: ResourceRef, *, label: str) -> None:
        if not isinstance(ref, ResourceRef):
            raise TypeError(f"{label} requires a structured ResourceRef")
        if ref.ref_type != "artifact":
            raise ValueError(f"{label} requires an artifact ResourceRef")

    def _artifact_grants(self, grants: dict, *, missing_message: str) -> dict:
        if not isinstance(grants, dict):
            raise TypeError("retrieval grants must be a dict")
        artifact_grants = grants.get("artifact")
        if not isinstance(artifact_grants, dict):
            raise PermissionError(missing_message)
        return artifact_grants
