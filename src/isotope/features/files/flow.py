"""User-facing file feature flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import ProductCore


@dataclass(frozen=True)
class FileSummary:
    file_id: str
    name: str
    summary: str
    artifact_type: str
    artifact_ref: dict[str, Any]
    run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "summary": self.summary,
            "artifact_type": self.artifact_type,
            "artifact_ref": dict(self.artifact_ref),
            "run_id": self.run_id,
        }


class FileFlow:
    """Thin user-facing file flow over ProductCore."""

    def __init__(self, core: ProductCore):
        self.core = core
        self._files: dict[str, FileSummary] = {}

    @classmethod
    def in_process(cls, root: Path | str) -> "FileFlow":
        return cls(ProductCore.in_process(root))

    def create_text_file(self, *, name: str, summary: str, content: str) -> FileSummary:
        clean_name = self._require_non_empty_text("name", name)
        clean_summary = self._require_non_empty_text("summary", summary)
        clean_content = self._require_non_empty_text("content", content)
        session = self.core.start_session()
        run = self.core.start_run(session.session_id, goal=f"store file: {clean_name}")
        artifact = self.core.runtime.create_source_artifact(
            run.run_id,
            summary=clean_summary,
            content=clean_content,
        )
        artifact_ref = artifact["artifact_ref"].to_dict()
        file_summary = FileSummary(
            file_id=artifact_ref["artifact_id"],
            name=clean_name,
            summary=artifact["artifact_summary"],
            artifact_type=artifact["artifact_type"],
            artifact_ref=artifact_ref,
            run_id=run.run_id,
        )
        self._files[file_summary.file_id] = file_summary
        return file_summary

    def get_file(self, file_id: str) -> FileSummary:
        try:
            return self._files[file_id]
        except KeyError as exc:
            raise ValueError(f"unknown file_id: {file_id}") from exc

    def _require_non_empty_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty")
        return stripped
