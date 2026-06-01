"""Ask the local workbench with a bounded LLM context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ...core import ProductCore
from ...llm.prompts import load_system_prompt
from ...llm.provider import LLMResponse
from ..search.flow import SearchResult
from ..workbench.flow import WorkbenchFlow, WorkbenchView


class AskProvider(Protocol):
    provider: str
    model: str

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        ...


@dataclass(frozen=True)
class WorkbenchAskReference:
    rank: int
    result_type: str
    result_id: str
    title: str
    summary: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "result_type": self.result_type,
            "result_id": self.result_id,
            "title": self.title,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class WorkbenchAskAnswer:
    question: str
    answer: str
    provider: str
    model: str
    finish_reason: str
    usage: dict[str, Any]
    workbench: WorkbenchView
    references: tuple[WorkbenchAskReference, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "question": self.question,
            "answer": self.answer,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "usage": dict(self.usage),
            "references": [reference.to_dict() for reference in self.references],
            "context": self.workbench.to_dict(),
        }


class WorkbenchAskFlow:
    """User-facing ask flow over the low-sensitive workbench summary."""

    def __init__(self, core: ProductCore, *, provider: AskProvider):
        self.core = core
        self.provider = provider

    @classmethod
    def in_process(
        cls,
        root: Path | str,
        *,
        provider: AskProvider,
    ) -> "WorkbenchAskFlow":
        return cls(ProductCore.in_process(root), provider=provider)

    def answer(
        self,
        question: str,
        *,
        search_limit: int | None = 5,
        max_tokens: int = 512,
    ) -> WorkbenchAskAnswer:
        clean_question = _require_non_empty_text("question", question)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        workbench = _with_generic_context_fallback(
            WorkbenchFlow(self.core).summary(
                query=clean_question,
                search_limit=search_limit,
            ),
            search_limit=search_limit,
        )
        references = _build_references(workbench)
        response = self.provider.generate(
            _build_workbench_ask_messages(clean_question, workbench, references),
            max_tokens=max_tokens,
        )
        answer = response.content.strip()
        if not answer:
            raise ValueError("provider returned empty answer")
        return WorkbenchAskAnswer(
            question=clean_question,
            answer=answer,
            provider=response.provider,
            model=response.model,
            finish_reason=response.finish_reason,
            usage=dict(response.usage),
            workbench=workbench,
            references=references,
        )


def _build_workbench_ask_messages(
    question: str,
    workbench: WorkbenchView,
    references: tuple[WorkbenchAskReference, ...] = (),
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": load_system_prompt("workbench_ask"),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "references": [reference.to_dict() for reference in references],
                    "workbench": workbench.to_dict(),
                    "output_requirements": [
                        "用中文回答",
                        "一到三句话",
                        "优先给可执行下一步",
                        "如果 references 不为空，优先根据 references 中的条目回答",
                        "不要输出 JSON",
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _build_references(
    workbench: WorkbenchView,
) -> tuple[WorkbenchAskReference, ...]:
    return tuple(
        WorkbenchAskReference(
            rank=index,
            result_type=result.result_type,
            result_id=result.result_id,
            title=result.title,
            summary=result.summary,
        )
        for index, result in enumerate(workbench.search_results, start=1)
    )


def _with_generic_context_fallback(
    workbench: WorkbenchView,
    *,
    search_limit: int | None,
) -> WorkbenchView:
    if workbench.search_results:
        return workbench
    fallback_results = _fallback_search_results(workbench, limit=search_limit)
    if not fallback_results:
        return workbench
    return WorkbenchView(
        projects=workbench.projects,
        tasks=workbench.tasks,
        files=workbench.files,
        search_results=fallback_results,
        empty_state=workbench.empty_state,
        updated_at=workbench.updated_at,
    )


def _fallback_search_results(
    workbench: WorkbenchView,
    *,
    limit: int | None,
) -> tuple[SearchResult, ...]:
    results: list[SearchResult] = []
    for project in workbench.projects:
        results.append(
            SearchResult(
                result_type="project",
                result_id=project.project_id,
                title=project.name,
                summary=project.summary,
                item=project.to_dict(),
            )
        )
    for task in workbench.tasks:
        results.append(
            SearchResult(
                result_type="task",
                result_id=task.task_id,
                title=task.goal,
                summary=task.result_summary,
                item=task.to_dict(),
            )
        )
    for file_summary in workbench.files:
        results.append(
            SearchResult(
                result_type="file",
                result_id=file_summary.file_id,
                title=file_summary.name,
                summary=file_summary.summary,
                item=file_summary.to_dict(),
            )
        )
    if limit is None:
        return tuple(results)
    if not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    return tuple(results[:limit])


def _require_non_empty_text(field_name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be empty")
    return stripped
