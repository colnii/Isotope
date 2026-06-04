"""Supervisor daemon and watcher service action routes."""

from __future__ import annotations

import importlib
from typing import Any, Protocol

from ...daemon import (
    start_supervisor_daemon,
    start_supervisor_watcher,
    stop_supervisor_daemon,
    stop_supervisor_watcher,
)
from ...planner.decision_requests import DEFAULT_DECISION_TIMEOUT_SECONDS
from ...runner import (
    DEFAULT_MAX_CONTEXT_REQUESTS,
    DEFAULT_MAX_FAILURE_RETRIES,
    DEFAULT_MAX_RUN_MINUTES,
    DEFAULT_WORKER_CODEX_CONFIG,
    DEFAULT_WORKER_CODEX_MODEL,
)
from ...state.fanout import DEFAULT_FANOUT_LIMIT
from ...state.lane_state import (
    DEFAULT_MAX_CONTINUE_COUNT,
    DEFAULT_PROMPT_COOLDOWN_SECONDS,
)


SERVICE_ACTION_PATHS = {"/daemon/start", "/daemon/stop", "/watcher/start", "/watcher/stop"}


class ServiceActionServer(Protocol):
    codex_home: Any
    limit: int
    stale_after_seconds: int
    active_within_seconds: int


def _service_function(name: str):
    web_package = importlib.import_module("isotope.features.supervisor.web")
    return getattr(web_package, name)


def run_service_action(
    server: ServiceActionServer,
    path: str,
) -> dict[str, Any]:
    if path == "/daemon/start":
        return {
            "target": "daemon",
            "action": "start",
            "service": _service_function("start_supervisor_daemon")(
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
            "service": _service_function("stop_supervisor_daemon")(
                codex_home=server.codex_home
            ),
        }
    if path == "/watcher/start":
        return {
            "target": "watcher",
            "action": "start",
            "service": _service_function("start_supervisor_watcher")(
                codex_home=server.codex_home,
                interval=60,
            ),
        }
    if path == "/watcher/stop":
        return {
            "target": "watcher",
            "action": "stop",
            "service": _service_function("stop_supervisor_watcher")(
                codex_home=server.codex_home
            ),
        }
    raise ValueError("unknown service action")
