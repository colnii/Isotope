"""Preview-only recall over stored research report artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Mapping

from isotope.platform.schemas.refs import make_artifact_ref
from isotope.rag import HybridRetriever, RetrievalDocument
from isotope.rag.index import build_rag_index


RESEARCH_REPORT_ARTIFACT_TYPE = "research.report"
RESEARCH_RECALL_CONTENT_POLICY = "research_report_artifact_preview_only"


@dataclass(frozen=True)
class ResearchArtifactPreview:
    run_id: str
    artifact_id: str
    artifact_type: str
    summary: str
    ref: dict[str, Any]
    provenance: dict[str, Any]
    basis_refs: list[dict[str, Any]]
    source_refs: list[dict[str, Any]]


def build_research_recall_payload(
    *,
    root: Path | str,
    query: str,
    run_id: str | None = None,
    limit: int = 20,
    dense_retrieval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).expanduser()
    clean_query = _required_text(query, "query")
    if run_id is not None:
        run_id = _required_text(run_id, "run_id")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    previews = list_research_report_previews(root_path, run_id=run_id)
    documents = [research_artifact_preview_document(preview) for preview in previews]
    index = build_rag_index(documents, dense_retrieval)
    components = index.components() if index is not None else None
    result = HybridRetriever(
        embedding_provider=components.embedding_provider if components else None,
        vector_store=components.vector_store if components else None,
    ).search(
        query=clean_query,
        documents=documents,
        limit=max(limit, len(documents), 1),
    )
    previews_by_document_id = {
        _preview_document_id(preview): preview for preview in previews
    }
    matched = [
        previews_by_document_id[hit.document.document_id]
        for hit in result.hits
        if hit.document.document_id in previews_by_document_id
    ]
    visible = matched[:limit]
    return {
        "status": "ok",
        "content_policy": RESEARCH_RECALL_CONTENT_POLICY,
        "store": {
            "root": str(root_path),
            "path": str(root_path / "runs"),
            "format": "artifact_store",
        },
        "query": clean_query,
        "run_id": run_id,
        "summary": {
            "total": len(previews),
            "matched": len(matched),
            "hidden_artifacts": max(0, len(matched) - len(visible)),
        },
        "retrieval": {
            "backend": result.backend,
            "dense_status": (result.metadata or {}).get("dense_status", "unknown"),
        },
        "results": [_preview_result(preview) for preview in visible],
    }


def list_research_report_previews(
    root: Path | str,
    *,
    run_id: str | None = None,
) -> list[ResearchArtifactPreview]:
    root_path = Path(root).expanduser()
    if run_id is not None:
        run_id = _required_text(run_id, "run_id")
    runs_dir = root_path / "runs"
    if not runs_dir.exists():
        return []

    previews: list[ResearchArtifactPreview] = []
    run_dirs = [runs_dir / run_id] if run_id is not None else sorted(runs_dir.iterdir())
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            continue
        artifact_dir = run_dir / "artifacts"
        if not artifact_dir.is_dir():
            continue
        for path in sorted(artifact_dir.glob("*.json")):
            preview = _preview_from_artifact_file(path, fallback_run_id=run_dir.name)
            if preview is not None:
                previews.append(preview)
    return previews


def research_artifact_preview_document(
    preview: ResearchArtifactPreview,
) -> RetrievalDocument:
    source_text = _refs_text(preview.source_refs)
    basis_text = _refs_text(preview.basis_refs)
    provenance_text = " ".join(str(value) for value in preview.provenance.values())
    return RetrievalDocument(
        document_id=_preview_document_id(preview),
        title=preview.summary,
        summary=" ".join(
            part
            for part in (
                preview.summary,
                preview.run_id,
                preview.artifact_id,
                source_text,
                basis_text,
                provenance_text,
            )
            if part
        ),
        metadata={
            "run_id": preview.run_id,
            "artifact_id": preview.artifact_id,
            "artifact_type": preview.artifact_type,
            "ref": dict(preview.ref),
            "source_refs": [dict(ref) for ref in preview.source_refs],
            "provenance": dict(preview.provenance),
        },
        sensitivity="low",
    )


def _preview_from_artifact_file(
    path: Path,
    *,
    fallback_run_id: str,
) -> ResearchArtifactPreview | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ValueError(f"malformed artifact file: {path}") from exc
    if not isinstance(data, Mapping):
        raise ValueError(f"malformed artifact file: {path}")
    data = {key: value for key, value in data.items() if key != "content"}
    if data.get("artifact_type") != RESEARCH_REPORT_ARTIFACT_TYPE:
        return None
    return _preview_from_mapping(data, fallback_run_id=fallback_run_id, path=path)


def _preview_from_mapping(
    data: Mapping[str, Any],
    *,
    fallback_run_id: str,
    path: Path,
) -> ResearchArtifactPreview:
    run_id = _mapping_text(data, "run_id", fallback=fallback_run_id, path=path)
    artifact_id = _mapping_text(data, "artifact_id", path=path)
    artifact_type = _mapping_text(data, "artifact_type", path=path)
    summary = _mapping_text(data, "summary", path=path)
    ref = data.get("ref")
    if not isinstance(ref, Mapping):
        ref = make_artifact_ref(run_id=run_id, artifact_id=artifact_id).to_dict()
    return ResearchArtifactPreview(
        run_id=run_id,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        summary=summary,
        ref=dict(ref),
        provenance=_mapping_dict(data.get("provenance")),
        basis_refs=_mapping_list(data.get("basis_refs")),
        source_refs=_mapping_list(data.get("source_refs")),
    )


def _preview_result(preview: ResearchArtifactPreview) -> dict[str, Any]:
    result = {
        "run_id": preview.run_id,
        "artifact_id": preview.artifact_id,
        "artifact_type": preview.artifact_type,
        "summary": preview.summary,
        "ref": dict(preview.ref),
        "source_refs": [dict(ref) for ref in preview.source_refs],
        "provenance": dict(preview.provenance),
    }
    if preview.basis_refs:
        result["basis_refs"] = [dict(ref) for ref in preview.basis_refs]
    return result


def _preview_document_id(preview: ResearchArtifactPreview) -> str:
    return f"{preview.run_id}:{preview.artifact_id}"


def _mapping_text(
    data: Mapping[str, Any],
    key: str,
    *,
    path: Path,
    fallback: str | None = None,
) -> str:
    value = data.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"malformed artifact file: {path}")
    return value.strip()


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    clean = value.strip()
    if not clean:
        raise ValueError(f"{name} must be a non-empty string")
    return clean


def _mapping_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _refs_text(refs: list[dict[str, Any]]) -> str:
    return " ".join(str(value) for ref in refs for value in ref.values())
