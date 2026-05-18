"""Read-only tmux discovery helpers for Codex Supervisor."""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

TMUX_SESSION_FORMAT = "#{session_name}\t#{session_attached}\t#{session_windows}"
CODEX_PANE_MARKERS = (
    "openai codex",
    "supervisor_status:",
    "gpt-5",
    "gpt-4",
    "context ",
)


@dataclass(frozen=True)
class TmuxAdoptCandidate:
    tmux_session: str
    suggested_name: str
    cwd: str
    attached: bool
    windows: int | None
    looks_like_codex: bool
    reason: str
    adopt_command: str
    attach_command: str
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tmux_session": self.tmux_session,
            "suggested_name": self.suggested_name,
            "cwd": self.cwd,
            "attached": self.attached,
            "windows": self.windows,
            "looks_like_codex": self.looks_like_codex,
            "reason": self.reason,
            "adopt_command": self.adopt_command,
            "attach_command": self.attach_command,
            "excerpt": self.excerpt,
        }


def discover_tmux_adopt_candidates(
    *,
    cwd: Path | str,
    include_all: bool = False,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[TmuxAdoptCandidate, ...]:
    workspace = Path(cwd).expanduser()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    completed = _run_tmux(
        run,
        ["tmux", "list-sessions", "-F", TMUX_SESSION_FORMAT],
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        if "no server running" in message.casefold():
            return ()
        raise ValueError(f"tmux discovery failed: {message or 'list-sessions failed'}")

    candidates: list[TmuxAdoptCandidate] = []
    for line in completed.stdout.splitlines():
        session = _session_from_tmux_line(line)
        if session is None:
            continue
        excerpt = _capture_tmux_pane(run, session["tmux_session"])
        candidate_cwd = _capture_tmux_cwd(
            run,
            session["tmux_session"],
            fallback=workspace,
        )
        looks_like_codex = _looks_like_codex_pane(excerpt)
        if not include_all and not looks_like_codex:
            continue
        reason = (
            "pane text looks like Codex"
            if looks_like_codex
            else "pane text does not look like Codex"
        )
        suggested_name = _suggest_managed_name(session["tmux_session"])
        candidates.append(
            TmuxAdoptCandidate(
                tmux_session=session["tmux_session"],
                suggested_name=suggested_name,
                cwd=str(candidate_cwd),
                attached=bool(session["attached"]),
                windows=session["windows"],
                looks_like_codex=looks_like_codex,
                reason=reason,
                adopt_command=shlex.join(
                    [
                        "isotope-supervisor",
                        "adopt",
                        "--name",
                        suggested_name,
                        "--cwd",
                        str(candidate_cwd),
                        "--tmux-session",
                        session["tmux_session"],
                    ]
                ),
                attach_command=shlex.join(
                    ["tmux", "attach", "-t", session["tmux_session"]]
                ),
                excerpt=_trim_excerpt(excerpt),
            )
        )
    return tuple(candidates)


def _run_tmux(
    run: Callable[..., subprocess.CompletedProcess[str]],
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    try:
        return run(command, check=False, text=True, capture_output=True)
    except OSError as exc:
        raise ValueError(f"tmux discovery failed: {exc}") from exc


def _session_from_tmux_line(line: str) -> dict[str, Any] | None:
    parts = line.split("\t")
    if len(parts) < 3 or not parts[0].strip():
        return None
    return {
        "tmux_session": parts[0].strip(),
        "attached": parts[1].strip() == "1",
        "windows": _int_or_none(parts[2].strip()),
    }


def _capture_tmux_pane(
    run: Callable[..., subprocess.CompletedProcess[str]],
    tmux_session: str,
) -> str:
    completed = _run_tmux(
        run,
        ["tmux", "capture-pane", "-p", "-t", tmux_session, "-S", "-80", "-E", "-"],
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout


def _capture_tmux_cwd(
    run: Callable[..., subprocess.CompletedProcess[str]],
    tmux_session: str,
    *,
    fallback: Path,
) -> Path:
    completed = _run_tmux(
        run,
        ["tmux", "display-message", "-p", "-t", tmux_session, "#{pane_current_path}"],
    )
    if completed.returncode != 0:
        return fallback
    path = Path(completed.stdout.strip()).expanduser()
    return path if path.is_dir() else fallback


def _looks_like_codex_pane(text: str) -> bool:
    normalized = text.casefold()
    return any(marker in normalized for marker in CODEX_PANE_MARKERS)


def _suggest_managed_name(tmux_session: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9]+", "-", tmux_session.strip()).strip("-").casefold()
    return name or "lane-a"


def _trim_excerpt(text: str, *, max_lines: int = 8) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines[-max_lines:])


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
