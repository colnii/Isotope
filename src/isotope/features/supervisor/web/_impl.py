"""Local web view for Codex Supervisor dashboard."""

from __future__ import annotations

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from ..notifications.bell_events import default_bell_events_path, read_latest_bell_events
from ..agent_group.codex_chat.api import (
    agent_group_payload,
    apply_chat_decision_payload,
    control_payload as agent_group_control_payload,
    list_agent_groups_payload,
    transcript_payload,
)
from ..desktop_chat import (
    DesktopChatProvider,
    stream_desktop_chat_events,
)
from ..desktop_snapshot import build_desktop_snapshot
from isotope.llm.capacity_calling import CapacityCallingProvider
from isotope.runtime.in_process import InProcessServer
from ..dashboard.html import dashboard_page_html
from ..planner.decision_requests import record_decision_answer
from ..flow import CodexSupervisorFlow, _tmux_capture_pane
from ..planner.goal_planner import plan_supervisor_goals
from ..planner.goal_queue import record_supervisor_goal
from ..state.lane_state import record_lane_prompt
from ..llm_action.llm_summary import (
    SummaryProvider,
    generate_llm_action_decision,
    resolve_summary_provider_from_env,
)
from ..commands.supervisor_action import set_supervisor_action_payload
from isotope.llm.provider import resolve_llm_chat_provider
from ...ask.pool import resolve_workbench_ask_provider_from_env
from ..registry import TmuxBellHookRepair, repair_tmux_bell_hooks, send_to_managed_codex
from ..runner import (
    EXECUTABLE_ADVICE_KINDS,
    EXECUTABLE_ADVICE_TEXT,
    _advice_payload,
)
from isotope.capabilities.runner import CapabilityRunner
from .routes.dashboard import (
    active_goal_dicts_for_codex_home,
    build_dashboard_web_payload,
    decision_answer_dicts,
    decision_request_dicts,
    recent_context_results_for_report,
)
from .routes.desktop import (
    desktop_approval_resolve_id,
    desktop_chat_history,
    desktop_terminal_allowed_commands,
    desktop_terminal_approval_mode,
)
from .routes.agent_groups import (
    agent_group_child_id_from_path,
    agent_group_id_from_path,
    codex_session_id_from_transcript_path,
    parse_agent_group_chat_payload,
    parse_agent_group_control_payload,
    parse_codex_transcript_query,
)
from .routes.agent_workspaces_dispatch import (
    handle_agent_workspace_get,
    handle_agent_workspace_post,
)
from .routes.desktop_artifacts import (
    desktop_screen_artifact_content_id,
    screen_screenshot_artifact_payload,
)
from .routes.goals import write_goal_plan_candidates
from .routes.long_tasks_dispatch import handle_long_task_get, handle_long_task_post
from .routes.service_actions import SERVICE_ACTION_PATHS, run_service_action
from .routes.worker_lifecycle import (
    WORKER_LIFECYCLE_EXECUTE_PATH,
    WorkerLifecycleExecuteError,
    run_worker_lifecycle_execute,
)


CORS_ALLOW_METHODS = "GET, POST, OPTIONS"
CORS_ALLOW_HEADERS = "content-type"


class SupervisorDashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        codex_home: Path,
        limit: int,
        stale_after_seconds: int,
        active_within_seconds: int,
        send_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        lifecycle_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        repair_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        llm_action_provider: SummaryProvider | None = None,
        desktop_chat_provider: DesktopChatProvider | None = None,
        desktop_chat_capacity_provider: CapacityCallingProvider | None = None,
    ) -> None:
        super().__init__(server_address, _DashboardRequestHandler)
        self.codex_home = codex_home
        self.limit = limit
        self.stale_after_seconds = stale_after_seconds
        self.active_within_seconds = active_within_seconds
        self.send_run = send_run
        self.lifecycle_run = lifecycle_run
        self.llm_action_provider = llm_action_provider
        self.desktop_chat_provider = desktop_chat_provider
        self.desktop_chat_capacity_provider = desktop_chat_capacity_provider
        self.bell_events_path = default_bell_events_path(self.codex_home)
        self.bell_hook_repairs: tuple[TmuxBellHookRepair, ...] = repair_tmux_bell_hooks(
            codex_home=self.codex_home,
            run=repair_run,
        )

    def _scan_report(self) -> Any:
        return CodexSupervisorFlow(
            codex_home=self.codex_home,
            tmux_pane_reader=_tmux_capture_pane,
        ).scan(
            limit=self.limit,
            stale_after_seconds=self.stale_after_seconds,
            active_within_seconds=self.active_within_seconds,
        )

    def dashboard_payload(self) -> dict[str, Any]:
        report = self._scan_report()
        return build_dashboard_web_payload(
            report,
            codex_home=self.codex_home,
            workspace_cwd=Path.cwd(),
        )

    def desktop_snapshot_payload(self) -> dict[str, Any]:
        return build_desktop_snapshot(state_root=self.codex_home)

    def desktop_screen_artifact_content_payload(self, artifact_id: str) -> dict[str, Any]:
        return {
            "status": "ok",
            **screen_screenshot_artifact_payload(self.codex_home, artifact_id),
        }

    def resolve_desktop_approval_payload(
        self,
        approval_id: str,
        *,
        resolution: str,
        reason: str,
        resolver: str,
    ) -> dict[str, Any]:
        api = InProcessServer(self.codex_home)
        result = api.resolve_approval(
            approval_id,
            {
                "resolution": resolution,
                "reason": reason,
                "resolver": resolver,
            },
        )
        run_state = result.get("run_state")
        response = {
            "status": "ok",
            "approvalId": approval_id,
            "resolution": resolution,
            "runStatus": getattr(run_state, "status", str(result.get("status", "unknown"))),
            "snapshot": self.desktop_snapshot_payload(),
        }
        read_result = _local_file_read_result_from_resolution(api, result)
        if read_result is not None:
            response["readResult"] = read_result
        return response

    def desktop_chat_provider_or_default(self) -> DesktopChatProvider:
        if self.desktop_chat_provider is not None:
            return self.desktop_chat_provider
        try:
            return resolve_workbench_ask_provider_from_env(
                agent_name="supervisor",
                timeout=int(
                    _env_number(
                        "ISOTOPE_DESKTOP_CHAT_PROVIDER_TIMEOUT_SECONDS",
                        default=6,
                    )
                ),
                allow_codex=False,
            )
        except ValueError as pool_error:
            resolution = resolve_llm_chat_provider()
            if resolution.status == "configured" and resolution.provider is not None:
                return resolution.provider
            raise pool_error

    def desktop_chat_capacity_provider_or_default(self) -> CapacityCallingProvider | None:
        if self.desktop_chat_capacity_provider is not None:
            return self.desktop_chat_capacity_provider
        return None

    def llm_action_payload(self) -> dict[str, Any]:
        report = self._scan_report()
        payload = _advice_payload(report)
        recent_context_results = recent_context_results_for_report(
            codex_home=self.codex_home,
            report=report,
        )
        payload["recent_context_results"] = recent_context_results
        provider = self.llm_action_provider or resolve_summary_provider_from_env(
            agent_name="supervisor"
        )
        set_supervisor_action_payload(
            payload,
            generate_llm_action_decision(
                report,
                payload["command_suggestions"],
                provider,
                recent_context_results,
                None,
                decision_answer_dicts(self.codex_home),
            ),
        )
        return payload

    def bell_event_stamp(self) -> tuple[int, int]:
        try:
            stat = self.bell_events_path.stat()
        except OSError:
            return (0, 0)
        return (stat.st_mtime_ns, stat.st_size)

    def latest_bell_event_payload(self) -> dict[str, Any]:
        events = read_latest_bell_events(self.bell_events_path)
        if not events:
            return {"event": "bell"}
        latest = max(events.values(), key=lambda event: event.created_at)
        return latest.to_dict()


