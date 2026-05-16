"""Read-only Codex session supervisor flow."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .bell_events import default_bell_events_path, read_latest_bell_events
from .registry import ManagedCodexRecord, default_registry_path, read_managed_records


STATUS_LABELS = {
    "working": "工作中",
    "needs_user": "等待用户",
    "stale": "疑似停住",
    "error": "疑似报错",
    "idle": "空闲",
    "exited": "已退出",
}
ATTENTION_MARKERS = (
    "是否继续",
    "确认是否",
    "需要你确认",
    "等待用户确认",
    "等待你确认",
    "等你确认",
    "请确认",
    "how would you like",
    "would you like",
    "please confirm",
)
ERROR_MARKERS = (
    "traceback",
    "error:",
    "failed",
    "process exited with code 1",
    "process exited with code 2",
    "exit code 1",
    "exit code 2",
    "测试失败",
    "命令失败",
)
MAX_FULL_SESSION_READ_BYTES = 2 * 1024 * 1024
SESSION_HEAD_READ_BYTES = 64 * 1024
SESSION_TAIL_READ_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CodexSessionSummary:
    session_id: str
    cwd: str
    source_path: str
    last_event_at: str
    age_seconds: int
    status: str
    reason: str
    status_evidence: dict[str, str] | None = None
    thread_name: str | None = None
    thread_id: str | None = None
    initial_user_title: str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    git_branch: str | None = None
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    cli_version: str | None = None
    model_provider: str | None = None
    managed: bool = False
    managed_name: str | None = None
    managed_pid: int | None = None
    managed_log_path: str | None = None
    managed_backend: str | None = None
    managed_tmux_session: str | None = None
    managed_terminal_excerpt: str | None = None
    managed_bell: bool = False
    managed_bell_event_at: str | None = None
    supervisor_status: str | None = None
    supervisor_summary: str | None = None
    supervisor_next: str | None = None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def short_session_id(self) -> str:
        parts = self.session_id.split("-")
        if len(parts) >= 5 and len(parts[0]) == 8:
            return parts[0]
        return self.session_id

    @property
    def display_title(self) -> str:
        title = (
            self.managed_name
            or self.thread_name
            or self.initial_user_title
            or self.agent_nickname
            or self.short_session_id
        )
        return _shorten(title, limit=48)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "short_session_id": self.short_session_id,
            "display_title": self.display_title,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "source_path": self.source_path,
            "last_event_at": self.last_event_at,
            "age_seconds": self.age_seconds,
            "status": self.status,
            "status_label": self.status_label,
            "reason": self.reason,
            "status_evidence": self.status_evidence,
            "thread_name": self.thread_name,
            "thread_id": self.thread_id,
            "initial_user_title": self.initial_user_title,
            "agent_nickname": self.agent_nickname,
            "agent_role": self.agent_role,
            "last_user_message": _shorten_optional(self.last_user_message),
            "last_assistant_message": _shorten_optional(self.last_assistant_message),
            "cli_version": self.cli_version,
            "model_provider": self.model_provider,
            "managed": self.managed,
            "managed_name": self.managed_name,
            "managed_pid": self.managed_pid,
            "managed_log_path": self.managed_log_path,
            "managed_backend": self.managed_backend,
            "managed_tmux_session": self.managed_tmux_session,
            "managed_terminal_excerpt": _shorten_optional(self.managed_terminal_excerpt),
            "managed_bell": self.managed_bell,
            "managed_bell_event_at": self.managed_bell_event_at,
            "supervisor_status": self.supervisor_status,
            "supervisor_summary": _shorten_optional(self.supervisor_summary),
            "supervisor_next": _shorten_optional(self.supervisor_next),
        }


@dataclass(frozen=True)
class SupervisorActionRecommendation:
    action: str
    label: str
    priority: str
    reason: str | None = None
    target_session_id: str | None = None
    target_name: str | None = None
    send_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "label": self.label,
            "priority": self.priority,
            "reason": self.reason,
            "target_name": self.target_name,
            "target_session_id": self.target_session_id,
            "send_text": self.send_text,
        }


@dataclass(frozen=True)
class CodexSupervisorReport:
    generated_at: str
    sessions: tuple[CodexSessionSummary, ...]

    @property
    def recommendation(self) -> SupervisorActionRecommendation:
        return _recommendation(self.sessions)

    def to_dict(self) -> dict[str, Any]:
        counts = {status: 0 for status in STATUS_LABELS}
        for session in self.sessions:
            counts[session.status] = counts.get(session.status, 0) + 1
        return {
            "status": "ok",
            "generated_at": self.generated_at,
            "summary": {
                "total": len(self.sessions),
                "counts": counts,
            },
            "recommendation": self.recommendation.to_dict(),
            "sessions": [session.to_dict() for session in self.sessions],
        }


class CodexSupervisorFlow:
    """Build a read-only status report from local Codex session files."""

    def __init__(
        self,
        *,
        codex_home: Path | str | None = None,
        registry_path: Path | str | None = None,
        now: Callable[[], datetime] | None = None,
        branch_resolver: Callable[[str], str | None] | None = None,
        process_checker: Callable[[int], bool] | None = None,
        tmux_session_checker: Callable[[str], bool] | None = None,
        tmux_bell_checker: Callable[[str], bool] | None = None,
        tmux_pane_reader: Callable[[str], str | None] | None = None,
    ) -> None:
        self.codex_home = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
        self.registry_path = (
            Path(registry_path).expanduser()
            if registry_path
            else default_registry_path(self.codex_home)
        )
        self.now = now or _utc_now
        self.branch_resolver = branch_resolver or _git_branch_for
        self.process_checker = process_checker or _pid_is_running
        self.tmux_session_checker = tmux_session_checker or _tmux_session_exists
        self.tmux_bell_checker = tmux_bell_checker or _tmux_window_has_bell
        self.tmux_pane_reader = tmux_pane_reader or _empty_tmux_pane

    def scan(
        self,
        *,
        limit: int = 10,
        stale_after_seconds: int = 600,
        active_within_seconds: int = 180,
    ) -> CodexSupervisorReport:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        if active_within_seconds <= 0:
            raise ValueError("active_within_seconds must be positive")
        now = _ensure_aware_utc(self.now())
        session_index_titles, session_index_recent_ids = _read_session_index(
            self.codex_home / "session_index.jsonl"
        )
        state_titles, state_recent_ids = _read_state_threads(self.codex_home / "state_5.sqlite")
        session_titles = {**session_index_titles, **state_titles}
        recent_session_ids = _merge_recent_session_ids(state_recent_ids, session_index_recent_ids)
        sessions = [
            summary
            for path in self._session_paths(limit=limit, recent_session_ids=recent_session_ids)
            if (
                summary := _read_session_summary(
                    path,
                    now=now,
                    stale_after_seconds=stale_after_seconds,
                    active_within_seconds=active_within_seconds,
                    branch_resolver=self.branch_resolver,
                    session_index_titles=session_titles,
                )
            )
            is not None
        ]
        bell_events = read_latest_bell_events(default_bell_events_path(self.codex_home))
        sessions.extend(
            _managed_summary(
                record,
                now=now,
                registry_path=self.registry_path,
                bell_events=bell_events,
                branch_resolver=self.branch_resolver,
                process_checker=self.process_checker,
                tmux_session_checker=self.tmux_session_checker,
                tmux_bell_checker=self.tmux_bell_checker,
                tmux_pane_reader=self.tmux_pane_reader,
            )
            for record in read_managed_records(self.registry_path)
        )
        sessions.sort(key=lambda session: session.last_event_at, reverse=True)
        return CodexSupervisorReport(
            generated_at=now.isoformat(),
            sessions=tuple(sessions[:limit]),
        )

    def _session_paths(
        self,
        *,
        limit: int,
        recent_session_ids: tuple[str, ...] = (),
    ) -> list[Path]:
        sessions_root = self.codex_home / "sessions"
        if not sessions_root.exists():
            return []
        paths = sorted(sessions_root.rglob("*.jsonl"))
        candidate_limit = max(4, limit + 3)
        if len(paths) <= candidate_limit:
            return paths
        selected: list[Path] = []
        seen: set[Path] = set()
        paths_by_id = {
            session_id: path
            for path in paths
            if (session_id := _session_id_from_path(path)) is not None
        }
        for session_id in recent_session_ids[:candidate_limit]:
            if path := paths_by_id.get(session_id):
                selected.append(path)
                seen.add(path)
        for path in sorted(paths, key=_path_mtime_ns, reverse=True):
            if len(selected) >= candidate_limit:
                break
            if path in seen:
                continue
            selected.append(path)
            seen.add(path)
        return selected


def render_plain_report(report: CodexSupervisorReport) -> str:
    lines = [
        "[Codex Supervisor]",
        f"生成时间：{report.generated_at}",
        f"窗口数量：{len(report.sessions)}",
    ]
    if not report.sessions:
        lines.append("未发现本机 Codex 会话。")
        return "\n".join(lines)
    for index, session in enumerate(report.sessions, start=1):
        branch = f" 分支：{session.git_branch}" if session.git_branch else ""
        lines.append(
            f"{index}. {session.session_id} 状态：{session.status_label} "
            f"目录：{session.cwd}{branch}"
        )
        if session.managed:
            pid = f" pid={session.managed_pid}" if session.managed_pid else ""
            backend = f" backend={session.managed_backend}" if session.managed_backend else ""
            tmux = (
                f" tmux={session.managed_tmux_session}"
                if session.managed_tmux_session
                else ""
            )
            bell = (
                f" bell={'响过' if session.managed_bell else '无'}"
                if session.managed_backend == "tmux"
                else ""
            )
            name = session.managed_name or "未命名"
            lines.append(f"   托管：{name}{pid}{backend}{tmux}{bell}")
            if session.managed_bell_event_at:
                lines.append(f"   bell 事件：{session.managed_bell_event_at}")
        if session.supervisor_status:
            lines.append(f"   Supervisor 状态：{session.supervisor_status}")
        if session.supervisor_summary:
            lines.append(f"   Supervisor 摘要：{_shorten(session.supervisor_summary)}")
        if session.supervisor_next:
            lines.append(f"   Supervisor 下一步：{_shorten(session.supervisor_next)}")
        lines.append(f"   原因：{session.reason}")
        if session.status_evidence:
            lines.append(
                "   依据："
                f"{session.status_evidence['label']} - {session.status_evidence['detail']}"
            )
        if session.last_user_message:
            lines.append(f"   最近用户：{_shorten(session.last_user_message)}")
        if session.last_assistant_message:
            lines.append(f"   最近回复：{_shorten(session.last_assistant_message)}")
    lines.append(f"建议：{report.recommendation.label}")
    return "\n".join(lines)


def _read_session_summary(
    path: Path,
    *,
    now: datetime,
    stale_after_seconds: int,
    active_within_seconds: int,
    branch_resolver: Callable[[str], str | None],
    session_index_titles: dict[str, str] | None = None,
) -> CodexSessionSummary | None:
    meta: dict[str, Any] = {}
    last_event_at: datetime | None = None
    last_user_message: str | None = None
    first_user_message: str | None = None
    last_assistant_message: str | None = None
    last_text: str | None = None
    supervisor_status: str | None = None
    supervisor_summary: str | None = None
    supervisor_next: str | None = None
    thread_name: str | None = None
    thread_id: str | None = None
    pending_thread_name: str | None = None
    pending_thread_id: str | None = None
    try:
        lines = _read_session_lines(path)
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_time = _parse_timestamp(event.get("timestamp"))
        if event_time is not None:
            last_event_at = event_time
        if event.get("type") == "session_meta":
            payload = event.get("payload")
            if isinstance(payload, dict):
                meta.update(payload)
            continue
        if event.get("type") == "event_msg":
            payload = event.get("payload")
            if isinstance(payload, dict) and payload.get("type") == "thread_name_updated":
                pending_thread_name = _optional_string(payload.get("thread_name")) or pending_thread_name
                pending_thread_id = _optional_string(payload.get("thread_id")) or pending_thread_id
        role, text = _message_from_event(event)
        if text:
            last_text = text
            protocol = _supervisor_protocol_from_text(text)
            supervisor_status = protocol.get("status") or supervisor_status
            supervisor_summary = protocol.get("summary") or supervisor_summary
            supervisor_next = protocol.get("next") or supervisor_next
            if role == "user":
                if first_user_message is None and not _is_title_noise(text):
                    first_user_message = text
                last_user_message = text
            if role == "assistant":
                last_assistant_message = text
    if not meta and last_event_at is None:
        return None
    if last_event_at is None:
        last_event_at = _parse_timestamp(meta.get("timestamp")) or now
    session_id = str(meta.get("id") or path.stem)
    if pending_thread_name and (pending_thread_id is None or pending_thread_id == session_id):
        thread_name = pending_thread_name
        thread_id = pending_thread_id
    if thread_name is None and session_index_titles:
        thread_name = session_index_titles.get(session_id)
    cwd = str(meta.get("cwd") or "")
    age_seconds = max(0, int((now - last_event_at).total_seconds()))
    status, reason, status_evidence = _classify_session(
        age_seconds=age_seconds,
        last_assistant_message=last_assistant_message,
        last_text=last_text,
        stale_after_seconds=stale_after_seconds,
        active_within_seconds=active_within_seconds,
    )
    if supervisor_status:
        status_evidence = _supervisor_status_evidence(supervisor_status)
    return CodexSessionSummary(
        session_id=session_id,
        cwd=cwd,
        git_branch=branch_resolver(cwd) if cwd else None,
        source_path=str(path),
        last_event_at=last_event_at.isoformat(),
        age_seconds=age_seconds,
        status=status,
        reason=reason,
        status_evidence=status_evidence,
        thread_name=thread_name,
        thread_id=thread_id,
        initial_user_title=_title_from_user_message(first_user_message),
        agent_nickname=_optional_string(meta.get("agent_nickname")),
        agent_role=_optional_string(meta.get("agent_role")),
        last_user_message=last_user_message,
        last_assistant_message=last_assistant_message,
        cli_version=_optional_string(meta.get("cli_version")),
        model_provider=_optional_string(meta.get("model_provider")),
        supervisor_status=supervisor_status,
        supervisor_summary=supervisor_summary,
        supervisor_next=supervisor_next,
    )


def _read_session_index(path: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    titles: dict[str, str] = {}
    updated_at: dict[str, datetime] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return titles, ()
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        session_id = _optional_string(item.get("id"))
        thread_name = _optional_string(item.get("thread_name"))
        if session_id and thread_name:
            titles[session_id] = thread_name
        if session_id:
            updated_at[session_id] = _parse_timestamp(item.get("updated_at")) or datetime.min.replace(
                tzinfo=timezone.utc
            )
    recent_session_ids = tuple(
        sorted(updated_at, key=lambda session_id: updated_at[session_id], reverse=True)
    )
    return titles, recent_session_ids


def _read_state_threads(path: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    if not path.exists():
        return {}, ()
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}, ()
    try:
        rows = connection.execute("select id, title, updated_at from threads").fetchall()
    except sqlite3.Error:
        return {}, ()
    finally:
        connection.close()
    titles: dict[str, str] = {}
    updated_at: dict[str, int] = {}
    for session_id_value, title_value, updated_at_value in rows:
        session_id = _optional_string(session_id_value)
        title = _optional_string(title_value)
        if session_id and title:
            titles[session_id] = title
        if session_id and isinstance(updated_at_value, int):
            updated_at[session_id] = updated_at_value
    recent_session_ids = tuple(
        sorted(updated_at, key=lambda session_id: updated_at[session_id], reverse=True)
    )
    return titles, recent_session_ids


def _merge_recent_session_ids(
    *groups: tuple[str, ...],
) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for session_id in group:
            if session_id in seen:
                continue
            merged.append(session_id)
            seen.add(session_id)
    return tuple(merged)


def _session_id_from_path(path: Path) -> str | None:
    match = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        path.name,
    )
    return match.group(1) if match else None


def _path_mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _read_session_lines(path: Path) -> list[str]:
    size = path.stat().st_size
    if size <= MAX_FULL_SESSION_READ_BYTES:
        return path.read_text(encoding="utf-8").splitlines()
    with path.open("rb") as handle:
        head = handle.read(SESSION_HEAD_READ_BYTES)
        tail_offset = max(0, size - SESSION_TAIL_READ_BYTES)
        handle.seek(tail_offset)
        tail = handle.read(SESSION_TAIL_READ_BYTES)
    data = head + b"\n" + tail
    return data.decode("utf-8", errors="ignore").splitlines()


def _managed_summary(
    record: ManagedCodexRecord,
    *,
    now: datetime,
    registry_path: Path,
    bell_events: dict[str, Any],
    branch_resolver: Callable[[str], str | None],
    process_checker: Callable[[int], bool],
    tmux_session_checker: Callable[[str], bool],
    tmux_bell_checker: Callable[[str], bool],
    tmux_pane_reader: Callable[[str], str | None],
) -> CodexSessionSummary:
    started_at = _parse_timestamp(record.started_at) or now
    age_seconds = max(0, int((now - started_at).total_seconds()))
    managed_terminal_excerpt = None
    if record.backend == "tmux":
        is_running = bool(record.tmux_session and tmux_session_checker(record.tmux_session))
        if is_running and record.tmux_session:
            managed_terminal_excerpt = _shorten_optional(
                tmux_pane_reader(record.tmux_session),
                limit=500,
            )
        bell_event = bell_events.get(record.tmux_session or "")
        managed_bell = bool(
            is_running
            and record.tmux_session
            and (tmux_bell_checker(record.tmux_session) or bell_event is not None)
        )
        managed_bell_event_at = bell_event.created_at if bell_event is not None else None
        status = "working" if is_running else "exited"
        reason = (
            "Supervisor 托管 tmux 会话仍在运行"
            if is_running
            else "Supervisor 托管 tmux 会话已退出"
        )
        status_evidence = (
            {
                "source": "tmux_bell",
                "label": "tmux 响铃",
                "detail": f"检测到 bell 信号：{managed_bell_event_at or record.tmux_session}",
            }
            if managed_bell
            else {
                "source": "managed_tmux",
                "label": "托管 tmux 状态",
                "detail": "tmux 会话仍在运行" if is_running else "tmux 会话已退出",
            }
        )
    else:
        is_running = process_checker(record.pid)
        managed_bell = False
        managed_bell_event_at = None
        status = "working" if is_running else "exited"
        reason = "Supervisor 托管进程已启动" if is_running else "Supervisor 托管进程已退出"
        status_evidence = {
            "source": "managed_process",
            "label": "托管进程状态",
            "detail": f"pid {record.pid} 仍在运行" if is_running else f"pid {record.pid} 已退出",
        }
    return CodexSessionSummary(
        session_id=f"managed:{record.record_id}",
        cwd=record.cwd,
        git_branch=branch_resolver(record.cwd) if record.cwd else None,
        source_path=str(registry_path),
        last_event_at=started_at.isoformat(),
        age_seconds=age_seconds,
        status=status,
        reason=reason,
        status_evidence=status_evidence,
        last_user_message=record.prompt,
        managed=True,
        managed_name=record.name,
        managed_pid=record.pid,
        managed_log_path=record.log_path,
        managed_backend=record.backend,
        managed_tmux_session=record.tmux_session,
        managed_terminal_excerpt=managed_terminal_excerpt,
        managed_bell=managed_bell,
        managed_bell_event_at=managed_bell_event_at,
    )


def _supervisor_protocol_from_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    keys = {
        "SUPERVISOR_STATUS": "status",
        "SUPERVISOR_SUMMARY": "summary",
        "SUPERVISOR_NEXT": "next",
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().upper()
        if normalized_key not in keys:
            continue
        normalized_value = value.strip()
        if normalized_value:
            values[keys[normalized_key]] = normalized_value
    return values


def _message_from_event(event: dict[str, Any]) -> tuple[str | None, str | None]:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None, None
    if event.get("type") == "event_msg":
        return None, _optional_string(payload.get("message"))
    if event.get("type") != "response_item":
        return None, None
    if payload.get("type") != "message":
        return None, None
    role = _optional_string(payload.get("role"))
    return role, _content_text(payload.get("content"))


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts) if parts else None


def _classify_session(
    *,
    age_seconds: int,
    last_assistant_message: str | None,
    last_text: str | None,
    stale_after_seconds: int,
    active_within_seconds: int,
) -> tuple[str, str, dict[str, str]]:
    text = (last_text or "").lower()
    if _looks_like_error_signal(text):
        return (
            "error",
            "最近事件包含错误信号",
            {
                "source": "error_marker",
                "label": "文本命中错误",
                "detail": "最近事件包含错误类表达",
            },
        )
    assistant_text = (last_assistant_message or "").lower()
    if _looks_like_user_prompt(assistant_text):
        return (
            "needs_user",
            "最近回复像是在等待用户确认",
            {
                "source": "attention_marker",
                "label": "文本命中等待用户",
                "detail": "最近回复包含确认类表达",
            },
        )
    if age_seconds >= stale_after_seconds:
        return (
            "stale",
            f"超过 {stale_after_seconds // 60} 分钟没有新事件",
            {
                "source": "stale_timeout",
                "label": "超过静默阈值",
                "detail": f"{age_seconds} 秒没有新事件，阈值 {stale_after_seconds} 秒",
            },
        )
    if age_seconds <= active_within_seconds:
        return (
            "working",
            "最近仍有 Codex 事件",
            {
                "source": "recent_event",
                "label": "最近仍有事件",
                "detail": f"{age_seconds} 秒前有新事件",
            },
        )
    return (
        "idle",
        "暂时没有明显异常",
        {
            "source": "idle_window",
            "label": "未命中异常规则",
            "detail": f"{age_seconds} 秒没有新事件，未超过阈值 {stale_after_seconds} 秒",
        },
    )


def _supervisor_status_evidence(status: str) -> dict[str, str]:
    return {
        "source": "supervisor_protocol",
        "label": "主动状态协议",
        "detail": f"SUPERVISOR_STATUS: {status}",
    }


def _recommendation(
    sessions: tuple[CodexSessionSummary, ...],
) -> SupervisorActionRecommendation:
    if session := _first_session_with_supervisor_status(sessions, "blocked"):
        return _session_recommendation(
            session,
            action="inspect_blocked",
            label="先查看主动汇报阻塞的窗口。",
            priority="high",
            reason=session.supervisor_summary,
        )
    if session := _first_session_with_supervisor_status(sessions, "needs_user"):
        return _session_recommendation(
            session,
            action="review_user_prompt",
            label="先处理主动等待用户确认的窗口。",
            priority="high",
            reason=session.supervisor_summary,
        )
    if session := _first_session_with_status(sessions, "needs_user"):
        return _session_recommendation(
            session,
            action="review_user_prompt",
            label="先处理等待用户确认的窗口。",
            priority="high",
        )
    if session := _first_session_with_status(sessions, "error"):
        return _session_recommendation(
            session,
            action="inspect_error",
            label="先查看疑似报错的窗口。",
            priority="high",
        )
    if session := _first_session_with_bell(sessions):
        return _session_recommendation(
            session,
            action="inspect_bell",
            label="查看刚响铃的托管窗口。",
            priority="medium",
            reason=f"tmux bell event at {session.managed_bell_event_at}"
            if session.managed_bell_event_at
            else "tmux bell flag is set",
        )
    if session := _first_session_with_supervisor_status(sessions, "done"):
        return _session_recommendation(
            session,
            action="review_done",
            label="先审阅已完成的窗口。",
            priority="medium",
            reason=session.supervisor_summary,
        )
    if session := _first_session_with_status(sessions, "stale"):
        return _session_recommendation(
            session,
            action="inspect_stale",
            label="检查长时间没有新事件的窗口。",
            priority="medium",
        )
    return SupervisorActionRecommendation(
        action="monitor",
        label="当前没有明显需要介入的窗口。",
        priority="low",
    )


def _first_session_with_status(
    sessions: tuple[CodexSessionSummary, ...], status: str
) -> CodexSessionSummary | None:
    for session in sessions:
        if session.status == status:
            return session
    return None


def _first_session_with_supervisor_status(
    sessions: tuple[CodexSessionSummary, ...], status: str
) -> CodexSessionSummary | None:
    for session in sessions:
        if (session.supervisor_status or "").lower() == status:
            return session
    return None


def _first_session_with_bell(
    sessions: tuple[CodexSessionSummary, ...],
) -> CodexSessionSummary | None:
    for session in sessions:
        if session.managed_bell:
            return session
    return None


def _session_recommendation(
    session: CodexSessionSummary,
    *,
    action: str,
    label: str,
    priority: str,
    reason: str | None = None,
) -> SupervisorActionRecommendation:
    return SupervisorActionRecommendation(
        action=action,
        label=label,
        priority=priority,
        reason=reason or session.reason,
        target_session_id=session.session_id,
        target_name=session.managed_name,
    )


def _looks_like_user_prompt(text: str) -> bool:
    if any(marker in text for marker in ATTENTION_MARKERS):
        return True
    return "下一步" in text and ("继续" in text or "怎么做" in text or "做什么" in text)


def _looks_like_error_signal(text: str) -> bool:
    return any(marker in text for marker in ERROR_MARKERS)


def _git_branch_for(cwd: str) -> str | None:
    path = Path(cwd).expanduser()
    if not path.exists():
        return None
    completed = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    branch = completed.stdout.strip()
    return branch or None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _tmux_session_exists(session: str) -> bool:
    if not session:
        return False
    completed = subprocess.run(
        ["tmux", "has-session", "-t", session],
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def _tmux_window_has_bell(session: str) -> bool:
    if not session:
        return False
    completed = subprocess.run(
        ["tmux", "display-message", "-p", "-t", session, "#{window_bell_flag}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    return completed.stdout.strip() == "1"


def _tmux_capture_pane(session: str) -> str | None:
    if not session:
        return None
    try:
        completed = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", session, "-S", "-80"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _empty_tmux_pane(session: str) -> str | None:
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _ensure_aware_utc(datetime.fromisoformat(normalized))
    except ValueError:
        return None


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _shorten(text: str, *, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _shorten_optional(text: str | None, *, limit: int = 120) -> str | None:
    if text is None:
        return None
    return _shorten(text, limit=limit)


def _title_from_user_message(text: str | None) -> str | None:
    if text is None:
        return None
    return _shorten(text, limit=48)


def _is_title_noise(text: str) -> bool:
    compact = text.lstrip()
    noise_prefixes = (
        "# AGENTS.md instructions",
        "<environment_context>",
        "<permissions instructions>",
        "<INSTRUCTIONS>",
    )
    return compact.startswith(noise_prefixes)
