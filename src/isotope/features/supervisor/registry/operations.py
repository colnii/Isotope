"""Managed Codex operations: send, archive, repair tmux bell hooks."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from ..notifications.bell_events import install_tmux_bell_hook

from ..registry.records import (
    ARCHIVED_MANAGED_STATUS,
    ManagedCodexRecord,
    ManagedSendResult,
    TmuxBellHookRepair,
    _find_managed_record,
    append_managed_record,
    default_registry_path,
    read_managed_records,
)

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
