"""Background daemon helpers for the Codex Supervisor loop."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .fanout import DEFAULT_FANOUT_LIMIT


@dataclass(frozen=True)
class SupervisorDaemonState:
    pid: int
    status: str
    started_at: str
    stopped_at: str | None
    command: tuple[str, ...]
    codex_home: str
    log_path: str
    state_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "command": list(self.command),
            "codex_home": self.codex_home,
            "log_path": self.log_path,
            "state_path": self.state_path,
        }

    def with_status(
        self,
        status: str,
        *,
        stopped_at: str | None = None,
    ) -> "SupervisorDaemonState":
        return SupervisorDaemonState(
            pid=self.pid,
            status=status,
            started_at=self.started_at,
            stopped_at=stopped_at if stopped_at is not None else self.stopped_at,
            command=self.command,
            codex_home=self.codex_home,
            log_path=self.log_path,
            state_path=self.state_path,
        )


def default_daemon_state_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "daemon.json"


def default_daemon_log_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "logs" / "daemon.log"


def default_watcher_state_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "watcher.json"


def default_watcher_log_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "logs" / "watcher.log"


def start_supervisor_daemon(
    *,
    codex_home: Path | str,
    interval: int,
    limit: int,
    stale_after: int,
    active_within: int,
    prompt_cooldown: int,
    max_continue_count: int,
    max_context_requests: int,
    max_run_minutes: int,
    max_fanout_launches: int,
    name: str | None = None,
    goal: str | None = None,
    llm_summary: bool = False,
    auto_adopt: bool = True,
    worker_codex_model: str | None = None,
    worker_codex_config: tuple[str, ...] = (),
) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    existing = read_supervisor_daemon_state(home)
    if (
        existing is not None
        and existing.status == "running"
        and _process_is_alive(existing.pid)
    ):
        return {"action": "already_running", **existing.to_dict()}

    log_path = default_daemon_log_path(home)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = _build_loop_command(
        codex_home=home,
        interval=interval,
        limit=limit,
        stale_after=stale_after,
        active_within=active_within,
        prompt_cooldown=prompt_cooldown,
        max_continue_count=max_continue_count,
        max_context_requests=max_context_requests,
        max_run_minutes=max_run_minutes,
        max_fanout_launches=max_fanout_launches,
        name=name,
        goal=goal,
        llm_summary=llm_summary,
        auto_adopt=auto_adopt,
        worker_codex_model=worker_codex_model,
        worker_codex_config=worker_codex_config,
    )
    pid = _spawn_daemon_process(command, log_path)
    state = SupervisorDaemonState(
        pid=pid,
        status="running",
        started_at=_utc_now().isoformat(),
        stopped_at=None,
        command=command,
        codex_home=str(home),
        log_path=str(log_path),
        state_path=str(default_daemon_state_path(home)),
    )
    write_supervisor_daemon_state(state)
    return {"action": "started", **state.to_dict()}


def start_supervisor_watcher(
    *,
    codex_home: Path | str,
    interval: int,
) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    existing = read_supervisor_watcher_state(home)
    if (
        existing is not None
        and existing.status == "running"
        and _process_is_alive(existing.pid)
    ):
        return {"action": "already_running", **existing.to_dict()}

    log_path = default_watcher_log_path(home)
    command = (
        sys.executable,
        "-m",
        "isotope.features.supervisor.runner",
        "daemon",
        "watcher",
        "run",
        "--codex-home",
        str(home),
        "--interval",
        str(interval),
    )
    pid = _spawn_daemon_process(command, log_path)
    state = SupervisorDaemonState(
        pid=pid,
        status="running",
        started_at=_utc_now().isoformat(),
        stopped_at=None,
        command=command,
        codex_home=str(home),
        log_path=str(log_path),
        state_path=str(default_watcher_state_path(home)),
    )
    write_supervisor_daemon_state(state)
    return {"action": "started", **state.to_dict()}


def supervisor_watcher_status(*, codex_home: Path | str) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    state = read_supervisor_watcher_state(home)
    if state is None:
        return _not_running_watcher_payload(home)
    if state.status == "running" and not _process_is_alive(state.pid):
        return state.with_status("stale").to_dict()
    return state.to_dict()


def stop_supervisor_watcher(*, codex_home: Path | str) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    state = read_supervisor_watcher_state(home)
    if state is None:
        return _not_running_watcher_payload(home)
    if state.status == "running" and _process_is_alive(state.pid):
        os.kill(state.pid, signal.SIGTERM)
    stopped = state.with_status("stopped", stopped_at=_utc_now().isoformat())
    write_supervisor_daemon_state(stopped)
    return stopped.to_dict()


def run_supervisor_watcher(
    *,
    codex_home: Path | str,
    interval: int,
    iterations: int | None = None,
) -> Iterator[dict[str, Any]]:
    home = Path(codex_home).expanduser()
    count = 0
    while iterations is None or count < iterations:
        count += 1
        payload = {
            "status": "ok",
            "iteration": count,
            "watchdog": watchdog_supervisor_daemon(codex_home=home),
        }
        yield payload
        if iterations is None or count < iterations:
            _sleep(interval)


def watchdog_supervisor_daemon(*, codex_home: Path | str) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    state = read_supervisor_daemon_state(home)
    if state is None:
        return {"action": "not_running", **_not_running_payload(home)}
    if state.status == "stopped":
        return {"action": "stopped", **state.to_dict()}
    if _process_is_alive(state.pid):
        return {"action": "alive", **state.to_dict()}
    if not state.command:
        return {"action": "cannot_restart", **state.to_dict()}

    log_path = Path(state.log_path).expanduser()
    pid = _spawn_daemon_process(state.command, log_path)
    restarted = SupervisorDaemonState(
        pid=pid,
        status="running",
        started_at=_utc_now().isoformat(),
        stopped_at=None,
        command=state.command,
        codex_home=state.codex_home,
        log_path=state.log_path,
        state_path=state.state_path,
    )
    write_supervisor_daemon_state(restarted)
    return {
        "action": "restarted",
        "previous_pid": state.pid,
        **restarted.to_dict(),
    }


def supervisor_daemon_status(*, codex_home: Path | str) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    state = read_supervisor_daemon_state(home)
    if state is None:
        return _not_running_payload(home)
    if state.status == "running" and not _process_is_alive(state.pid):
        return state.with_status("stale").to_dict()
    return state.to_dict()


def stop_supervisor_daemon(*, codex_home: Path | str) -> dict[str, Any]:
    home = Path(codex_home).expanduser()
    state = read_supervisor_daemon_state(home)
    if state is None:
        return _not_running_payload(home)
    if state.status == "running" and _process_is_alive(state.pid):
        os.kill(state.pid, signal.SIGTERM)
    stopped = state.with_status("stopped", stopped_at=_utc_now().isoformat())
    write_supervisor_daemon_state(stopped)
    return stopped.to_dict()


def read_supervisor_daemon_state(codex_home: Path | str) -> SupervisorDaemonState | None:
    return _read_supervisor_state(default_daemon_state_path(codex_home))


def read_supervisor_watcher_state(
    codex_home: Path | str,
) -> SupervisorDaemonState | None:
    return _read_supervisor_state(default_watcher_state_path(codex_home))


def _read_supervisor_state(state_path: Path | str) -> SupervisorDaemonState | None:
    state_path = Path(state_path).expanduser()
    if not state_path.is_file():
        return None
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return _state_from_dict(raw, state_path=state_path)


def write_supervisor_daemon_state(state: SupervisorDaemonState) -> None:
    path = Path(state.state_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _spawn_daemon_process(command: tuple[str, ...], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return int(process.pid)


def _build_loop_command(
    *,
    codex_home: Path,
    interval: int,
    limit: int,
    stale_after: int,
    active_within: int,
    prompt_cooldown: int,
    max_continue_count: int,
    max_context_requests: int,
    max_run_minutes: int,
    max_fanout_launches: int,
    name: str | None,
    goal: str | None,
    llm_summary: bool,
    auto_adopt: bool,
    worker_codex_model: str | None,
    worker_codex_config: tuple[str, ...],
) -> tuple[str, ...]:
    command = [
        sys.executable,
        "-u",
        "-m",
        "isotope.features.supervisor.runner",
        "loop",
        "--codex-home",
        str(codex_home),
        "--interval",
        str(interval),
        "--limit",
        str(limit),
    ]
    if stale_after != 600:
        command.extend(["--stale-after", str(stale_after)])
    if active_within != 180:
        command.extend(["--active-within", str(active_within)])
    if prompt_cooldown != 300:
        command.extend(["--prompt-cooldown", str(prompt_cooldown)])
    if max_continue_count != 0:
        command.extend(["--max-continue-count", str(max_continue_count)])
    if max_context_requests != 0:
        command.extend(["--max-context-requests", str(max_context_requests)])
    if max_run_minutes != 0:
        command.extend(["--max-run-minutes", str(max_run_minutes)])
    if max_fanout_launches != DEFAULT_FANOUT_LIMIT:
        command.extend(["--max-fanout-launches", str(max_fanout_launches)])
    if name:
        command.extend(["--name", name])
    if goal:
        command.extend(["--goal", goal])
    if worker_codex_model:
        command.extend(["--worker-codex-model", worker_codex_model])
    for item in worker_codex_config:
        command.extend(["--worker-codex-config", item])
    if llm_summary:
        command.append("--llm-summary")
    if not auto_adopt:
        command.append("--no-auto-adopt")
    return tuple(command)


def _state_from_dict(
    raw: dict[str, object],
    *,
    state_path: Path,
) -> SupervisorDaemonState | None:
    pid = raw.get("pid")
    status = _string(raw.get("status")) or "running"
    started_at = _string(raw.get("started_at"))
    stopped_at = _optional_string(raw.get("stopped_at"))
    command = raw.get("command")
    codex_home = _string(raw.get("codex_home"))
    log_path = _string(raw.get("log_path"))
    stored_state_path = _string(raw.get("state_path")) or str(state_path)
    if (
        not isinstance(pid, int)
        or started_at is None
        or not isinstance(command, list)
        or codex_home is None
        or log_path is None
    ):
        return None
    command_items = tuple(item for item in command if isinstance(item, str))
    if len(command_items) != len(command):
        return None
    return SupervisorDaemonState(
        pid=pid,
        status=status,
        started_at=started_at,
        stopped_at=stopped_at,
        command=command_items,
        codex_home=codex_home,
        log_path=log_path,
        state_path=stored_state_path,
    )


def _not_running_payload(codex_home: Path) -> dict[str, Any]:
    return {
        "pid": None,
        "status": "not_running",
        "started_at": None,
        "stopped_at": None,
        "command": [],
        "codex_home": str(codex_home),
        "log_path": str(default_daemon_log_path(codex_home)),
        "state_path": str(default_daemon_state_path(codex_home)),
    }


def _not_running_watcher_payload(codex_home: Path) -> dict[str, Any]:
    return {
        "pid": None,
        "status": "not_running",
        "started_at": None,
        "stopped_at": None,
        "command": [],
        "codex_home": str(codex_home),
        "log_path": str(default_watcher_log_path(codex_home)),
        "state_path": str(default_watcher_state_path(codex_home)),
    }


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)
