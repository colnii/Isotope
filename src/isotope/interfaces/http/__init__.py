"""In-process HTTP API boundary for the v0.2 minimal surface.

This module is a test-client style facade. It does not open sockets and does
not commit the project to a web framework.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...core import ProductCore
from ...features.ask.flow import AskProvider, WorkbenchAskFlow
from ...features.files.flow import FileFlow
from ...features.projects.flow import ProjectFlow
from ...features.projects.workspace import ProjectWorkspaceFlow
from ...features.search.flow import SearchFlow
from ...features.tasks.flow import TaskFlow
from ...features.workbench.flow import WorkbenchFlow
from ...runtime.in_process import InProcessServer
from .dispatch import HttpDispatchMixin
from .responses import HttpResponseMixin
from .routes import HttpRouteMixin
from .serialization import HttpSerializationMixin
from .types import HttpResponse
from .validation import HttpValidationMixin


class HttpApiApp(
    HttpDispatchMixin,
    HttpResponseMixin,
    HttpRouteMixin,
    HttpSerializationMixin,
    HttpValidationMixin,
):
    """Minimal in-process HTTP-like app for the kernel runtime boundary."""

    def __init__(
        self,
        root_path: Path | str,
        *,
        allow_artifact_content: bool = False,
        artifact_content_retrieval_service: Any | None = None,
        server: InProcessServer | None = None,
        enable_codex_task_route: bool = False,
        enable_llm_provider_route: bool = False,
        enable_llm_product_chat_route: bool = False,
        llm_tool_call_provider: Any | None = None,
        llm_tool_names: tuple[str, ...] = ("codex_task",),
        workbench_ask_provider: AskProvider | None = None,
    ):
        self.root_path = Path(root_path)
        self.server = server if server is not None else InProcessServer(self.root_path)
        self.allow_artifact_content = allow_artifact_content
        self.artifact_content_retrieval_service = artifact_content_retrieval_service
        self.enable_codex_task_route = enable_codex_task_route
        self.enable_llm_provider_route = enable_llm_provider_route
        self.enable_llm_product_chat_route = enable_llm_product_chat_route
        self.llm_tool_call_provider = llm_tool_call_provider
        self.llm_tool_names = self._validate_llm_tool_names(llm_tool_names)
        self.workbench_ask_provider = workbench_ask_provider
        product_core = ProductCore(self.server)
        self.task_flow = TaskFlow(product_core)
        self.file_flow = FileFlow(product_core)
        self.project_flow = ProjectFlow(product_core)
        self.project_workspace_flow = ProjectWorkspaceFlow(product_core)
        self.search_flow = SearchFlow(product_core)
        self.workbench_flow = WorkbenchFlow(product_core)
        self.workbench_ask_flow = (
            WorkbenchAskFlow(product_core, provider=workbench_ask_provider)
            if workbench_ask_provider is not None
            else None
        )
        self._idempotency_cache: dict[str, dict[str, Any]] = {}

    def routes(self) -> list[tuple[str, str]]:
        return list(self._active_routes())

    def list_routes(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "routes": [
                {
                    "method": method,
                    "path": route,
                    "status": "supported",
                }
                for method, route in self._active_routes()
            ],
        }

    def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> HttpResponse:
        method = method.upper()
        try:
            idempotency_key = self._extract_idempotency_key(json)
        except ValueError as exc:
            return self._error(400, "bad_request", str(exc))

        body_fingerprint = self._body_fingerprint(json) if idempotency_key is not None else None
        if idempotency_key is not None:
            replay_or_conflict = self._idempotency_replay_or_conflict(
                idempotency_key,
                method,
                path,
                body_fingerprint,
            )
            if replay_or_conflict is not None:
                return replay_or_conflict

        response = self._dispatch_request(method, path, json)
        if idempotency_key is not None and 200 <= response.status_code < 300:
            self._idempotency_cache[idempotency_key] = {
                "method": method,
                "path": path,
                "body_fingerprint": body_fingerprint,
                "response": self._copy_response(response),
            }
        return response


def create_http_app(
    root_path: Path | str,
    *,
    allow_artifact_content: bool = False,
    artifact_content_retrieval_service: Any | None = None,
    workbench_ask_provider: AskProvider | None = None,
) -> HttpApiApp:
    return HttpApiApp(
        root_path=root_path,
        allow_artifact_content=allow_artifact_content,
        artifact_content_retrieval_service=artifact_content_retrieval_service,
        workbench_ask_provider=workbench_ask_provider,
    )


def create_codex_cli_http_app(
    root_path: Path | str,
    *,
    config,
    checkpoint_store: Any | None = None,
    process_runner: Any | None = None,
    executable_resolver: Any | None = None,
) -> HttpApiApp:
    from ...integrations.codex.server import create_codex_cli_server

    kwargs: dict[str, Any] = {}
    if process_runner is not None:
        kwargs["process_runner"] = process_runner
    if executable_resolver is not None:
        kwargs["executable_resolver"] = executable_resolver
    server = create_codex_cli_server(
        root_path,
        config=config,
        checkpoint_store=checkpoint_store,
        **kwargs,
    )
    return HttpApiApp(
        root_path=root_path,
        server=server,
        enable_codex_task_route=True,
    )


def create_llm_provider_http_app(
    root_path: Path | str,
    *,
    config,
    provider: Any,
    checkpoint_store: Any | None = None,
    process_runner: Any | None = None,
    executable_resolver: Any | None = None,
    tool_names: tuple[str, ...] = ("codex_task",),
) -> HttpApiApp:
    from ...integrations.codex.server import create_codex_cli_server

    kwargs: dict[str, Any] = {}
    if process_runner is not None:
        kwargs["process_runner"] = process_runner
    if executable_resolver is not None:
        kwargs["executable_resolver"] = executable_resolver
    server = create_codex_cli_server(
        root_path,
        config=config,
        checkpoint_store=checkpoint_store,
        **kwargs,
    )
    return HttpApiApp(
        root_path=root_path,
        server=server,
        enable_codex_task_route=True,
        enable_llm_provider_route=True,
        llm_tool_call_provider=provider,
        llm_tool_names=tool_names,
    )


def create_llm_product_chat_http_app(
    root_path: Path | str,
    *,
    config,
    provider: Any,
    checkpoint_store: Any | None = None,
    process_runner: Any | None = None,
    executable_resolver: Any | None = None,
    tool_names: tuple[str, ...] = ("codex_task",),
) -> HttpApiApp:
    from ...integrations.codex.server import create_codex_cli_server

    kwargs: dict[str, Any] = {}
    if process_runner is not None:
        kwargs["process_runner"] = process_runner
    if executable_resolver is not None:
        kwargs["executable_resolver"] = executable_resolver
    server = create_codex_cli_server(
        root_path,
        config=config,
        checkpoint_store=checkpoint_store,
        **kwargs,
    )
    return HttpApiApp(
        root_path=root_path,
        server=server,
        enable_codex_task_route=True,
        enable_llm_product_chat_route=True,
        llm_tool_call_provider=provider,
        llm_tool_names=tool_names,
    )
