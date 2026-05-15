"""User-facing workbench summary flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ..files.flow import FileFlow, FileSummary
from ..projects.flow import ProjectFlow, ProjectSummary
from ..search.flow import SearchFlow, SearchResult
from ..tasks.flow import TaskFlow, TaskSummary


@dataclass(frozen=True)
class WorkbenchView:
    projects: tuple[ProjectSummary, ...]
    tasks: tuple[TaskSummary, ...]
    files: tuple[FileSummary, ...]
    search_results: tuple[SearchResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "projects": [summary.to_dict() for summary in self.projects],
            "tasks": [summary.to_dict() for summary in self.tasks],
            "files": [summary.to_dict() for summary in self.files],
            "search_results": [result.to_dict() for result in self.search_results],
            "counts": {
                "projects": len(self.projects),
                "tasks": len(self.tasks),
                "files": len(self.files),
                "search_results": len(self.search_results),
            },
        }


class WorkbenchFlow:
    """Thin home-view flow over low-sensitive feature summaries."""

    def __init__(self, core: ProductCore):
        self.core = core

    @classmethod
    def in_process(cls, root: Path | str) -> "WorkbenchFlow":
        return cls(ProductCore.in_process(root))

    def summary(
        self,
        *,
        query: str | None = None,
        search_types: tuple[str, ...] | None = None,
        search_limit: int | None = None,
    ) -> WorkbenchView:
        project_flow = ProjectFlow(self.core)
        task_flow = TaskFlow(self.core)
        file_flow = FileFlow(self.core)
        search_results: tuple[SearchResult, ...] = ()
        if query is not None:
            search_results = tuple(
                SearchFlow(self.core).search(
                    query,
                    result_types=search_types,
                    limit=search_limit,
                )
            )
        return WorkbenchView(
            projects=tuple(project_flow.list_projects()),
            tasks=tuple(task_flow.list_tasks()),
            files=tuple(file_flow.list_files()),
            search_results=search_results,
        )
