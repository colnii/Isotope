"""Request dispatch for the in-process HTTP facade."""

from __future__ import annotations

from typing import Any

from ..platform.errors import IsotopeError
from .http_types import HttpResponse


class HttpDispatchMixin:
    """Dispatch supported HTTP-like requests to product flows and runtime calls."""

    def _dispatch_request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
    ) -> HttpResponse:
        parts = self._split_path(path)
        allowed_methods = self._allowed_methods(parts) if parts else set()

        if parts and allowed_methods and method not in allowed_methods:
            return self._error(
                405,
                "method_not_allowed",
                "method not allowed",
                allowed_methods=sorted(allowed_methods),
            )

        if method == "GET" and self._route_matches("/artifacts/{artifact_id}/content", parts):
            return self._artifact_content_guard()

        deferred_capability = self._deferred_capability(method, parts)
        if deferred_capability is not None:
            return self._error(
                501,
                "not_enabled",
                f"{deferred_capability} is not enabled",
                capability=deferred_capability,
            )

        try:
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
            if method == "POST" and parts == ["sessions"]:
                return self._json(201, self.server.create_session())
            if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "runs":
                body = self._require_body(json_body, required_fields=("goal",))
                if parts[1] not in self.server._sessions:
                    return self._isotope_error_response(
                        IsotopeError(
                            "session not found",
                            code="unknown_session",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"session_id": parts[1]},
                        )
                    )
                return self._json(
                    201,
                    self.server.create_run(parts[1], goal=body["goal"]),
                )
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "input":
                body = self._require_body(json_body, required_fields=("text",))
                if not self._run_exists(parts[1]):
                    return self._isotope_error_response(
                        IsotopeError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                requires_approval = False
                if isinstance(json_body, dict):
                    requires_approval = json_body.get("requires_approval", False)
                result = self.server.submit_input(
                    parts[1],
                    text=body["text"],
                    requires_approval=requires_approval,
                )
                return self._json(200, self._submit_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-step"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self.server.run_agent_loop_step(parts[1], json_body))
            if (
                method == "POST"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-planner-step"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self.server.run_agent_loop_planner_step(parts[1], json_body))
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "codex-tasks":
                if not self._run_exists(parts[1]):
                    return self._isotope_error_response(
                        IsotopeError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                body = self._require_body(json_body, required_fields=("prompt",))
                intent = {
                    "action": "delegate_agent_task",
                    "tool": "codex_task",
                    "prompt": body["prompt"],
                    "summary": self._optional_summary(json_body),
                }
                result = self.server.submit_action(
                    parts[1],
                    intent,
                    requires_approval=True,
                    complete_run=self._optional_complete_run(json_body),
                )
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._submit_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "llm"
                and parts[3] == "tool-calls"
            ):
                if not self._run_exists(parts[1]):
                    return self._isotope_error_response(
                        IsotopeError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                if self.llm_tool_call_provider is None:
                    return self._error(
                        501,
                        "not_enabled",
                        "llm_provider_tool_call is not enabled",
                        capability="llm_provider_tool_call",
                    )
                body = self._require_llm_provider_body(json_body)
                from ..llm.provider import submit_llm_tool_call

                result = submit_llm_tool_call(
                    self,
                    parts[1],
                    self.llm_tool_call_provider,
                    body["messages"],
                    max_tokens=body["max_tokens"],
                    tool_names=self.llm_tool_names,
                    complete_run=body["complete_run"],
                )
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._llm_provider_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "llm"
                and parts[3] == "tool-result-followups"
            ):
                if not self._run_exists(parts[1]):
                    return self._isotope_error_response(
                        IsotopeError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                if self.llm_tool_call_provider is None:
                    return self._error(
                        501,
                        "not_enabled",
                        "llm_provider_tool_result_followup is not enabled",
                        capability="llm_provider_tool_result_followup",
                    )
                body = self._require_llm_tool_result_followup_body(json_body)
                from ..llm.provider import submit_llm_tool_result_followup

                result = submit_llm_tool_result_followup(
                    self,
                    parts[1],
                    self.llm_tool_call_provider,
                    body["messages"],
                    body["llm_result"],
                    body["tool_execution_result"],
                    max_tokens=body["max_tokens"],
                    tool_names=self.llm_tool_names,
                    complete_run=body["complete_run"],
                )
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._llm_provider_result_to_dict(result))
            if (
                method == "POST"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "llm"
                and parts[3] == "chat-turns"
            ):
                if not self._run_exists(parts[1]):
                    return self._isotope_error_response(
                        IsotopeError(
                            "run not found",
                            code="unknown_run",
                            category="not_found",
                            retryable=False,
                            http_status=404,
                            details={"run_id": parts[1]},
                        )
                    )
                if self.llm_tool_call_provider is None:
                    return self._error(
                        501,
                        "not_enabled",
                        "llm_product_chat_route is not enabled",
                        capability="llm_product_chat_route",
                    )
                body = self._require_llm_product_chat_body(json_body)
                from ..llm.provider import submit_llm_chat_turn

                result = submit_llm_chat_turn(
                    self,
                    parts[1],
                    self.llm_tool_call_provider,
                    body["messages"],
                    body.get("llm_result"),
                    body.get("tool_execution_result"),
                    max_tokens=body["max_tokens"],
                    tool_names=self.llm_tool_names,
                    complete_run=body["complete_run"],
                )
                result["turn_kind"] = body["turn_kind"]
                status_code = 202 if result["status"] == "pending_user_approval" else 200
                return self._json(status_code, self._llm_product_chat_result_to_dict(result))
            if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "approvals":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(
                    200,
                    {
                        "status": "ok",
                        "pending_approvals": self.server.get_pending_approvals(parts[1]),
                    },
                )
            if (
                method == "GET"
                and len(parts) == 4
                and parts[0] == "runs"
                and parts[2] == "approvals"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                try:
                    approval = self.server.get_approval(parts[1], parts[3])
                except ValueError as exc:
                    if "unknown approval" in str(exc):
                        return self._error(404, "not_found", "approval not found")
                    raise
                return self._json(200, {"status": "ok", "approval": approval})
            if (
                method == "POST"
                and len(parts) == 5
                and parts[0] == "runs"
                and parts[2] == "approvals"
                and parts[4] == "resolve"
            ):
                if not self._approval_known_for_run(parts[3], parts[1]):
                    return self._error(404, "not_found", "approval not found")
                result = self.server.resolve_approval(parts[3], json_body)
                if result.get("run_state") is not None and result["run_state"].run_id != parts[1]:
                    return self._error(404, "not_found", "approval not found")
                return self._json(200, self._submit_result_to_dict(result))
            if method == "GET" and len(parts) == 2 and parts[0] == "runs":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self._run_state_to_dict(self.server.get_run_state(parts[1])))
            if (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-control"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, self.server.get_agent_loop_control(parts[1]))
            if (
                method == "GET"
                and len(parts) == 3
                and parts[0] == "runs"
                and parts[2] == "agent-loop-tick-policy"
            ):
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                controls = self._agent_loop_tick_policy_controls(json_body)
                return self._json(200, self.server.get_agent_loop_tick_policy(parts[1], **controls))
            if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "events":
                if not self._run_exists(parts[1]):
                    return self._error(404, "not_found", "run not found")
                return self._json(200, [event.to_dict() for event in self.server.get_events(parts[1])])
            if method == "GET" and len(parts) == 3 and parts[0] == "artifacts" and parts[2] == "summary":
                summary = self._find_artifact_summary(parts[1])
                if summary is None:
                    return self._error(404, "not_found", "artifact not found")
                return self._json(200, summary)
        except PermissionError as exc:
            return self._error(403, "forbidden", str(exc))
        except IsotopeError as exc:
            return self._isotope_error_response(exc)
        except (FileNotFoundError, ValueError) as exc:
            message = str(exc)
            if "unknown approval" in message:
                return self._error(404, "not_found", "approval not found")
            if "already resolved" in message or "conflict" in message:
                return self._error(409, "approval_already_resolved", message)
            return self._error(400, "bad_request", str(exc))

        return self._error(404, "not_found", "route not found")

    def _artifact_content_guard(self) -> HttpResponse:
        if not self.allow_artifact_content:
            return self._content_not_enabled()
        if self.artifact_content_retrieval_service is None:
            return self._content_not_enabled()

        # The explicit enablement guard exists before opening the route. A later
        # slice must wire RetrievalService.get_artifact_content(...) and its
        # ResourceRef / grants / caller_context / purpose checks here.
        return self._content_not_enabled()

    def _content_not_enabled(self) -> HttpResponse:
        return self._error(
            501,
            "not_enabled",
            "artifact_content is not enabled",
            capability="artifact_content",
        )