def create_dashboard_server(
    *,
    codex_home: Path | str,
    host: str,
    port: int,
    limit: int,
    stale_after_seconds: int,
    active_within_seconds: int,
    send_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    lifecycle_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    repair_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    llm_action_provider: SummaryProvider | None = None,
    desktop_chat_provider: DesktopChatProvider | None = None,
    desktop_chat_capacity_provider: CapacityCallingProvider | None = None,
) -> SupervisorDashboardServer:
    return SupervisorDashboardServer(
        (host, port),
        codex_home=Path(codex_home),
        limit=limit,
        stale_after_seconds=stale_after_seconds,
        active_within_seconds=active_within_seconds,
        send_run=send_run,
        lifecycle_run=lifecycle_run,
        repair_run=repair_run,
        llm_action_provider=llm_action_provider,
        desktop_chat_provider=desktop_chat_provider,
        desktop_chat_capacity_provider=desktop_chat_capacity_provider,
    )


def _local_file_read_result_from_resolution(
    api: InProcessServer,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    artifact_ref = result.get("artifact_ref")
    if artifact_ref is None:
        return None
    metadata = api.artifact_store.get_metadata(artifact_ref)
    if metadata.get("artifact_type") != "local_file_read":
        return None
    try:
        content = json.loads(api.artifact_store.get_content(artifact_ref))
    except json.JSONDecodeError:
        return None
    if not isinstance(content, dict):
        return None
    return content


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    server: SupervisorDashboardServer

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("access-control-max-age", "600")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            self._send_text(dashboard_page_html(), content_type="text/html; charset=utf-8")
            return
        if path == "/dashboard.json":
            payload = self.server.dashboard_payload()
            self._send_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                content_type="application/json; charset=utf-8",
            )
            return
        if path == "/desktop/snapshot":
            payload = self.server.desktop_snapshot_payload()
            self._send_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                content_type="application/json; charset=utf-8",
            )
            return
        artifact_id = desktop_screen_artifact_content_id(path)
        if artifact_id is not None:
            self._send_desktop_screen_artifact_content(artifact_id)
            return
        if handle_long_task_get(self, path=path):
            return
        if path == "/desktop/agent-groups":
            self._send_json(list_agent_groups_payload(self.server.codex_home))
            return
        if handle_agent_workspace_get(
            self,
            path=path,
            query=parsed.query,
            root_path=Path.cwd(),
        ):
            return
        group_id = agent_group_id_from_path(path)
        if group_id is not None:
            try:
                payload = agent_group_payload(self.server.codex_home, group_id)
            except ValueError as exc:
                self._send_json(
                    {
                        "status": "error",
                        "error": {
                            "code": "codex_supervisor_web_error",
                            "message": str(exc),
                        },
                    },
                    status_code=404,
                )
                return
            self._send_json(payload)
            return
        transcript_session_id = codex_session_id_from_transcript_path(path)
        if transcript_session_id is not None:
            try:
                query = parse_codex_transcript_query(parsed.query)
                payload = transcript_payload(
                    self.server.codex_home,
                    session_id=transcript_session_id,
                    offset=int(query["offset"]),
                    limit=int(query["limit"]),
                    include_raw=bool(query["include_raw"]),
                    latest=bool(query["latest"]),
                )
            except ValueError as exc:
                self._send_json(
                    {
                        "status": "error",
                        "error": {
                            "code": "codex_supervisor_web_error",
                            "message": str(exc),
                        },
                    },
                    status_code=400,
                )
                return
            self._send_json(payload)
            return
        if path == "/events":
            self._send_events()
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/managed/send":
            self._send_managed_command()
            return
        if path == "/llm-action":
            self._send_llm_action()
            return
        if path == "/desktop/chat":
            self._send_desktop_chat()
            return
        if handle_long_task_post(self, path=path):
            return
        if handle_agent_workspace_post(self, path=path):
            return
        chat_group_id = agent_group_child_id_from_path(path, suffix="chat")
        if chat_group_id is not None:
            try:
                payload = parse_agent_group_chat_payload(self._read_json_body())
                result = apply_chat_decision_payload(
                    self.server.codex_home,
                    group_id=chat_group_id,
                    message=payload["message"],
                    mode=payload["mode"],
                )
            except ValueError as exc:
                self._send_json(
                    {
                        "status": "error",
                        "error": {
                            "code": "codex_supervisor_web_error",
                            "message": str(exc),
                        },
                    },
                    status_code=400,
                )
                return
            self._send_json(result)
            return
        control_group_id = agent_group_child_id_from_path(path, suffix="control")
        if control_group_id is not None:
            try:
                payload = parse_agent_group_control_payload(self._read_json_body())
                result = agent_group_control_payload(
                    self.server.codex_home,
                    group_id=control_group_id,
                    intent=str(payload["intent"]),
                    target=str(payload["target"]),
                    target_member_id=payload["target_member_id"],
                    reason=str(payload["reason"]),
                )
            except ValueError as exc:
                self._send_json(
                    {
                        "status": "error",
                        "error": {
                            "code": "codex_supervisor_web_error",
                            "message": str(exc),
                        },
                    },
                    status_code=400,
                )
                return
            self._send_json(result)
            return
        approval_id = desktop_approval_resolve_id(path)
        if approval_id is not None:
            self._send_desktop_approval_resolution(approval_id)
            return
        if path == "/decision/answer":
            self._send_decision_answer()
            return
        if path == "/goal/add":
            self._send_goal_add()
            return
        if path == "/goal/plan":
            self._send_goal_plan()
            return
        if path == WORKER_LIFECYCLE_EXECUTE_PATH:
            self._send_worker_lifecycle_execute()
            return
        if path in SERVICE_ACTION_PATHS:
            self._send_service_action(path)
            return
        self._send_json(
            {
                "status": "error",
                "error": {
                    "code": "codex_supervisor_web_error",
                    "message": "unknown endpoint",
                },
            },
            status_code=404,
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_managed_command(self) -> None:
        try:
            payload = self._read_json_body()
            kind = _required_string(payload.get("kind"), "kind")
            name = _required_string(payload.get("name"), "name")
            if kind not in EXECUTABLE_ADVICE_KINDS:
                supported = ", ".join(sorted(EXECUTABLE_ADVICE_KINDS))
                raise ValueError(f"kind supports only: {supported}")
            result = send_to_managed_codex(
                codex_home=self.server.codex_home,
                name=name,
                text=EXECUTABLE_ADVICE_TEXT[kind],
                run=self.server.send_run,
            )
            lane_state = record_lane_prompt(
                codex_home=self.server.codex_home,
                name=result.record.name,
                tmux_session=result.record.tmux_session,
                status=kind,
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(
            {
                "status": "ok",
                "kind": kind,
                "text": result.text,
                "managed": {
                    "name": result.record.name,
                    "record_id": result.record.record_id,
                    "tmux_session": result.record.tmux_session,
                },
                "lane_state": lane_state.to_dict(),
            }
        )

    def _send_llm_action(self) -> None:
        try:
            self._read_json_body()
            payload = self.server.llm_action_payload()
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(payload)

    def _send_desktop_chat(self) -> None:
        try:
            payload = self._read_json_body()
            question = _required_string(payload.get("question"), "question")
            max_tokens = _positive_int(payload.get("max_tokens"), "max_tokens", default=512)
            history = desktop_chat_history(payload.get("history"))
            workspace_cwd = _workspace_cwd(payload.get("workspace_cwd"))
            terminal_approval_mode = desktop_terminal_approval_mode(
                payload.get("terminal_approval_mode")
            )
            terminal_allowed_commands = desktop_terminal_allowed_commands(
                payload.get("terminal_allowed_commands")
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return

        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self._write_sse("start", {"status": "ok"})
        provider_name = "unknown"
        model_name = "unknown"
        try:
            for event in stream_desktop_chat_events(
                state_root=self.server.codex_home,
                cwd=workspace_cwd,
                question=question,
                provider=self.server.desktop_chat_provider_or_default(),
                capacity_provider=self.server.desktop_chat_capacity_provider_or_default(),
                max_tokens=max_tokens,
                history=history,
                capacity_timeout_seconds=_env_number(
                    "ISOTOPE_DESKTOP_CAPACITY_TIMEOUT_SECONDS",
                    default=4,
                ),
                chat_timeout_seconds=_env_number(
                    "ISOTOPE_DESKTOP_CHAT_TIMEOUT_SECONDS",
                    default=18,
                ),
                terminal_approval_mode=terminal_approval_mode,
                terminal_allowed_commands=terminal_allowed_commands,
            ):
                if event.event == "delta":
                    provider_name = event.provider
                    model_name = event.model
                self._write_sse(event.event, event.payload)
        except Exception as exc:  # noqa: BLE001 - stream should surface backend failure.
            self._write_sse(
                "error",
                {
                    "status": "error",
                    "message": str(exc) or type(exc).__name__,
                    "error_type": type(exc).__name__,
                },
            )
            return
        self._write_sse(
            "done",
            {
                "status": "ok",
                "provider": provider_name,
                "model": model_name,
            },
        )

    def _send_desktop_approval_resolution(self, approval_id: str) -> None:
        try:
            payload = self._read_json_body()
            resolution = _required_string(payload.get("resolution"), "resolution")
            if resolution not in {"approved", "denied"}:
                raise ValueError("resolution must be approved or denied")
            reason = _optional_string(payload.get("reason")) or (
                "desktop operator approved" if resolution == "approved" else "desktop operator denied"
            )
            resolver = _optional_string(payload.get("resolver")) or "desktop_frontend"
            result = self.server.resolve_desktop_approval_payload(
                approval_id,
                resolution=resolution,
                reason=reason,
                resolver=resolver,
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(result)

    def _send_desktop_screen_artifact_content(self, artifact_id: str) -> None:
        try:
            payload = self.server.desktop_screen_artifact_content_payload(artifact_id)
        except FileNotFoundError:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "artifact_not_found",
                        "message": "screen artifact not found",
                    },
                },
                status_code=404,
            )
            return
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "screen_artifact_unavailable",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(payload)

    def _send_goal_plan(self) -> None:
        try:
            payload = self._read_json_body()
            write = bool(payload.get("write"))
            if write and isinstance(payload.get("candidates"), list):
                planned = write_goal_plan_candidates(
                    codex_home=self.server.codex_home,
                    payload=payload,
                )
            else:
                planned = _run_goal_plan_capacity(
                    codex_home=self.server.codex_home,
                    goal=_required_string(payload.get("goal"), "goal"),
                    write=write,
                    limit=_positive_int(payload.get("limit"), "limit", default=3),
                    provider=self.server.llm_action_provider,
                )
            planned["active_goals"] = active_goal_dicts_for_codex_home(
                self.server.codex_home,
                include_status=True,
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(planned)

    def _send_decision_answer(self) -> None:
        try:
            payload = self._read_json_body()
            request_id = _required_string(payload.get("request_id"), "request_id")
            answer = _required_string(payload.get("answer"), "answer")
            answered = record_decision_answer(
                codex_home=self.server.codex_home,
                request_id=request_id,
                answer=answer,
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(
            {
                "status": "ok",
                "answered": answered,
                "decision_requests": decision_request_dicts(self.server.codex_home),
                "recent_decision_answers": decision_answer_dicts(self.server.codex_home),
            }
        )

    def _send_goal_add(self) -> None:
        try:
            payload = self._read_json_body()
            goal = record_supervisor_goal(
                codex_home=self.server.codex_home,
                cwd=Path.cwd(),
                goal=_required_string(payload.get("goal"), "goal"),
                target_name=_optional_string(payload.get("target_name")),
            )
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(
            {
                "status": "ok",
                "goal": goal.to_dict(),
                "active_goals": active_goal_dicts_for_codex_home(
                    self.server.codex_home,
                    include_status=True,
                ),
            }
        )

    def _send_service_action(self, path: str) -> None:
        try:
            self._read_json_body()
            result = run_service_action(self.server, path)
        except ValueError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": "codex_supervisor_web_error",
                        "message": str(exc),
                    },
                },
                status_code=400,
            )
            return
        self._send_json(
            {
                "status": "ok",
                "target": result["target"],
                "action": result["action"],
                "service": result["service"],
            }
        )

    def _send_worker_lifecycle_execute(self) -> None:
        try:
            payload = self._read_json_body()
            result = run_worker_lifecycle_execute(self.server, payload)
        except WorkerLifecycleExecuteError as exc:
            self._send_json(
                {
                    "status": "error",
                    "error": {
                        "code": exc.code,
                        "message": str(exc),
                    },
                },
                status_code=exc.status_code,
            )
            return
        self._send_json(result)

    def _send_events(self) -> None:
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("connection", "keep-alive")
        self._send_cors_headers()
        self.end_headers()
        previous_stamp = self.server.bell_event_stamp()
        self._write_sse("ready", {"status": "ok"})
        last_heartbeat = time.monotonic()
        while True:
            time.sleep(0.25)
            if time.monotonic() - last_heartbeat >= 15:
                try:
                    self._write_sse("heartbeat", {"status": "ok"})
                except OSError:
                    return
                last_heartbeat = time.monotonic()
            current_stamp = self.server.bell_event_stamp()
            if current_stamp == previous_stamp:
                continue
            previous_stamp = current_stamp
            try:
                self._write_sse("bell", self.server.latest_bell_event_payload())
            except OSError:
                return

    def _write_sse(self, event: str, payload: dict[str, Any]) -> None:
        body = (
            f"event: {event}\n"
            + "data: "
            + json.dumps(payload, ensure_ascii=False, sort_keys=True)
            + "\n\n"
        ).encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_text(self, text: str, *, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", CORS_ALLOW_METHODS)
        self.send_header("access-control-allow-headers", CORS_ALLOW_HEADERS)


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value.strip()


def _env_number(name: str, *, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _workspace_cwd(value: object) -> Path:
    if value is None:
        return Path.cwd()
    text = _required_string(value, "workspace_cwd")
    path = Path(text).expanduser()
    if not path.is_dir():
        raise ValueError("workspace_cwd must be an existing directory")
    return path


def _positive_int(value: object, field: str, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return number


def _run_goal_plan_capacity(
    *,
    codex_home: Path,
    goal: str,
    write: bool,
    limit: int,
    provider: SummaryProvider | None,
) -> dict[str, Any]:
    if provider is not None:
        return plan_supervisor_goals(
            root=Path.cwd(),
            codex_home=codex_home,
            provider=provider,
            user_goal=goal,
            write=write,
            limit=limit,
            planning_trigger="capacity",
        )
    result = CapabilityRunner().run_capability(
        "supervisor.goal_plan",
        inputs={
            "state_root": str(codex_home),
            "cwd": str(Path.cwd()),
            "goal": goal,
            "limit": limit,
            "write": write,
        },
    )
    planned = result.get("goal_plan")
    if not isinstance(planned, dict):
        raise ValueError("supervisor.goal_plan did not return a goal_plan payload")
    return dict(planned)
