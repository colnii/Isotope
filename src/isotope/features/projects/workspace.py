"""Project workspace composition flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ..files.flow import FileFlow
from ..tasks.flow import TaskFlow
from ..workbench.flow import WorkbenchFlow, WorkbenchView
from .flow import ProjectDetail, ProjectFlow


@dataclass(frozen=True)
class ProjectWorkspace:
    project_detail: ProjectDetail
    workbench: WorkbenchView

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_detail": self.project_detail.to_dict(),
            "workbench": self.workbench.to_dict(),
        }


class ProjectWorkspaceFlow:
    """Create a linked project, task, file, and matching workbench view."""

    def __init__(self, core: ProductCore):
        self.core = core

    @classmethod
    def in_process(cls, root: Path | str) -> "ProjectWorkspaceFlow":
        return cls(ProductCore.in_process(root))

    def create_workspace(
        self,
        *,
        project_name: str,
        project_summary: str,
        task_goal: str,
        task_message: str,
        file_name: str,
        file_summary: str,
        file_content: str,
        search_query: str | None = None,
    ) -> ProjectWorkspace:
        project_flow = ProjectFlow(self.core)
        task_flow = TaskFlow(self.core)
        file_flow = FileFlow(self.core)

        project = project_flow.create_project(
            name=project_name,
            summary=project_summary,
        )
        task = task_flow.create_task(
            goal=task_goal,
            first_message=task_message,
        )
        file_record = file_flow.create_text_file(
            name=file_name,
            summary=file_summary,
            content=file_content,
        )
        project_flow.add_task(project.project_id, task.task_id)
        linked_project = project_flow.add_file(project.project_id, file_record.file_id)
        detail = project_flow.get_project_detail(linked_project.project_id)
        workbench = WorkbenchFlow(self.core).summary(
            query=search_query or project_name,
        )
        return ProjectWorkspace(project_detail=detail, workbench=workbench)
