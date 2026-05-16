"""本机 Codex 托管进程登记表。"""

from __future__ import annotations

import json
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


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
        }


@dataclass(frozen=True)
class ManagedSendResult:
    record: ManagedCodexRecord
    text: str


def default_registry_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "managed_sessions.jsonl"


def default_log_dir(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "logs"


def read_managed_records(registry_path: Path | str) -> tuple[ManagedCodexRecord, ...]:
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
    backend: str = "process",
    tmux_session: str | None = None,
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
    backend_text = backend.strip()
    if backend_text not in {"process", "tmux"}:
        raise ValueError("backend must be process or tmux")

    started_at = _ensure_aware_utc((now or _utc_now)()).isoformat()
    record_id = "managed-" + uuid.uuid4().hex[:12]
    log_dir = default_log_dir(codex_home)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{record_id}.log"
    codex_command = (
        codex_bin_text,
        "--cd",
        str(workspace),
        "--no-alt-screen",
        _with_supervisor_protocol(prompt_text),
    )
    tmux_session_text: str | None = None
    pid = 0
    if backend_text == "process":
        command = codex_command
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
        command = (
            "tmux",
            "new-session",
            "-d",
            "-s",
            tmux_session_text,
            "-c",
            str(workspace),
            shlex.join(codex_command),
        )
        try:
            run(list(command), check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or str(exc)).strip()
            raise ValueError(f"tmux launch failed: {message}") from exc

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

    try:
        run(
            ["tmux", "send-keys", "-t", record.tmux_session, "-l", text_text],
            check=True,
            text=True,
            capture_output=True,
        )
        run(
            ["tmux", "send-keys", "-t", record.tmux_session, "Enter"],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ValueError(f"tmux send failed: {message}") from exc
    return ManagedSendResult(record=record, text=text_text)


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
    records: tuple[ManagedCodexRecord, ...], name: str
) -> ManagedCodexRecord | None:
    for record in reversed(records):
        if record.name == name:
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
    )


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
