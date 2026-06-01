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

from .notifications.bell_events import default_bell_events_path, read_latest_bell_events
from .notifications.context import read_recent_context_results
from .desktop_chat import (
    DesktopChatProvider,
    stream_desktop_chat_events,
)
from .desktop_snapshot import build_desktop_snapshot
from isotope.llm.capacity_calling import CapacityCallingProvider
from .dashboard.html import dashboard_page_html
from .planner.decision_requests import (
    DEFAULT_DECISION_TIMEOUT_SECONDS,
    read_active_decision_requests,
    read_recent_decision_answers,
    record_decision_answer,
)
from .daemon import (
    start_supervisor_daemon,
    start_supervisor_watcher,
    stop_supervisor_daemon,
    stop_supervisor_watcher,
    supervisor_daemon_status,
    supervisor_watcher_status,
)
from .state.fanout import DEFAULT_FANOUT_LIMIT
from .flow import CodexSupervisorFlow, _tmux_capture_pane
from .planner.goal_planner import plan_supervisor_goals
from .planner.goal_queue import record_supervisor_goal
from .state.lane_state import (
    DEFAULT_MAX_CONTINUE_COUNT,
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
    record_lane_prompt,
)
from .llm_action.llm_summary import (
    SummaryProvider,
    generate_llm_action_decision,
    resolve_summary_provider_from_env,
)
from isotope.llm.provider import resolve_llm_chat_provider
from ..ask.pool import resolve_workbench_ask_provider_from_env
from .registry import TmuxBellHookRepair, repair_tmux_bell_hooks, send_to_managed_codex
from .state.multi_worker import build_multi_worker_status_payload
from .runner import (
    EXECUTABLE_ADVICE_KINDS,
    EXECUTABLE_ADVICE_TEXT,
    DEFAULT_MAX_CONTEXT_REQUESTS,
    DEFAULT_MAX_FAILURE_RETRIES,
    DEFAULT_MAX_RUN_MINUTES,
    DEFAULT_WORKER_CODEX_CONFIG,
    DEFAULT_WORKER_CODEX_MODEL,
    _advice_payload,
    _dashboard_payload,
)
from .state.projection import build_supervisor_state_snapshot


SERVICE_ACTION_PATHS = {"/daemon/start", "/daemon/stop", "/watcher/start", "/watcher/stop"}
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
        return build_desktop_snapshot(codex_home=self.codex_home)

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
        recent_context_results = _recent_context_results_for_report(
            codex_home=self.codex_home,
            report=report,
        )
        payload["recent_context_results"] = recent_context_results
        provider = self.llm_action_provider or resolve_summary_provider_from_env(
            agent_name="supervisor"
        )
        payload["llm_action"] = generate_llm_action_decision(
            report,
            payload["command_suggestions"],
            provider,
            recent_context_results,
            None,
            _decision_answer_dicts(self.codex_home),
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
        repair_run=repair_run,
        llm_action_provider=llm_action_provider,
        desktop_chat_provider=desktop_chat_provider,
        desktop_chat_capacity_provider=desktop_chat_capacity_provider,
    )


