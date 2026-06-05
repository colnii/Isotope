"""Managed Codex worker lifecycle: launch, resume, adopt."""

from __future__ import annotations

import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from isotope.integrations.codex.cli import (
    CodexSupervisorCliConfig,
    build_supervisor_launch_exec_argv,
    build_supervisor_resume_exec_argv,
    build_supervisor_tmux_launch_command,
)

from ..notifications.bell_events import install_tmux_bell_hook

from ..registry.records import (
    ARCHIVED_MANAGED_STATUS,
    ManagedCodexRecord,
    _ensure_aware_utc,
    _utc_now,
    _with_supervisor_protocol,
    _worker_role,
    append_managed_record,
    default_log_dir,
    default_registry_path,
)
from ..registry.session_lookup import find_codex_session_snapshot

def launch_managed_codex(
    *,
    codex_home: Path | str,
    cwd: Path | str,
    name: str,
    prompt: str,
    codex_bin: str = "codex",
    codex_model: str | None = None,
    codex_config: tuple[str, ...] = (),
    backend: str = "process",
    tmux_session: str | None = None,
    worker_role: str = "worker",
    now: Callable[[], datetime] | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ManagedCodexRecord:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    name_text = name.strip()
    prompt_text = prompt.strip()
    codex_bin_text = codex_bin.strip()
    if not name_text:
        raise ValueError("name must not be empty")
    if not prompt_text:
        raise ValueError("prompt must not be empty")
    if not codex_bin_text:
        raise ValueError("codex_bin must not be empty")
    worker_role_text = _worker_role(worker_role)
    backend_text = backend.strip()
    if backend_text not in {"process", "tmux"}:
        raise ValueError("backend must be process or tmux")

    started_at = _ensure_aware_utc((now or _utc_now)()).isoformat()
    record_id = "managed-" + uuid.uuid4().hex[:12]
    log_dir = default_log_dir(codex_home)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{record_id}.log"
    supervisor_prompt = _with_supervisor_protocol(prompt_text)
    command_config = CodexSupervisorCliConfig(
        executable=codex_bin_text,
        workspace_root=str(workspace),
        model=codex_model,
        config_overrides=codex_config,
    )
    process_codex_command = build_supervisor_launch_exec_argv(
        command_config,
        prompt=supervisor_prompt,
    )
    tmux_session_text: str | None = None
    pid = 0
    if backend_text == "process":
        command = process_codex_command
        with log_path.open("ab") as log_file:
            process = popen(
                list(command),
                cwd=str(workspace),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        pid = int(process.pid)
    else:
        tmux_session_text = (tmux_session or name_text).strip()
        if not tmux_session_text:
            raise ValueError("tmux_session must not be empty")
        command = build_supervisor_tmux_launch_command(
            command_config,
            tmux_session=tmux_session_text,
            prompt=supervisor_prompt,
        )
        try:
            run(list(command), check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise ValueError(f"tmux launch failed: {message}") from exc
        try:
            install_tmux_bell_hook(
                codex_home=codex_home,
                name=name_text,
                tmux_session=tmux_session_text,
                run=run,
            )
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise ValueError(f"tmux bell hook install failed: {message}") from exc

    record = ManagedCodexRecord(
        record_id=record_id,
        name=name_text,
        cwd=str(workspace),
        prompt=prompt_text,
        command=command,
        pid=pid,
        started_at=started_at,
        log_path=str(log_path),
        backend=backend_text,
        tmux_session=tmux_session_text,
        worker_role=worker_role_text,
    )
    append_managed_record(default_registry_path(codex_home), record)
    return record


def resume_managed_codex(
    *,
    codex_home: Path | str,
    cwd: Path | str,
    name: str,
    prompt: str,
    session_id: str | None = None,
    last: bool = False,
    codex_bin: str = "codex",
    codex_model: str | None = None,
    codex_config: tuple[str, ...] = (),
    worker_role: str = "worker",
    now: Callable[[], datetime] | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> ManagedCodexRecord:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    name_text = name.strip()
    prompt_text = prompt.strip()
    codex_bin_text = codex_bin.strip()
    session_text = session_id.strip() if session_id else None
    if not name_text:
        raise ValueError("name must not be empty")
    if not prompt_text:
        raise ValueError("prompt must not be empty")
    if not codex_bin_text:
        raise ValueError("codex_bin must not be empty")
    worker_role_text = _worker_role(worker_role)
    if last and session_text:
        raise ValueError("use either session_id or last, not both")
    if not last and not session_text:
        raise ValueError("session_id or last is required")

    started_at = _ensure_aware_utc((now or _utc_now)()).isoformat()
    record_id = "managed-" + uuid.uuid4().hex[:12]
    log_dir = default_log_dir(codex_home)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{record_id}.log"
    command = build_supervisor_resume_exec_argv(
        CodexSupervisorCliConfig(
            executable=codex_bin_text,
            workspace_root=str(workspace),
            model=codex_model,
            config_overrides=codex_config,
        ),
        session_id=session_text,
        last=last,
        prompt=_with_supervisor_protocol(prompt_text),
    )
    with log_path.open("ab") as log_file:
        process = popen(
            list(command),
            cwd=str(workspace),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    record = ManagedCodexRecord(
        record_id=record_id,
        name=name_text,
        cwd=str(workspace),
        prompt=prompt_text,
        command=command,
        pid=int(process.pid),
        started_at=started_at,
        log_path=str(log_path),
        status="resumed",
        backend="codex_exec_resume",
        resume_session_id=session_text,
        resume_last=last,
        worker_role=worker_role_text,
    )
    append_managed_record(default_registry_path(codex_home), record)
    return record


def adopt_tmux_session(
    *,
    codex_home: Path | str,
    cwd: Path | str,
    name: str,
    tmux_session: str,
    prompt: str = "接管已有 tmux 会话",
    worker_role: str = "worker",
    now: Callable[[], datetime] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ManagedCodexRecord:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    name_text = name.strip()
    tmux_session_text = tmux_session.strip()
    prompt_text = prompt.strip()
    if not name_text:
        raise ValueError("name must not be empty")
    if not tmux_session_text:
        raise ValueError("tmux_session must not be empty")
    if not prompt_text:
        raise ValueError("prompt must not be empty")
    worker_role_text = _worker_role(worker_role)

    completed = run(
        ["tmux", "has-session", "-t", tmux_session_text],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or tmux_session_text).strip()
        raise ValueError(f"tmux session not found: {message}")
    try:
        install_tmux_bell_hook(
            codex_home=codex_home,
            name=name_text,
            tmux_session=tmux_session_text,
            run=run,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ValueError(f"tmux bell hook install failed: {message}") from exc

    started_at = _ensure_aware_utc((now or _utc_now)()).isoformat()
    record_id = "managed-" + uuid.uuid4().hex[:12]
    log_dir = default_log_dir(codex_home)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{record_id}.log"
    record = ManagedCodexRecord(
        record_id=record_id,
        name=name_text,
        cwd=str(workspace),
        prompt=prompt_text,
        command=("tmux", "attach", "-t", tmux_session_text),
        pid=0,
        started_at=started_at,
        log_path=str(log_path),
        status="adopted",
        backend="tmux",
        tmux_session=tmux_session_text,
        worker_role=worker_role_text,
    )
    append_managed_record(default_registry_path(codex_home), record)
    return record


def adopt_codex_session(
    *,
    codex_home: Path | str,
    name: str,
    session_id: str,
    cwd: Path | str | None = None,
    prompt: str = "接管已有 Codex 会话",
    worker_role: str = "worker",
    now: Callable[[], datetime] | None = None,
) -> ManagedCodexRecord:
    name_text = name.strip()
    session_text = session_id.strip()
    prompt_text = prompt.strip()
    if not name_text:
        raise ValueError("name must not be empty")
    if not session_text:
        raise ValueError("session_id must not be empty")
    if not prompt_text:
        raise ValueError("prompt must not be empty")
    worker_role_text = _worker_role(worker_role)

    snapshot = find_codex_session_snapshot(codex_home=codex_home, session_id=session_text)
    if snapshot is None:
        raise ValueError(f"Codex session not found: {session_text}")
    workspace_text = str(cwd).strip() if cwd is not None else snapshot.cwd.strip()
    if not workspace_text:
        raise ValueError("cwd is required when the Codex session has no cwd metadata")
    workspace = Path(workspace_text).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")

    started_at = _ensure_aware_utc((now or _utc_now)()).isoformat()
    record_id = "managed-" + uuid.uuid4().hex[:12]
    log_dir = default_log_dir(codex_home)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{record_id}.log"
    record = ManagedCodexRecord(
        record_id=record_id,
        name=name_text,
        cwd=str(workspace),
        prompt=prompt_text,
        command=("codex", "resume", session_text),
        pid=0,
        started_at=started_at,
        log_path=str(log_path),
        status="adopted",
        backend="codex_session",
        resume_session_id=session_text,
        worker_role=worker_role_text,
    )
    append_managed_record(default_registry_path(codex_home), record)
    return record
