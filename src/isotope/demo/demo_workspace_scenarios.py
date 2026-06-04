"""Workbench and project workspace developer demo scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..interfaces.http import create_http_app
from ..llm.provider import LLMResponse


def _run_project_workspace_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)
    response = app.request(
        "POST",
        "/projects/workspace",
        {
            "project_name": "portfolio demo",
            "project_summary": "autumn recruiting workspace",
            "task_goal": "build portfolio story",
            "task_message": "private task note",
            "file_name": "portfolio-notes.md",
            "file_summary": "portfolio notes",
            "file_content": "private file content",
            "search_query": "portfolio",
        },
    )
    workspace = response.body["workspace"]  # type: ignore[index]
    detail = workspace["project_detail"]
    workbench = workspace["workbench"]
    project = detail["project"]
    tasks = detail["tasks"]
    files = detail["files"]
    search_result_types = [
        result["result_type"]
        for result in workbench["search_results"]
    ]
    workspace_ok = (
        response.status_code == 201
        and len(tasks) == 1
        and len(files) == 1
        and project["task_ids"] == [tasks[0]["task_id"]]
        and project["file_ids"] == [files[0]["file_id"]]
        and workbench["counts"]
        == {
            "projects": 1,
            "tasks": 1,
            "files": 1,
            "search_results": 3,
        }
        and search_result_types == ["project", "task", "file"]
    )

    return {
        "scenario": "project-workspace",
        "transport": "in_process_http_facade",
        "workspace_ok": workspace_ok,
        "project_task_count": len(project["task_ids"]),
        "project_file_count": len(project["file_ids"]),
        "workbench_counts": dict(workbench["counts"]),
        "search_result_types": search_result_types,
        "post_workspace_status_code": response.status_code,
        "content_policy": "summary_only",
        "memory_status": "active",
    }


def _run_project_workspace_append_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)
    created = app.request(
        "POST",
        "/projects/workspace",
        {
            "project_name": "portfolio demo",
            "project_summary": "autumn recruiting workspace",
            "task_goal": "build portfolio story",
            "task_message": "private task note",
            "file_name": "portfolio-notes.md",
            "file_summary": "portfolio notes",
            "file_content": "private file content",
            "search_query": "portfolio",
        },
    )
    project_id = created.body["workspace"]["project_detail"]["project"]["project_id"]  # type: ignore[index]
    appended = app.request(
        "POST",
        f"/projects/{project_id}/workspace",
        {
            "task_goal": "polish portfolio case study",
            "task_message": "private second task note",
            "file_name": "portfolio-case-study.md",
            "file_summary": "portfolio case study notes",
            "file_content": "private second file content",
            "search_query": "portfolio",
        },
    )
    workspace = appended.body["workspace"]  # type: ignore[index]
    detail = workspace["project_detail"]
    workbench = workspace["workbench"]
    project = detail["project"]
    search_result_types = [
        result["result_type"]
        for result in workbench["search_results"]
    ]
    workspace_ok = (
        created.status_code == 201
        and appended.status_code == 200
        and project["project_id"] == project_id
        and len(project["task_ids"]) == 2
        and len(project["file_ids"]) == 2
        and workbench["counts"]
        == {
            "projects": 1,
            "tasks": 2,
            "files": 2,
            "search_results": 5,
        }
        and search_result_types == ["project", "task", "task", "file", "file"]
    )

    return {
        "scenario": "project-workspace-append",
        "transport": "in_process_http_facade",
        "workspace_ok": workspace_ok,
        "project_task_count": len(project["task_ids"]),
        "project_file_count": len(project["file_ids"]),
        "workbench_counts": dict(workbench["counts"]),
        "search_result_types": search_result_types,
        "post_workspace_status_code": created.status_code,
        "append_workspace_status_code": appended.status_code,
        "content_policy": "summary_only",
        "memory_status": "active",
    }


def _run_workbench_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    app = create_http_app(root)

    project_response = app.request(
        "POST",
        "/projects",
        {
            "name": "portfolio demo",
            "summary": "autumn recruiting workspace",
        },
    )
    task_response = app.request(
        "POST",
        "/tasks",
        {
            "goal": "build portfolio story",
            "message": "private task note",
        },
    )
    file_response = app.request(
        "POST",
        "/files",
        {
            "name": "portfolio-notes.md",
            "summary": "portfolio notes",
            "content": "private file content",
        },
    )
    get_workbench_response = app.request("GET", "/workbench")
    post_workbench_response = app.request(
        "POST",
        "/workbench",
        {
            "query": "portfolio",
            "types": ["task", "file"],
            "limit": 1,
        },
    )
    workbench = post_workbench_response.body["workbench"]  # type: ignore[index]
    counts = workbench["counts"]
    search_results = workbench["search_results"]
    search_result_types = [result["result_type"] for result in search_results]
    updated_at = workbench["updated_at"]
    empty_state = workbench["empty_state"]
    workbench_ok = (
        project_response.status_code == 201
        and task_response.status_code == 201
        and file_response.status_code == 201
        and get_workbench_response.status_code == 200
        and post_workbench_response.status_code == 200
        and counts == {
            "projects": 1,
            "tasks": 1,
            "files": 1,
            "search_results": 1,
        }
        and search_result_types == ["task"]
        and empty_state is None
        and isinstance(updated_at, str)
    )

    return {
        "scenario": "workbench",
        "transport": "in_process_http_facade",
        "workbench_ok": workbench_ok,
        "project_count": counts["projects"],
        "task_count": counts["tasks"],
        "file_count": counts["files"],
        "search_result_count": counts["search_results"],
        "search_result_types": search_result_types,
        "workbench_counts": dict(counts),
        "empty_state": empty_state,
        "updated_at_present": isinstance(updated_at, str),
        "get_workbench_status_code": get_workbench_response.status_code,
        "post_workbench_status_code": post_workbench_response.status_code,
        "search_query": "portfolio",
        "memory_status": "active",
        "content_policy": "summary_only",
    }


def _run_workbench_ask_demo(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    provider = _FakeWorkbenchAskProvider(
        "建议先把作品集项目拆成一个可展示任务。"
    )
    app = create_http_app(root, workbench_ask_provider=provider)

    app.request(
        "POST",
        "/projects",
        {
            "name": "秋招作品集",
            "summary": "秋招作品集项目工作台",
        },
    )
    app.request(
        "POST",
        "/tasks",
        {
            "goal": "秋招作品集任务拆解",
            "message": "private task note",
        },
    )
    app.request(
        "POST",
        "/files",
        {
            "name": "portfolio-notes.md",
            "summary": "秋招作品集素材摘要",
            "content": "PRIVATE_WORKBENCH_ASK_CONTENT_SHOULD_NOT_LEAK",
        },
    )
    answer_response = app.request(
        "POST",
        "/workbench/ask",
        {
            "question": "秋招作品集下一步做什么？",
            "limit": 3,
        },
    )
    answer = answer_response.body["answer"]  # type: ignore[index]

    return {
        "scenario": "workbench-ask",
        "transport": "in_process_http_facade",
        "question": answer["question"],
        "answer": answer["answer"],
        "provider": answer["provider"],
        "model": answer["model"],
        "provider_call_count": provider.call_count,
        "context_counts": answer["context"]["counts"],
        "post_workbench_ask_status_code": answer_response.status_code,
        "content_policy": "summary_only",
        "memory_status": "active",
    }


class _FakeWorkbenchAskProvider:
    provider = "fake"
    model = "fake-workbench-ask"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.call_count = 0

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.answer,
            finish_reason="stop",
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            raw={"fake": True, "message_count": len(messages), "max_tokens": max_tokens},
        )
