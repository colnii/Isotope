"""User-facing search feature flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ...rag import SummarySearchDocument, rank_summary_documents
from ..files.flow import FileFlow, FileSummary
from ..projects.flow import ProjectFlow, ProjectSummary
from ..tasks.flow import TaskFlow, TaskSummary


SUPPORTED_RESULT_TYPES = ("project", "task", "file")


@dataclass(frozen=True)
class SearchResult:
    result_type: str
    result_id: str
    title: str
    summary: str | None
    item: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_type": self.result_type,
            "result_id": self.result_id,
            "title": self.title,
            "summary": self.summary,
            "item": dict(self.item),
        }


class SearchFlow:
    """Thin public search flow over user-facing summaries."""

    def __init__(self, core: ProductCore):
        self.core = core

    @classmethod
    def in_process(cls, root: Path | str) -> "SearchFlow":
        return cls(ProductCore.in_process(root))

    def search(
        self,
        query: str,
        *,
        result_types: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> list[SearchResult]:
        clean_query = self._require_non_empty_text("query", query)
        allowed_types = self._validate_result_types(result_types)
        clean_limit = self._validate_limit(limit)
        needle = clean_query.casefold()
        project_flow = ProjectFlow(self.core)
        task_flow = TaskFlow(self.core)
        file_flow = FileFlow(self.core)
        results: list[SearchResult] = []
        ranked_candidates: list[SearchResult] = []
        if "project" in allowed_types:
            project_results = [
                self._project_result(project) for project in project_flow.list_projects()
            ]
            results.extend(
                result
                for result in project_results
                if _matches(needle, result.result_id, result.title, result.summary)
            )
            ranked_candidates.extend(project_results)
        if "task" in allowed_types:
            task_results = [self._task_result(task) for task in task_flow.list_tasks()]
            results.extend(
                result
                for result in task_results
                if _matches(needle, result.result_id, result.title, result.summary)
            )
            ranked_candidates.extend(task_results)
        if "file" in allowed_types:
            file_results = [
                self._file_result(file_summary)
                for file_summary in file_flow.list_files()
            ]
            results.extend(
                result
                for result in file_results
                if _matches(needle, result.result_id, result.title, result.summary)
            )
            ranked_candidates.extend(file_results)
        if not results:
            results = _rank_results(clean_query, ranked_candidates)
        if clean_limit is None:
            return results
        return results[:clean_limit]

    def _project_result(self, project: ProjectSummary) -> SearchResult:
        return SearchResult(
            result_type="project",
            result_id=project.project_id,
            title=project.name,
            summary=project.summary,
            item=project.to_dict(),
        )

    def _task_result(self, task: TaskSummary) -> SearchResult:
        return SearchResult(
            result_type="task",
            result_id=task.task_id,
            title=task.goal,
            summary=task.result_text,
            item=task.to_dict(),
        )

    def _file_result(self, file_summary: FileSummary) -> SearchResult:
        return SearchResult(
            result_type="file",
            result_id=file_summary.file_id,
            title=file_summary.name,
            summary=file_summary.summary,
            item=file_summary.to_dict(),
        )

    def _require_non_empty_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty")
        return stripped

    def _validate_result_types(
        self,
        result_types: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        if result_types is None:
            return SUPPORTED_RESULT_TYPES
        clean_types: list[str] = []
        for result_type in result_types:
            if result_type not in SUPPORTED_RESULT_TYPES:
                raise ValueError(f"unsupported search result_type: {result_type}")
            if result_type not in clean_types:
                clean_types.append(result_type)
        return tuple(clean_types)

    def _validate_limit(self, limit: int | None) -> int | None:
        if limit is None:
            return None
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        return limit


def _matches(needle: str, *values: str | None) -> bool:
    return any(value is not None and needle in value.casefold() for value in values)


def _rank_results(query: str, results: list[SearchResult]) -> list[SearchResult]:
    result_by_document_id = {
        _document_id_for_result(result): result for result in results
    }
    documents = [
        SummarySearchDocument(
            document_id=_document_id_for_result(result),
            title=result.title,
            summary=result.summary,
        )
        for result in results
    ]
    return [
        result_by_document_id[hit.document.document_id]
        for hit in rank_summary_documents(query, documents)
    ]


def _document_id_for_result(result: SearchResult) -> str:
    return f"{result.result_type}:{result.result_id}"
