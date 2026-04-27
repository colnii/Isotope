"""Artifact store boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from pathlib import Path

from .ids import new_id
from .models import Artifact
from .refs import make_artifact_ref


class ArtifactStore:
    """Minimal artifact store for the write_artifact_tool slice."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._artifacts: dict[str, Artifact] = {}

    def create_artifact(
        self,
        run_id: str,
        execution_id: str,
        artifact_type: str,
        summary: str,
        content: str,
    ) -> Artifact:
        artifact_id = new_id("artifact")
        artifact = Artifact(
            artifact_id=artifact_id,
            run_id=run_id,
            ref=make_artifact_ref(run_id=run_id, artifact_id=artifact_id),
            artifact_type=artifact_type,
            summary=summary,
            content=content,
            provenance={"execution_id": execution_id},
        )
        self._artifacts[artifact.artifact_id] = artifact
        return artifact

    def list_artifacts(self, run_id: str) -> list[Artifact]:
        return [
            artifact
            for artifact in self._artifacts.values()
            if artifact.run_id == run_id
        ]

    def get_metadata(self, artifact_id: str) -> dict[str, str]:
        artifact = self._artifacts[artifact_id]
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "summary": artifact.summary,
        }

    def get_content(self, artifact_id: str) -> str:
        return self._artifacts[artifact_id].content
