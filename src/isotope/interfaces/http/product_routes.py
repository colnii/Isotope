"""Product-flow route handlers for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from .types import HttpResponse


class HttpProductRouteMixin:
    """Handle task, file, project, search, and workbench routes."""

    def _dispatch_product_route(
        self,
        method: str,
        parts: list[str],
        json_body: dict[str, Any] | None,
    ) -> HttpResponse | None:
        if method == "GET" and parts == ["routes"]:
            return self._json(200, self.list_routes())
        if method == "GET" and parts == ["health"]:
            return self._json(200, {"status": "ok"})
        if method == "POST" and parts == ["tasks"]:
            body = self._require_body(json_body, required_fields=("goal", "message"))
            summary = self.task_flow.create_task(
                goal=body["goal"],
                first_message=body["message"],
            )
            return self._json(201, {"status": "ok", "task": self._task_summary_to_dict(summary)})
        if method == "GET" and parts == ["tasks"]:
            summaries = [
                self._task_summary_to_dict(summary)
                for summary in self.task_flow.list_tasks()
            ]
            return self._json(200, {"status": "ok", "tasks": summaries})
        if method == "GET" and len(parts) == 2 and parts[0] == "tasks":
            try:
                summary = self.task_flow.get_task(parts[1])
            except ValueError as exc:
                if "unknown task_id" in str(exc):
                    return self._error(404, "not_found", "task not found")
                raise
            return self._json(200, {"status": "ok", "task": self._task_summary_to_dict(summary)})
        if method == "POST" and parts == ["files"]:
            body = self._require_body(json_body, required_fields=("name", "summary", "content"))
            summary = self.file_flow.create_text_file(
                name=body["name"],
                summary=body["summary"],
                content=body["content"],
            )
            return self._json(201, {"status": "ok", "file": self._file_summary_to_dict(summary)})
        if method == "GET" and parts == ["files"]:
            summaries = [
                self._file_summary_to_dict(summary)
                for summary in self.file_flow.list_files()
            ]
            return self._json(200, {"status": "ok", "files": summaries})
        if method == "GET" and len(parts) == 2 and parts[0] == "files":
            try:
                summary = self.file_flow.get_file(parts[1])
            except ValueError as exc:
                if "unknown file_id" in str(exc):
                    return self._error(404, "not_found", "file not found")
                raise
            return self._json(200, {"status": "ok", "file": self._file_summary_to_dict(summary)})
        if method == "POST" and parts == ["projects"]:
            body = self._require_body(json_body, required_fields=("name", "summary"))
            summary = self.project_flow.create_project(
                name=body["name"],
                summary=body["summary"],
            )
            return self._json(201, {"status": "ok", "project": self._project_summary_to_dict(summary)})
        if method == "POST" and parts == ["projects", "workspace"]:
            body = self._require_body(
                json_body,
                required_fields=(
                    "project_name",
                    "project_summary",
                    "task_goal",
                    "task_message",
                    "file_name",
                    "file_summary",
                    "file_content",
                ),
            )
            workspace = self.project_workspace_flow.create_workspace(
                project_name=body["project_name"],
                project_summary=body["project_summary"],
                task_goal=body["task_goal"],
                task_message=body["task_message"],
                file_name=body["file_name"],
                file_summary=body["file_summary"],
                file_content=body["file_content"],
                search_query=json_body.get("search_query"),
            )
            return self._json(
                201,
                {
                    "status": "ok",
                    "workspace": self._project_workspace_to_dict(workspace),
                },
            )
        if method == "GET" and parts == ["projects"]:
            summaries = [
                self._project_summary_to_dict(summary)
                for summary in self.project_flow.list_projects()
            ]
            return self._json(200, {"status": "ok", "projects": summaries})
        if method == "GET" and len(parts) == 2 and parts[0] == "projects":
            try:
                summary = self.project_flow.get_project(parts[1])
            except ValueError as exc:
                if "unknown project_id" in str(exc):
                    return self._error(404, "not_found", "project not found")
                raise
            return self._json(200, {"status": "ok", "project": self._project_summary_to_dict(summary)})
        if method == "GET" and len(parts) == 3 and parts[0] == "projects" and parts[2] == "detail":
            try:
                detail = self.project_flow.get_project_detail(parts[1])
            except ValueError as exc:
                if "unknown project_id" in str(exc):
                    return self._error(404, "not_found", "project not found")
                raise
            return self._json(
                200,
                {
                    "status": "ok",
                    "project_detail": self._project_detail_to_dict(detail),
                },
            )
        if method == "POST" and len(parts) == 3 and parts[0] == "projects" and parts[2] == "workspace":
            body = self._require_body(
                json_body,
                required_fields=(
                    "task_goal",
                    "task_message",
                    "file_name",
                    "file_summary",
                    "file_content",
                ),
            )
            workspace = self.project_workspace_flow.append_to_project(
                parts[1],
                task_goal=body["task_goal"],
                task_message=body["task_message"],
                file_name=body["file_name"],
                file_summary=body["file_summary"],
                file_content=body["file_content"],
                search_query=json_body.get("search_query") if json_body is not None else None,
            )
            return self._json(
                200,
                {
                    "status": "ok",
                    "workspace": self._project_workspace_to_dict(workspace),
                },
            )
        if method == "POST" and len(parts) == 3 and parts[0] == "projects" and parts[2] == "tasks":
            body = self._require_body(json_body, required_fields=("task_id",))
            summary = self.project_flow.add_task(parts[1], body["task_id"])
            return self._json(200, {"status": "ok", "project": self._project_summary_to_dict(summary)})
        if method == "POST" and len(parts) == 3 and parts[0] == "projects" and parts[2] == "files":
            body = self._require_body(json_body, required_fields=("file_id",))
            summary = self.project_flow.add_file(parts[1], body["file_id"])
            return self._json(200, {"status": "ok", "project": self._project_summary_to_dict(summary)})
        if method == "POST" and parts == ["search"]:
            body = self._require_body(json_body, required_fields=("query",))
            search_options = self._search_options(json_body)
            results = [
                self._search_result_to_dict(result)
                for result in self.search_flow.search(
                    body["query"],
                    result_types=search_options["result_types"],
                    limit=search_options["limit"],
                )
            ]
            return self._json(200, {"status": "ok", "results": results})
        if method == "GET" and parts == ["workbench"]:
            view = self.workbench_flow.summary()
            return self._json(200, {"status": "ok", "workbench": self._workbench_view_to_dict(view)})
        if method == "POST" and parts == ["workbench"]:
            workbench_options = self._workbench_options(json_body)
            view = self.workbench_flow.summary(
                query=workbench_options["query"],
                search_types=workbench_options["search_types"],
                search_limit=workbench_options["search_limit"],
            )
            return self._json(200, {"status": "ok", "workbench": self._workbench_view_to_dict(view)})
        if method == "POST" and parts == ["workbench", "ask"]:
            if self.workbench_ask_flow is None:
                return self._error(
                    501,
                    "not_enabled",
                    "workbench_ask is not enabled",
                    capability="workbench_ask",
                )
            ask_options = self._workbench_ask_options(json_body)
            answer = self.workbench_ask_flow.answer(
                ask_options["question"],
                search_limit=ask_options["search_limit"],
                max_tokens=ask_options["max_tokens"],
            )
            return self._json(
                200,
                {"status": "ok", "answer": self._workbench_ask_answer_to_dict(answer)},
            )
        return None
