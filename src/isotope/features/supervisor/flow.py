"""Read-only Codex session supervisor flow."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


STATUS_LABELS = {
    "working": "工作中",
    "needs_user": "等待用户",
    "stale": "疑似停住",
    "error": "疑似报错",
    "idle": "空闲",
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


@dataclass(frozen=True)
class CodexSessionSummary:
    session_id: str
    cwd: str
    source_path: str
    last_event_at: str
    age_seconds: int
    status: str
    reason: str
    git_branch: str | None = None
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    cli_version: str | None = None
    model_provider: str | None = None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "source_path": self.source_path,
            "last_event_at": self.last_event_at,
            "age_seconds": self.age_seconds,
            "status": self.status,
            "status_label": self.status_label,
            "reason": self.reason,
            "last_user_message": _shorten_optional(self.last_user_message),
            "last_assistant_message": _shorten_optional(self.last_assistant_message),
            "cli_version": self.cli_version,
            "model_provider": self.model_provider,
        }


@dataclass(frozen=True)
class CodexSupervisorReport:
    generated_at: str
    sessions: tuple[CodexSessionSummary, ...]

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
            "sessions": [session.to_dict() for session in self.sessions],
        }


class CodexSupervisorFlow:
    """Build a read-only status report from local Codex session files."""

    def __init__(
        self,
        *,
        codex_home: Path | str | None = None,
        now: Callable[[], datetime] | None = None,
        branch_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.codex_home = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
        self.now = now or _utc_now
        self.branch_resolver = branch_resolver or _git_branch_for

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
        sessions = [
            summary
            for path in self._session_paths()
            if (
                summary := _read_session_summary(
                    path,
                    now=now,
                    stale_after_seconds=stale_after_seconds,
                    active_within_seconds=active_within_seconds,
                    branch_resolver=self.branch_resolver,
                )
            )
            is not None
        ]
        sessions.sort(key=lambda session: session.last_event_at, reverse=True)
        return CodexSupervisorReport(
            generated_at=now.isoformat(),
            sessions=tuple(sessions[:limit]),
        )

    def _session_paths(self) -> list[Path]:
        sessions_root = self.codex_home / "sessions"
        if not sessions_root.exists():
            return []
        return sorted(sessions_root.rglob("*.jsonl"))


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
        lines.append(f"   原因：{session.reason}")
        if session.last_user_message:
            lines.append(f"   最近用户：{_shorten(session.last_user_message)}")
        if session.last_assistant_message:
            lines.append(f"   最近回复：{_shorten(session.last_assistant_message)}")
    lines.append(f"建议：{_recommendation(report.sessions)}")
    return "\n".join(lines)


def _read_session_summary(
    path: Path,
    *,
    now: datetime,
    stale_after_seconds: int,
    active_within_seconds: int,
    branch_resolver: Callable[[str], str | None],
) -> CodexSessionSummary | None:
    meta: dict[str, Any] = {}
    last_event_at: datetime | None = None
    last_user_message: str | None = None
    last_assistant_message: str | None = None
    last_text: str | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
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
        role, text = _message_from_event(event)
        if text:
            last_text = text
            if role == "user":
                last_user_message = text
            if role == "assistant":
                last_assistant_message = text
    if not meta and last_event_at is None:
        return None
    session_id = str(meta.get("id") or path.stem)
    cwd = str(meta.get("cwd") or "")
    if last_event_at is None:
        last_event_at = _parse_timestamp(meta.get("timestamp")) or now
    age_seconds = max(0, int((now - last_event_at).total_seconds()))
    status, reason = _classify_session(
        age_seconds=age_seconds,
        last_assistant_message=last_assistant_message,
        last_text=last_text,
        stale_after_seconds=stale_after_seconds,
        active_within_seconds=active_within_seconds,
    )
    return CodexSessionSummary(
        session_id=session_id,
        cwd=cwd,
        git_branch=branch_resolver(cwd) if cwd else None,
        source_path=str(path),
        last_event_at=last_event_at.isoformat(),
        age_seconds=age_seconds,
        status=status,
        reason=reason,
        last_user_message=last_user_message,
        last_assistant_message=last_assistant_message,
        cli_version=_optional_string(meta.get("cli_version")),
        model_provider=_optional_string(meta.get("model_provider")),
    )


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
) -> tuple[str, str]:
    text = (last_text or "").lower()
    if _looks_like_error_signal(text):
        return "error", "最近事件包含错误信号"
    assistant_text = (last_assistant_message or "").lower()
    if _looks_like_user_prompt(assistant_text):
        return "needs_user", "最近回复像是在等待用户确认"
    if age_seconds >= stale_after_seconds:
        return "stale", f"超过 {stale_after_seconds // 60} 分钟没有新事件"
    if age_seconds <= active_within_seconds:
        return "working", "最近仍有 Codex 事件"
    return "idle", "暂时没有明显异常"


def _recommendation(sessions: tuple[CodexSessionSummary, ...]) -> str:
    if any(session.status == "needs_user" for session in sessions):
        return "先处理等待用户确认的窗口。"
    if any(session.status == "error" for session in sessions):
        return "先查看疑似报错的窗口。"
    if any(session.status == "stale" for session in sessions):
        return "检查长时间没有新事件的窗口。"
    return "当前没有明显需要介入的窗口。"


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
