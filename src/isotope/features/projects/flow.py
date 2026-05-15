"""User-facing project feature flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ...platform.ids import new_id


@dataclass(frozen=True)
class ProjectSummary:
    project_id: str
    name: str
    summary: str
    task_ids: tuple[str, ...] = ()
    file_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "summary": self.summary,
            "task_ids": list(self.task_ids),
            "file_ids": list(self.file_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectSummary":
        return cls(
            project_id=_required_string(data, "project_id"),
            name=_required_string(data, "name"),
            summary=_required_string(data, "summary"),
            task_ids=tuple(_required_string_list(data, "task_ids")),
            file_ids=tuple(_required_string_list(data, "file_ids")),
        )


class ProjectFlow:
    """Thin user-facing project flow over ProductCore."""

    def __init__(self, core: ProductCore):
        self.core = core
        self._index_path = Path(self.core.runtime.root) / "projects" / "index.json"
        self._projects: dict[str, ProjectSummary] = self._load_index()

    @classmethod
    def in_process(cls, root: Path | str) -> "ProjectFlow":
        return cls(ProductCore.in_process(root))

    def create_project(self, *, name: str, summary: str) -> ProjectSummary:
        project = ProjectSummary(
            project_id=new_id("project"),
            name=self._require_non_empty_text("name", name),
            summary=self._require_non_empty_text("summary", summary),
        )
        return self._store_summary(project)

    def get_project(self, project_id: str) -> ProjectSummary:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise ValueError(f"unknown project_id: {project_id}") from exc

    def list_projects(self) -> list[ProjectSummary]:
        return list(self._projects.values())

    def add_task(self, project_id: str, task_id: str) -> ProjectSummary:
        project = self.get_project(project_id)
        clean_task_id = self._require_non_empty_text("task_id", task_id)
        task_ids = _append_unique(project.task_ids, clean_task_id)
        return self._store_summary(
            ProjectSummary(
                project_id=project.project_id,
                name=project.name,
                summary=project.summary,
                task_ids=task_ids,
                file_ids=project.file_ids,
            )
        )

    def add_file(self, project_id: str, file_id: str) -> ProjectSummary:
        project = self.get_project(project_id)
        clean_file_id = self._require_non_empty_text("file_id", file_id)
        file_ids = _append_unique(project.file_ids, clean_file_id)
        return self._store_summary(
            ProjectSummary(
                project_id=project.project_id,
                name=project.name,
                summary=project.summary,
                task_ids=project.task_ids,
                file_ids=file_ids,
            )
        )

    def _store_summary(self, summary: ProjectSummary) -> ProjectSummary:
        self._projects[summary.project_id] = summary
        self._save_index()
        return summary

    def _require_non_empty_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty")
        return stripped

    def _load_index(self) -> dict[str, ProjectSummary]:
        if not self._index_path.exists():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(f"malformed project index: {self._index_path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
            raise ValueError(f"malformed project index: {self._index_path}")
        projects: dict[str, ProjectSummary] = {}
        for item in data["projects"]:
            if not isinstance(item, dict):
                raise ValueError(f"malformed project index: {self._index_path}")
            summary = ProjectSummary.from_dict(item)
            projects[summary.project_id] = summary
        return projects

    def _save_index(self) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "projects": [summary.to_dict() for summary in self._projects.values()]
        }
        self._index_path.write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    if value in values:
        return values
    return (*values, value)


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"project summary requires {field_name}")
    return value


def _required_string_list(data: dict[str, Any], field_name: str) -> list[str]:
    value = data.get(field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"project summary requires {field_name}")
    return value
