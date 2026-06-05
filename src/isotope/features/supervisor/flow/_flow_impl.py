"""Codex session supervisor flow."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from isotope.integrations.codex.session_reader import (
    find_codex_session_paths,
    merge_recent_session_ids,
    read_codex_session,
    read_codex_session_index,
    read_codex_state_threads,
)

from ..notifications.bell_events import default_bell_events_path, read_latest_bell_events
from ..state.lane_state import read_lane_states
from ..registry import ManagedCodexRecord, default_registry_path, read_managed_records
from ..registry.session_lookup import find_codex_session_snapshot


STATUS_LABELS = {
    "working": "工作中",
    "needs_user": "等待用户",
    "done": "已完成",
    "blocked": "阻塞",
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
SUPERVISOR_STATUS_VALUES = {"working", "done", "blocked", "needs_user"}
MANAGED_LOG_TAIL_READ_BYTES = 64 * 1024


@dataclass(frozen=True)
class CodexSessionSummary:
    session_id: str
    cwd: str
    source_path: str
    last_event_at: str
    age_seconds: int
    status: str
    reason: str
    source_size_bytes: int | None = None
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
    managed_terminal_ready: bool = False
    managed_bell: bool = False
    managed_bell_event_at: str | None = None
    managed_bell_hook_installed: bool | None = None
    managed_resume_session_id: str | None = None
    managed_resume_last: bool = False
    managed_failure: dict[str, Any] | None = None
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
            "source_size_bytes": self.source_size_bytes,
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
            "managed_terminal_excerpt": self.managed_terminal_excerpt,
            "managed_terminal_ready": self.managed_terminal_ready,
            "managed_bell": self.managed_bell,
            "managed_bell_event_at": self.managed_bell_event_at,
            "managed_bell_hook_installed": self.managed_bell_hook_installed,
            "managed_resume_session_id": self.managed_resume_session_id,
            "managed_resume_last": self.managed_resume_last,
            "managed_failure": self.managed_failure,
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
    """Build a state projection report from local Codex session files."""

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
        tmux_bell_hook_checker: Callable[[str], bool | None] | None = None,
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
        self.tmux_bell_hook_checker = tmux_bell_hook_checker or _tmux_bell_hook_installed
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
        session_index = read_codex_session_index(self.codex_home / "session_index.jsonl")
        state_threads = read_codex_state_threads(self.codex_home / "state_5.sqlite")
        session_titles = {**session_index.titles, **state_threads.titles}
        recent_session_ids = merge_recent_session_ids(
            state_threads.recent_session_ids,
            session_index.recent_session_ids,
        )
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
                tmux_bell_hook_checker=self.tmux_bell_hook_checker,
                tmux_pane_reader=self.tmux_pane_reader,
                stale_after_seconds=stale_after_seconds,
                active_within_seconds=active_within_seconds,
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
        return find_codex_session_paths(
            self.codex_home,
            limit=limit,
            recent_session_ids=recent_session_ids,
        )


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
            bell_hook = (
                f" bell hook={_bell_hook_label(session.managed_bell_hook_installed)}"
                if session.managed_backend == "tmux"
                else ""
            )
            terminal = (
                f" 终端={'可输入' if session.managed_terminal_ready else '运行中'}"
                if session.managed_backend == "tmux"
                else ""
            )
            name = session.managed_name or "未命名"
            lines.append(
                f"   托管：{name}{pid}{backend}{tmux}{bell}{bell_hook}{terminal}"
            )
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


def _bell_hook_label(value: bool | None) -> str:
    if value is True:
        return "已安装"
    if value is False:
        return "未安装"
    return "未确认"


def _read_session_summary(
    path: Path,
    *,
    now: datetime,
    stale_after_seconds: int,
    active_within_seconds: int,
    branch_resolver: Callable[[str], str | None],
    session_index_titles: dict[str, str] | None = None,
) -> CodexSessionSummary | None:
    last_user_message: str | None = None
    first_user_message: str | None = None
    last_assistant_message: str | None = None
    last_text: str | None = None
    supervisor_status: str | None = None
    supervisor_summary: str | None = None
    supervisor_next: str | None = None
    thread_name: str | None = None
    thread_id: str | None = None
    snapshot = read_codex_session(path)
    if snapshot is None:
        return None
    for message in snapshot.messages:
        last_text = message.text
        if message.role == "user":
            if first_user_message is None and not _is_title_noise(message.text):
                first_user_message = message.text
            last_user_message = message.text
        if message.role == "assistant":
            protocol = _supervisor_protocol_from_text(message.text)
            supervisor_status = protocol.get("status") or supervisor_status
            supervisor_summary = protocol.get("summary") or supervisor_summary
            supervisor_next = protocol.get("next") or supervisor_next
            last_assistant_message = message.text
    session_id = snapshot.session_id
    for update in snapshot.thread_updates:
        if update.thread_id is None or update.thread_id == session_id:
            thread_name = update.thread_name
            thread_id = update.thread_id
    if thread_name is None and session_index_titles:
        thread_name = session_index_titles.get(session_id)
    last_event_at = snapshot.last_event_at or now
    cwd = snapshot.cwd
    age_seconds = max(0, int((now - last_event_at).total_seconds()))
    status, reason, status_evidence = _classify_session(
        age_seconds=age_seconds,
        last_assistant_message=last_assistant_message,
        last_text=last_text,
        stale_after_seconds=stale_after_seconds,
        active_within_seconds=active_within_seconds,
    )
    if supervisor_status:
        status = supervisor_status
        reason = supervisor_summary or _supervisor_status_reason(supervisor_status)
        status_evidence = _supervisor_status_evidence(supervisor_status)
    return CodexSessionSummary(
        session_id=session_id,
        cwd=cwd,
        git_branch=branch_resolver(cwd) if cwd else None,
        source_path=str(path),
        source_size_bytes=snapshot.source_size_bytes,
        last_event_at=last_event_at.isoformat(),
        age_seconds=age_seconds,
        status=status,
        reason=reason,
        status_evidence=status_evidence,
        thread_name=thread_name,
        thread_id=thread_id,
        initial_user_title=_title_from_user_message(first_user_message),
        agent_nickname=_optional_string(snapshot.meta.get("agent_nickname")),
        agent_role=_optional_string(snapshot.meta.get("agent_role")),
        last_user_message=last_user_message,
        last_assistant_message=last_assistant_message,
        cli_version=_optional_string(snapshot.meta.get("cli_version")),
        model_provider=_optional_string(snapshot.meta.get("model_provider")),
        supervisor_status=supervisor_status,
        supervisor_summary=supervisor_summary,
        supervisor_next=supervisor_next,
    )


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
    tmux_bell_hook_checker: Callable[[str], bool | None],
    tmux_pane_reader: Callable[[str], str | None],
    stale_after_seconds: int,
    active_within_seconds: int,
) -> CodexSessionSummary:
    started_at = _parse_timestamp(record.started_at) or now
    age_seconds = max(0, int((now - started_at).total_seconds()))
    managed_terminal_excerpt = None
    managed_terminal_ready = False
    supervisor_status: str | None = None
    supervisor_summary: str | None = None
    supervisor_next: str | None = None
    managed_failure = _managed_failure_payload(record, registry_path=registry_path)
    if record.backend == "codex_session":
        codex_home = registry_path.parent.parent
        snapshot = (
            find_codex_session_snapshot(
                codex_home=codex_home,
                session_id=record.resume_session_id or "",
            )
            if record.resume_session_id
            else None
        )
        adopted = (
            _read_session_summary(
                snapshot.source_path,
                now=now,
                stale_after_seconds=stale_after_seconds,
                active_within_seconds=active_within_seconds,
                branch_resolver=branch_resolver,
            )
            if snapshot is not None
            else None
        )
        managed_bell = False
        managed_bell_event_at = None
        managed_bell_hook_installed = None
        if adopted is not None:
            status = adopted.status
            reason = adopted.reason
            status_evidence = adopted.status_evidence
            managed_terminal_excerpt = adopted.last_assistant_message
            supervisor_status = adopted.supervisor_status
            supervisor_summary = adopted.supervisor_summary
            supervisor_next = adopted.supervisor_next
        else:
            status = "stale"
            reason = "Supervisor 已接管 Codex session，但本地会话文件不可用"
            status_evidence = {
                "source": "adopted_codex_session",
                "label": "接管会话记录",
                "detail": record.resume_session_id or record.record_id,
            }
    elif record.backend == "tmux":
        is_running = bool(record.tmux_session and tmux_session_checker(record.tmux_session))
        if is_running and record.tmux_session:
            managed_terminal_excerpt = _terminal_tail_excerpt(
                tmux_pane_reader(record.tmux_session),
            )
            managed_terminal_ready = _terminal_ready_for_input(managed_terminal_excerpt)
        bell_event = bell_events.get(record.tmux_session or "")
        managed_bell = bool(
            is_running
            and record.tmux_session
            and (tmux_bell_checker(record.tmux_session) or bell_event is not None)
        )
        managed_bell_event_at = bell_event.created_at if bell_event is not None else None
        managed_bell_hook_installed = (
            tmux_bell_hook_checker(record.tmux_session)
            if is_running and record.tmux_session
            else False
        )
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
        managed_terminal_excerpt = _managed_process_log_excerpt(record.log_path)
        if managed_terminal_excerpt:
            protocol = _supervisor_protocol_from_text(managed_terminal_excerpt)
            supervisor_status = protocol.get("status")
            supervisor_summary = protocol.get("summary")
            supervisor_next = protocol.get("next")
        managed_bell = False
        managed_bell_event_at = None
        managed_bell_hook_installed = None
        status = "working" if is_running else "exited"
        reason = "Supervisor 托管进程已启动" if is_running else "Supervisor 托管进程已退出"
        status_evidence = {
            "source": "managed_process",
            "label": "托管进程状态",
            "detail": f"pid {record.pid} 仍在运行" if is_running else f"pid {record.pid} 已退出",
        }
    if supervisor_status and (supervisor_status != "working" or status == "working"):
        status = supervisor_status
        reason = supervisor_summary or _supervisor_status_reason(supervisor_status)
        status_evidence = _supervisor_status_evidence(supervisor_status)
    if managed_failure is not None:
        status = "error"
        reason = f"worker failed: {managed_failure['reason']}"
        status_evidence = {
            "source": "managed_worker_failure",
            "label": "托管 worker 失败",
            "detail": _managed_failure_detail(managed_failure),
        }
    return CodexSessionSummary(
        session_id=f"managed:{record.record_id}",
        cwd=record.cwd,
        git_branch=branch_resolver(record.cwd) if record.cwd else None,
        source_path=str(registry_path),
        source_size_bytes=None,
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
        managed_terminal_ready=managed_terminal_ready,
        managed_bell=managed_bell,
        managed_bell_event_at=managed_bell_event_at,
        managed_bell_hook_installed=managed_bell_hook_installed,
        managed_resume_session_id=record.resume_session_id,
        managed_resume_last=record.resume_last,
        managed_failure=managed_failure,
        supervisor_status=supervisor_status,
        supervisor_summary=supervisor_summary,
        supervisor_next=supervisor_next,
    )


def _managed_failure_payload(
    record: ManagedCodexRecord,
    *,
    registry_path: Path,
) -> dict[str, Any] | None:
    state_path = registry_path.parent / "lane_state.json"
    state = read_lane_states(state_path).get(record.name)
    if state is None or state.last_status != "failed" or not state.last_failure_reason:
        return None
    if state.last_failure_record_id and state.last_failure_record_id != record.record_id:
        return None
    payload: dict[str, Any] = {
        "reason": state.last_failure_reason,
        "exit_code": state.last_failure_exit_code,
        "stderr_summary": state.last_failure_stderr_summary,
        "record_id": state.last_failure_record_id,
        "failed_at": state.last_failed_at,
    }
    return payload


def _managed_failure_detail(failure: dict[str, Any]) -> str:
    reason = failure.get("reason")
    exit_code = failure.get("exit_code")
    summary = failure.get("stderr_summary")
    parts = [str(reason)]
    if isinstance(exit_code, int):
        parts.append(f"exit_code={exit_code}")
    if isinstance(summary, str) and summary:
        parts.append(_shorten(summary, limit=96))
    return " / ".join(parts)


def _managed_process_log_excerpt(log_path: str | None) -> str | None:
    if not log_path:
        return None
    path = Path(log_path).expanduser()
    try:
        size = path.stat().st_size
    except OSError:
        return None
    try:
        with path.open("rb") as handle:
            if size > MANAGED_LOG_TAIL_READ_BYTES:
                handle.seek(size - MANAGED_LOG_TAIL_READ_BYTES)
            data = handle.read()
    except OSError:
        return None
    return _terminal_tail_excerpt(data.decode("utf-8", errors="ignore"))


def _supervisor_protocol_from_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    current_protocol: dict[str, str] | None = None
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
        if normalized_key == "SUPERVISOR_STATUS":
            normalized_value = normalized_value.lower()
            if normalized_value not in SUPERVISOR_STATUS_VALUES:
                current_protocol = None
                continue
            current_protocol = {"status": normalized_value}
            values = current_protocol
            continue
        if current_protocol is None:
            continue
        if normalized_value:
            current_protocol[keys[normalized_key]] = normalized_value
    return values


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


def _supervisor_status_reason(status: str) -> str:
    return {
        "working": "托管窗口主动汇报仍在工作",
        "done": "托管窗口主动汇报已完成",
        "blocked": "托管窗口主动汇报已阻塞",
        "needs_user": "托管窗口主动汇报需要用户处理",
    }.get(status, f"托管窗口主动汇报状态：{status}")


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


def _tmux_bell_hook_installed(session: str) -> bool:
    if not session:
        return False
    completed = subprocess.run(
        ["tmux", "show-hooks", "-t", session],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    return "alert-bell" in completed.stdout and "bell_events.jsonl" in completed.stdout


def _tmux_capture_pane(session: str) -> str | None:
    if not session:
        return None
    try:
        completed = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", session, "-S", "-80", "-E", "-"],
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


def _terminal_tail_excerpt(
    text: str | None,
    *,
    max_lines: int = 40,
    limit: int = 2400,
) -> str | None:
    if text is None:
        return None
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    anchor_index = _terminal_anchor_line_index(lines)
    anchored = anchor_index is not None and anchor_index < max(0, len(lines) - max_lines)
    if anchored and anchor_index is not None:
        anchor_count = min(10, max(4, max_lines // 3))
        tail_count = max_lines - anchor_count - 1
        anchor_end = min(len(lines), anchor_index + anchor_count)
        tail_start = max(anchor_end, len(lines) - tail_count)
        tail_lines = lines[anchor_index:anchor_end]
        if tail_start > anchor_end:
            tail_lines.append(f"... 已省略中间 {tail_start - anchor_end} 行")
        tail_lines.extend(lines[tail_start:])
        omitted_lines = anchor_index
    else:
        omitted_lines = max(0, len(lines) - max_lines)
        tail_lines = lines[-max_lines:]
    excerpt = "\n".join(tail_lines)
    if len(excerpt) > limit:
        if anchored:
            head_limit = min(800, limit // 3)
            marker = "\n... 已省略中间若干字符\n"
            tail_limit = max(0, limit - head_limit - len(marker))
            excerpt = excerpt[:head_limit].rstrip() + marker + excerpt[-tail_limit:].lstrip()
        else:
            excerpt = excerpt[-limit:].lstrip()
    if omitted_lines:
        excerpt = f"... 已省略前面 {omitted_lines} 行\n{excerpt}"
    return excerpt


def _terminal_ready_for_input(text: str | None) -> bool:
    if not text:
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if _terminal_has_active_work_marker(lines[-8:]):
        return False
    last_prompt = -1
    last_assistant_marker = -1
    for index, line in enumerate(lines):
        if line.startswith("›"):
            last_prompt = index
        if line.startswith("•"):
            last_assistant_marker = index
    if last_prompt < 0 or last_prompt <= last_assistant_marker:
        return False
    return last_prompt >= max(0, len(lines) - 4)


def _terminal_has_active_work_marker(lines: list[str]) -> bool:
    for line in lines:
        compact = line.casefold()
        if compact.startswith("◦ working") or (
            "working" in compact and "esc to interrupt" in compact
        ):
            return True
    return False


def _terminal_anchor_line_index(lines: list[str]) -> int | None:
    markers = (
        "thread renamed to",
        ">_ openai codex",
        "openai codex",
        "tip: use /copy",
    )
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].casefold()
        if any(marker in line for marker in markers):
            return index
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
