"""User-facing file feature flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ...platform.schemas.refs import ResourceRef


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileSummary":
        return cls(
            file_id=_required_string(data, "file_id"),
            name=_required_string(data, "name"),
            summary=_required_string(data, "summary"),
            artifact_type=_required_string(data, "artifact_type"),
            artifact_ref=dict(_required_dict(data, "artifact_ref")),
            run_id=_required_string(data, "run_id"),
        )


class FileFlow:
    """Thin user-facing file flow over ProductCore."""

    def __init__(self, core: ProductCore):
        self.core = core
        self._index_path = Path(self.core.runtime.root) / "files" / "index.json"
        self._files: dict[str, FileSummary] = self._load_index()

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
        self._save_index()
        return file_summary

    def get_file(self, file_id: str) -> FileSummary:
        try:
            summary = self._files[file_id]
        except KeyError as exc:
            raise ValueError(f"unknown file_id: {file_id}") from exc
        return self._refresh_from_artifact_record(summary)

    def list_files(self) -> list[FileSummary]:
        return [
            self._refresh_from_artifact_record(summary)
            for summary in self._files.values()
        ]

    def _refresh_from_artifact_record(self, summary: FileSummary) -> FileSummary:
        artifact_ref = _artifact_ref_from_dict(summary.artifact_ref)
        record = self.core.runtime.get_artifact_record(artifact_ref)
        refreshed = FileSummary(
            file_id=summary.file_id,
            name=summary.name,
            summary=_required_string(record, "summary"),
            artifact_type=_required_string(record, "artifact_type"),
            artifact_ref=dict(_required_dict(record, "ref")),
            run_id=summary.run_id,
        )
        if refreshed != summary:
            self._files[summary.file_id] = refreshed
            self._save_index()
        return refreshed

    def _require_non_empty_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty")
        return stripped

    def _load_index(self) -> dict[str, FileSummary]:
        if not self._index_path.exists():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(f"malformed file index: {self._index_path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            raise ValueError(f"malformed file index: {self._index_path}")
        files: dict[str, FileSummary] = {}
        for item in data["files"]:
            if not isinstance(item, dict):
                raise ValueError(f"malformed file index: {self._index_path}")
            file_summary = FileSummary.from_dict(item)
            files[file_summary.file_id] = file_summary
        return files

    def _save_index(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "files": [file_summary.to_dict() for file_summary in self._files.values()]
        }
        self._index_path.write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"file summary requires {field_name}")
    return value


def _required_dict(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"file summary requires {field_name}")
    return value


def _artifact_ref_from_dict(data: dict[str, Any]) -> ResourceRef:
    return ResourceRef(
        ref_type=_required_string(data, "ref_type"),
        scope=_required_string(data, "scope"),
        run_id=_required_string(data, "run_id"),
        artifact_id=_required_string(data, "artifact_id"),
    )
