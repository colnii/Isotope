"""Route inventory and matching helpers for the in-process HTTP facade."""

from __future__ import annotations


class HttpRouteMixin:
    """Declare supported and deferred route surfaces."""

    """Minimal in-process HTTP-like app for the kernel runtime boundary."""

    _ROUTES: tuple[tuple[str, str], ...] = (
        ("GET", "/health"),
        ("POST", "/tasks"),
        ("GET", "/tasks"),
        ("GET", "/tasks/{task_id}"),
        ("POST", "/files"),
        ("GET", "/files"),
        ("GET", "/files/{file_id}"),
        ("POST", "/projects"),
        ("GET", "/projects"),
        ("GET", "/projects/{project_id}"),
        ("GET", "/projects/{project_id}/detail"),
        ("POST", "/projects/workspace"),
        ("POST", "/projects/{project_id}/workspace"),
        ("POST", "/projects/{project_id}/tasks"),
        ("POST", "/projects/{project_id}/files"),
        ("POST", "/search"),
        ("GET", "/workbench"),
        ("POST", "/workbench"),
        ("POST", "/workbench/ask"),
        ("POST", "/sessions"),
        ("POST", "/sessions/{session_id}/runs"),
        ("POST", "/runs/{run_id}/input"),
        ("POST", "/runs/{run_id}/agent-loop-step"),
        ("POST", "/runs/{run_id}/agent-loop-planner-step"),
        ("POST", "/runs/{run_id}/agent-loop-tick"),
        ("GET", "/runs/{run_id}"),
        ("GET", "/runs/{run_id}/agent-loop-control"),
        ("GET", "/runs/{run_id}/agent-loop-tick-policy"),
        ("GET", "/runs/{run_id}/events"),
        ("GET", "/artifacts/{artifact_id}/summary"),
    )
    _CODEX_TASK_ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/runs/{run_id}/codex-tasks"),
    )
    _LLM_PROVIDER_ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/tool-calls"),
        ("POST", "/runs/{run_id}/llm/tool-result-followups"),
    )
    _LLM_PRODUCT_CHAT_ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/chat-turns"),
    )
    _DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/memory/query", "memory_query"),
        ("POST", "/external-ingestion", "external_ingestion"),
        ("GET", "/runs/{run_id}/events/stream", "sse_stream"),
        ("POST", "/runs/{run_id}/approvals", "approval_api"),
        ("GET", "/artifacts/{artifact_id}/content", "artifact_content"),
    )
    _CODEX_TASK_DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/codex-tasks", "codex_task"),
    )
    _LLM_PROVIDER_DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/tool-calls", "llm_provider_tool_call"),
        (
            "POST",
            "/runs/{run_id}/llm/tool-result-followups",
            "llm_provider_tool_result_followup",
        ),
    )
    _LLM_PRODUCT_CHAT_DEFERRED_ROUTES: tuple[tuple[str, str, str], ...] = (
        ("POST", "/runs/{run_id}/llm/chat-turns", "llm_product_chat_route"),
    )

    def _deferred_capability(self, method: str, parts: list[str]) -> str | None:
        for deferred_method, route, capability in self._deferred_routes():
            if method == deferred_method and self._route_matches(route, parts):
                return capability
        return None

    def _active_routes(self) -> tuple[tuple[str, str], ...]:
        routes = self._ROUTES
        if self.enable_codex_task_route:
            routes += self._CODEX_TASK_ROUTES
        if self.enable_llm_provider_route:
            routes += self._LLM_PROVIDER_ROUTES
        if self.enable_llm_product_chat_route:
            routes += self._LLM_PRODUCT_CHAT_ROUTES
        return routes

    def _deferred_routes(self) -> tuple[tuple[str, str, str], ...]:
        routes = self._DEFERRED_ROUTES
        if not self.enable_codex_task_route:
            routes += self._CODEX_TASK_DEFERRED_ROUTES
        if not self.enable_llm_provider_route:
            routes += self._LLM_PROVIDER_DEFERRED_ROUTES
        if not self.enable_llm_product_chat_route:
            routes += self._LLM_PRODUCT_CHAT_DEFERRED_ROUTES
        return routes


    def _split_path(self, path: str) -> list[str]:
        if not isinstance(path, str) or not path.startswith("/"):
            return []
        return [part for part in path.split("/") if part]

    def _allowed_methods(self, parts: list[str]) -> set[str]:
        methods: set[str] = set()
        for method, route in self._active_routes():
            if self._route_matches(route, parts):
                methods.add(method)
        return methods

    def _route_matches(self, route: str, parts: list[str]) -> bool:
        route_parts = self._split_path(route)
        if len(route_parts) != len(parts):
            return False
        return all(
            expected == actual or (expected.startswith("{") and expected.endswith("}"))
            for expected, actual in zip(route_parts, parts, strict=True)
        )