def build_dashboard_web_payload(
    report: Any,
    *,
    codex_home: Path,
    workspace_cwd: Path,
    state_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the `/dashboard.json` payload used by the local web page."""
    if state_snapshot is None:
        state_snapshot = build_supervisor_state_snapshot(codex_home=codex_home)
    payload = _dashboard_payload(
        report,
        active_goals=state_snapshot["active_goals"],
        decision_requests=state_snapshot["active_decisions"],
        notifications=state_snapshot["notifications"]["recent"],
        multi_worker=build_multi_worker_status_payload(root=codex_home),
        state_snapshot=state_snapshot,
    )
    payload["daemon"] = supervisor_daemon_status(codex_home=codex_home)
    payload["watcher"] = supervisor_watcher_status(codex_home=codex_home)
    payload["workspace_cwd"] = str(workspace_cwd)
    return payload


def _active_goal_dicts_for_codex_home(
    codex_home: Path,
    *,
    limit: int = 20,
    include_status: bool = False,
) -> list[dict[str, Any]]:
    return list(
        build_supervisor_state_snapshot(
            codex_home=codex_home,
            goal_limit=limit,
        )["active_goals"]
    )


def _recent_context_results_for_report(
    *,
    codex_home: Path,
    report: Any,
) -> list[dict[str, Any]]:
    cwd = _context_cwd_for_report(report)
    results = read_recent_context_results(
        codex_home=codex_home,
        cwd=Path(cwd) if cwd else None,
    )
    return [result.to_dict() for result in results]


def _decision_request_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        request.to_dict()
        for request in read_active_decision_requests(codex_home=codex_home)
    ]


def _decision_answer_dicts(codex_home: Path) -> list[dict[str, Any]]:
    return [
        dict(answer)
        for answer in read_recent_decision_answers(codex_home=codex_home)
    ]


def _context_cwd_for_report(report: Any) -> str | None:
    for session in report.sessions:
        cwd = getattr(session, "cwd", None)
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


class _DashboardRequestHandler(BaseHTTPRequestHandler):
    server: SupervisorDashboardServer

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("access-control-max-age", "600")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
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
        if path == "/decision/answer":
            self._send_decision_answer()
            return
        if path == "/goal/add":
            self._send_goal_add()
            return
        if path == "/goal/plan":
            self._send_goal_plan()
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
            history = _desktop_chat_history(payload.get("history"))
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

    def _send_goal_plan(self) -> None:
        try:
            payload = self._read_json_body()
            write = bool(payload.get("write"))
            if write and isinstance(payload.get("candidates"), list):
                planned = _write_goal_plan_candidates(
                    codex_home=self.server.codex_home,
                    payload=payload,
                )
            else:
                provider = self.server.llm_action_provider or resolve_summary_provider_from_env(
                    agent_name="supervisor"
                )
                planned = plan_supervisor_goals(
                    root=Path.cwd(),
                    codex_home=self.server.codex_home,
                    provider=provider,
                    user_goal=_required_string(payload.get("goal"), "goal"),
                    write=write,
                    limit=_positive_int(payload.get("limit"), "limit", default=3),
                    planning_trigger="web",
                )
            planned["active_goals"] = _active_goal_dicts_for_codex_home(
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
                "decision_requests": _decision_request_dicts(self.server.codex_home),
                "recent_decision_answers": _decision_answer_dicts(self.server.codex_home),
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
                "active_goals": _active_goal_dicts_for_codex_home(
                    self.server.codex_home,
                    include_status=True,
                ),
            }
        )

    def _send_service_action(self, path: str) -> None:
        try:
            self._read_json_body()
            result = _run_service_action(self.server, path)
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


def _run_service_action(
    server: SupervisorDashboardServer,
    path: str,
) -> dict[str, Any]:
    if path == "/daemon/start":
        return {
            "target": "daemon",
            "action": "start",
            "service": start_supervisor_daemon(
                codex_home=server.codex_home,
                interval=30,
                limit=server.limit,
                stale_after=server.stale_after_seconds,
                active_within=server.active_within_seconds,
                prompt_cooldown=DEFAULT_PROMPT_COOLDOWN_SECONDS,
                max_continue_count=DEFAULT_MAX_CONTINUE_COUNT,
                max_context_requests=DEFAULT_MAX_CONTEXT_REQUESTS,
                max_failure_retries=DEFAULT_MAX_FAILURE_RETRIES,
                decision_timeout=DEFAULT_DECISION_TIMEOUT_SECONDS,
                max_run_minutes=DEFAULT_MAX_RUN_MINUTES,
                max_fanout_launches=DEFAULT_FANOUT_LIMIT,
                worker_codex_model=DEFAULT_WORKER_CODEX_MODEL,
                worker_codex_config=DEFAULT_WORKER_CODEX_CONFIG,
            ),
        }
    if path == "/daemon/stop":
        return {
            "target": "daemon",
            "action": "stop",
            "service": stop_supervisor_daemon(codex_home=server.codex_home),
        }
    if path == "/watcher/start":
        return {
            "target": "watcher",
            "action": "start",
            "service": start_supervisor_watcher(
                codex_home=server.codex_home,
                interval=60,
            ),
        }
    if path == "/watcher/stop":
        return {
            "target": "watcher",
            "action": "stop",
            "service": stop_supervisor_watcher(codex_home=server.codex_home),
        }
    raise ValueError("unknown service action")


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


def _desktop_chat_history(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("history must be a list")
    history: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        clean_content = content.strip()
        if not clean_content:
            continue
        history.append({"role": role, "content": clean_content})
    return history[-12:]


def _write_goal_plan_candidates(
    *,
    codex_home: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    candidates = _goal_plan_candidates(payload)
    written = [
        record_supervisor_goal(
            codex_home=codex_home,
            cwd=Path.cwd(),
            goal=candidate["goal"],
            target_name=candidate.get("target_name"),
        ).to_dict()
        for candidate in candidates
    ]
    return {
        "status": "ok",
        "mode": "write",
        "root": str(Path.cwd()),
        "user_goal": _optional_string(payload.get("goal")),
        "planning_trigger": "web",
        "sources": [],
        "candidates": candidates,
        "written_goals": written,
        "plan_summary": _optional_string(payload.get("plan_summary")),
        "phases": payload.get("phases") if isinstance(payload.get("phases"), list) else [],
        "parallel_recommendations": payload.get("parallel_recommendations")
        if isinstance(payload.get("parallel_recommendations"), list)
        else [],
        "stop_conditions": payload.get("stop_conditions")
        if isinstance(payload.get("stop_conditions"), list)
        else [],
        "acceptance_conditions": payload.get("acceptance_conditions")
        if isinstance(payload.get("acceptance_conditions"), list)
        else [],
    }


def _goal_plan_candidates(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("candidates must not be empty")
    candidates: list[dict[str, str]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        goal = _optional_string(raw.get("goal"))
        if goal is None:
            continue
        target_name = _optional_string(raw.get("target_name"))
        reason = _optional_string(raw.get("reason"))
        item = {"goal": goal}
        if target_name is not None:
            item["target_name"] = target_name
        if reason is not None:
            item["reason"] = reason
        candidates.append(item)
    if not candidates:
        raise ValueError("candidates must contain usable goals")
    return candidates
