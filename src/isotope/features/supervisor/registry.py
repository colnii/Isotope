"""本机 Codex 托管进程登记表。"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from isotope.integrations.codex.cli import (
    CodexSupervisorCliConfig,
    build_supervisor_launch_exec_argv,
    build_supervisor_resume_exec_argv,
    build_supervisor_tmux_launch_command,
)

from .bell_events import install_tmux_bell_hook

ARCHIVED_MANAGED_STATUS = "archived"


@dataclass(frozen=True)
class ManagedCodexRecord:
    record_id: str
    name: str
    cwd: str
    prompt: str
    command: tuple[str, ...]
    pid: int
    started_at: str
    log_path: str
    status: str = "launched"
    backend: str = "process"
    tmux_session: str | None = None
    resume_session_id: str | None = None
    resume_last: bool = False
    worker_role: str = "worker"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "name": self.name,
            "cwd": self.cwd,
            "prompt": self.prompt,
            "command": list(self.command),
            "pid": self.pid,
            "started_at": self.started_at,
            "log_path": self.log_path,
            "status": self.status,
            "backend": self.backend,
            "tmux_session": self.tmux_session,
            "resume_session_id": self.resume_session_id,
            "resume_last": self.resume_last,
            "worker_role": self.worker_role,
        }


@dataclass(frozen=True)
class ManagedSendResult:
    record: ManagedCodexRecord
    text: str


@dataclass(frozen=True)
class TmuxBellHookRepair:
    name: str
    tmux_session: str
    status: str
    message: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "name": self.name,
            "tmux_session": self.tmux_session,
            "status": self.status,
            "message": self.message,
        }


def default_registry_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "managed_sessions.jsonl"


def default_log_dir(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "logs"


def read_managed_records(registry_path: Path | str) -> tuple[ManagedCodexRecord, ...]:
    latest_by_record_id: dict[str, ManagedCodexRecord] = {}
    for record in read_managed_record_events(registry_path):
        latest_by_record_id[record.record_id] = record
    return tuple(
        record
        for record in latest_by_record_id.values()
        if record.status != ARCHIVED_MANAGED_STATUS
    )


def read_managed_record_events(registry_path: Path | str) -> tuple[ManagedCodexRecord, ...]:
    path = Path(registry_path).expanduser()
    if not path.is_file():
        return ()
    records: list[ManagedCodexRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        record = _record_from_dict(raw)
        if record is not None:
            records.append(record)
    return tuple(records)


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


def send_to_managed_codex(
    *,
    codex_home: Path | str,
    name: str,
    text: str,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ManagedSendResult:
    name_text = name.strip()
    text_text = text
    if not name_text:
        raise ValueError("name must not be empty")
    if not text_text.strip():
        raise ValueError("text must not be empty")

    record = _find_managed_record(
        read_managed_records(default_registry_path(codex_home)),
        name_text,
    )
    if record is None:
        raise ValueError(f"managed Codex not found: {name_text}")
    if record.backend != "tmux" or record.tmux_session is None:
        raise ValueError("send requires a tmux-managed Codex session")

    buffer_name = f"isotope-supervisor-{record.record_id}"
    try:
        run(
            ["tmux", "set-buffer", "-b", buffer_name, "--", text_text],
            check=True,
            text=True,
            capture_output=True,
        )
        run(
            ["tmux", "paste-buffer", "-d", "-b", buffer_name, "-t", record.tmux_session],
            check=True,
            text=True,
            capture_output=True,
        )
        time.sleep(0.2)
        run(
            ["tmux", "send-keys", "-t", record.tmux_session, "C-m"],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ValueError(f"tmux send failed: {message}") from exc
    return ManagedSendResult(record=record, text=text_text)


def archive_managed_codex(
    *,
    codex_home: Path | str,
    name: str,
    record_id: str | None = None,
) -> ManagedCodexRecord:
    name_text = name.strip()
    if not name_text:
        raise ValueError("name must not be empty")
    record_id_text = record_id.strip() if record_id is not None else None
    if record_id is not None and not record_id_text:
        raise ValueError("record_id must not be empty")
    registry_path = default_registry_path(codex_home)
    record = _find_managed_record(
        read_managed_records(registry_path),
        name_text,
        record_id=record_id_text,
    )
    if record is None:
        suffix = f" / {record_id_text}" if record_id_text else ""
        raise ValueError(f"managed Codex not found: {name_text}{suffix}")
    archived = ManagedCodexRecord(
        record_id=record.record_id,
        name=record.name,
        cwd=record.cwd,
        prompt=record.prompt,
        command=record.command,
        pid=record.pid,
        started_at=record.started_at,
        log_path=record.log_path,
        status=ARCHIVED_MANAGED_STATUS,
        backend=record.backend,
        tmux_session=record.tmux_session,
        resume_session_id=record.resume_session_id,
        resume_last=record.resume_last,
        worker_role=record.worker_role,
    )
    append_managed_record(registry_path, archived)
    return archived


def repair_tmux_bell_hooks(
    *,
    codex_home: Path | str,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[TmuxBellHookRepair, ...]:
    records = read_managed_records(default_registry_path(codex_home))
    latest_by_tmux: dict[str, ManagedCodexRecord] = {}
    for record in records:
        if record.backend == "tmux" and record.tmux_session:
            latest_by_tmux[record.tmux_session] = record

    repairs: list[TmuxBellHookRepair] = []
    for record in latest_by_tmux.values():
        tmux_session = record.tmux_session or ""
        try:
            exists = run(
                ["tmux", "has-session", "-t", tmux_session],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            repairs.append(
                TmuxBellHookRepair(
                    name=record.name,
                    tmux_session=tmux_session,
                    status="failed",
                    message=str(exc),
                )
            )
            continue
        if exists.returncode != 0:
            message = (exists.stderr or exists.stdout or "tmux session not found").strip()
            repairs.append(
                TmuxBellHookRepair(
                    name=record.name,
                    tmux_session=tmux_session,
                    status="missing",
                    message=message,
                )
            )
            continue
        try:
            install_tmux_bell_hook(
                codex_home=codex_home,
                name=record.name,
                tmux_session=tmux_session,
                run=run,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            message = getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or str(exc)
            repairs.append(
                TmuxBellHookRepair(
                    name=record.name,
                    tmux_session=tmux_session,
                    status="failed",
                    message=str(message).strip(),
                )
            )
            continue
        repairs.append(
            TmuxBellHookRepair(
                name=record.name,
                tmux_session=tmux_session,
                status="installed",
            )
        )
    return tuple(repairs)


def append_managed_record(registry_path: Path | str, record: ManagedCodexRecord) -> None:
    path = Path(registry_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def _with_supervisor_protocol(prompt: str) -> str:
    return (
        prompt
        + "\n\n"
        + "Supervisor 状态汇报要求：\n"
        + "当你暂停、等待用户、完成一批工作或遇到阻塞时，"
        + "在回复末尾追加三行：\n"
        + "SUPERVISOR_STATUS: working|done|blocked|needs_user\n"
        + "SUPERVISOR_SUMMARY: 用一句中文说明当前状态\n"
        + "SUPERVISOR_NEXT: 用一句中文说明建议下一步\n"
    )


def _find_managed_record(
    records: tuple[ManagedCodexRecord, ...],
    name: str,
    *,
    record_id: str | None = None,
) -> ManagedCodexRecord | None:
    for record in reversed(records):
        if record.name == name and (record_id is None or record.record_id == record_id):
            return record
    return None


def _record_from_dict(raw: dict[str, object]) -> ManagedCodexRecord | None:
    record_id = _string(raw.get("record_id"))
    name = _string(raw.get("name"))
    cwd = _string(raw.get("cwd"))
    prompt = _string(raw.get("prompt"))
    pid = raw.get("pid")
    started_at = _string(raw.get("started_at"))
    log_path = _string(raw.get("log_path"))
    command = raw.get("command")
    status = _string(raw.get("status")) or "launched"
    backend = _string(raw.get("backend")) or "process"
    tmux_session = _string(raw.get("tmux_session"))
    resume_session_id = _string(raw.get("resume_session_id"))
    resume_last = raw.get("resume_last")
    worker_role = _string(raw.get("worker_role")) or "worker"
    if (
        record_id is None
        or name is None
        or cwd is None
        or prompt is None
        or not isinstance(pid, int)
        or started_at is None
        or log_path is None
        or not isinstance(command, list)
    ):
        return None
    command_items = tuple(item for item in command if isinstance(item, str))
    if len(command_items) != len(command):
        return None
    return ManagedCodexRecord(
        record_id=record_id,
        name=name,
        cwd=cwd,
        prompt=prompt,
        command=command_items,
        pid=pid,
        started_at=started_at,
        log_path=log_path,
        status=status,
        backend=backend,
        tmux_session=tmux_session,
        resume_session_id=resume_session_id,
        resume_last=resume_last if isinstance(resume_last, bool) else False,
        worker_role=worker_role,
    )


def _worker_role(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError("worker_role must not be empty")
    return text


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
