"""本机 Codex 托管进程登记表。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable



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
