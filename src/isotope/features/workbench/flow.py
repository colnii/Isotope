"""User-facing workbench summary flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    empty_state: dict[str, Any] | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "projects": [summary.to_dict() for summary in self.projects],
            "tasks": [summary.to_dict() for summary in self.tasks],
            "files": [summary.to_dict() for summary in self.files],
            "search_results": [result.to_dict() for result in self.search_results],
            "empty_state": self.empty_state,
            "updated_at": self.updated_at,
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
        projects = tuple(project_flow.list_projects())
        tasks = tuple(task_flow.list_tasks())
        files = tuple(file_flow.list_files())
        search_results: tuple[SearchResult, ...] = ()
        if query is not None:
            search_results = tuple(
                SearchFlow(self.core).search(
                    query,
                    result_types=search_types,
                    limit=search_limit,
                )
            )
        is_empty = not projects and not tasks and not files and not search_results
        return WorkbenchView(
            projects=projects,
            tasks=tasks,
            files=files,
            search_results=search_results,
            empty_state=_empty_state() if is_empty else None,
            updated_at=_latest_index_updated_at(Path(self.core.runtime.root)),
        )


def _empty_state() -> dict[str, Any]:
    return {
        "is_empty": True,
        "title": "还没有工作台内容",
        "message": "先创建一个项目、任务或文件摘要，工作台会在这里汇总。",
        "primary_action": "create_project",
    }


def _latest_index_updated_at(root: Path) -> str | None:
    index_paths = (
        root / "projects" / "index.json",
        root / "tasks" / "index.json",
        root / "files" / "index.json",
    )
    mtimes = [path.stat().st_mtime for path in index_paths if path.exists()]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc).isoformat()
