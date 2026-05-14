"""Artifact store boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ..models import Artifact
from ..platform.ids import new_id
from ..refs import ResourceRef, make_artifact_ref


class ArtifactStore:
    """Minimal artifact store for the write_artifact_tool slice."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._artifacts: dict[str, Artifact] = {}

    def artifact_path(self, run_id: str, artifact_id: str) -> Path:
        return self.root / "runs" / run_id / "artifacts" / f"{artifact_id}.json"

    def create_artifact(
        self,
        run_id: str,
        execution_id: str,
        artifact_type: str,
        summary: str,
        content: str,
        proposal_id: str | None = None,
        decision_id: str | None = None,
        basis_refs: list[dict[str, Any]] | None = None,
        source_refs: list[dict[str, Any]] | None = None,
    ) -> Artifact:
        artifact_id = new_id("artifact")
        provenance = {"execution_id": execution_id}
        if proposal_id is not None:
            provenance["proposal_id"] = proposal_id
        if decision_id is not None:
            provenance["decision_id"] = decision_id
        artifact = Artifact(
            artifact_id=artifact_id,
            run_id=run_id,
            ref=make_artifact_ref(run_id=run_id, artifact_id=artifact_id),
            artifact_type=artifact_type,
            summary=summary,
            content=content,
            provenance=provenance,
            basis_refs=[dict(ref) for ref in basis_refs or []],
            source_refs=[dict(ref) for ref in source_refs or []],
        )
        self._artifacts[artifact.artifact_id] = artifact
        self._write_artifact(artifact)
        return artifact

    def list_artifacts(self, run_id: str) -> list[Artifact]:
        artifact_dir = self.root / "runs" / run_id / "artifacts"
        artifacts = [
            artifact
            for artifact in self._artifacts.values()
            if artifact.run_id == run_id
        ]
        if artifact_dir.exists():
            seen = {artifact.artifact_id for artifact in artifacts}
            for path in sorted(artifact_dir.glob("*.json")):
                artifact = self._read_artifact_file(path)
                if artifact.artifact_id not in seen:
                    artifacts.append(artifact)
                    seen.add(artifact.artifact_id)
        return artifacts

    def get_metadata(
        self,
        artifact_ref: ResourceRef | str,
        *,
        include_provenance: bool = False,
    ) -> dict[str, Any]:
        artifact = self._get_artifact(artifact_ref)
        metadata = {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "summary": artifact.summary,
        }
        if include_provenance:
            metadata["provenance"] = dict(artifact.provenance)
        if artifact.basis_refs:
            metadata["basis_refs"] = [dict(ref) for ref in artifact.basis_refs]
        if artifact.source_refs:
            metadata["source_refs"] = [dict(ref) for ref in artifact.source_refs]
        return metadata

    def get_content(self, artifact_ref: ResourceRef | str) -> str:
        return self._get_artifact(artifact_ref).content

    def _write_artifact(self, artifact: Artifact) -> None:
        path = self.artifact_path(artifact.run_id, artifact.artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._artifact_to_dict(artifact), sort_keys=True),
            encoding="utf-8",
        )

    def _artifact_to_dict(self, artifact: Artifact) -> dict[str, Any]:
        data: dict[str, Any] = {
            "artifact_id": artifact.artifact_id,
            "run_id": artifact.run_id,
            "ref": artifact.ref.to_dict(),
            "artifact_type": artifact.artifact_type,
            "summary": artifact.summary,
            "content": artifact.content,
            "provenance": artifact.provenance,
        }
        if artifact.basis_refs:
            data["basis_refs"] = [dict(ref) for ref in artifact.basis_refs]
        if artifact.source_refs:
            data["source_refs"] = [dict(ref) for ref in artifact.source_refs]
        return data

    def _get_artifact(self, artifact_ref: ResourceRef | str) -> Artifact:
        if isinstance(artifact_ref, ResourceRef):
            if artifact_ref.ref_type != "artifact":
                raise ValueError("artifact store requires an artifact ResourceRef")
            return self._read_artifact_by_path(
                self.artifact_path(artifact_ref.run_id, artifact_ref.artifact_id)
            )
        if isinstance(artifact_ref, str):
            if artifact_ref.startswith("artifact://"):
                raise TypeError("artifact store requires a structured ResourceRef or artifact_id")
            if artifact_ref in self._artifacts:
                return self._artifacts[artifact_ref]
            matches = sorted((self.root / "runs").glob(f"*/artifacts/{artifact_ref}.json"))
            if matches:
                return self._read_artifact_by_path(matches[0])
            raise FileNotFoundError(f"artifact not found: {artifact_ref}")
        raise TypeError("artifact store requires a structured ResourceRef or artifact_id")

    def _read_artifact_by_path(self, path: Path) -> Artifact:
        if not path.exists():
            raise FileNotFoundError(f"artifact not found: {path}")
        return self._read_artifact_file(path)

    def _read_artifact_file(self, path: Path) -> Artifact:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(f"malformed artifact file: {path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"malformed artifact file: {path}")
        try:
            return self._artifact_from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed artifact file: {path}") from exc

    def _artifact_from_dict(self, data: dict[str, Any]) -> Artifact:
        run_id = data["run_id"]
        artifact_id = data["artifact_id"]
        return Artifact(
            artifact_id=artifact_id,
            run_id=run_id,
            ref=make_artifact_ref(run_id=run_id, artifact_id=artifact_id),
            artifact_type=data["artifact_type"],
            summary=data["summary"],
            content=data["content"],
            provenance=dict(data["provenance"]),
            basis_refs=[dict(ref) for ref in data.get("basis_refs", [])],
            source_refs=[dict(ref) for ref in data.get("source_refs", [])],
        )
