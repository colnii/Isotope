"""Supervisor project context capability."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SKIPPED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".worktrees",
    "__pycache__",
    "node_modules",
}
SEARCH_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".json", ".txt"}


@dataclass(frozen=True)
class ContextItem:
    path: str
    line: int
    text: str
    score: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "text": self.text,
            "score": self.score,
        }


@dataclass(frozen=True)
class ContextResult:
    result_id: str
    cwd: str
    query: str
    created_at: str
    items: tuple[ContextItem, ...]
    backend: str = "python"

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "cwd": self.cwd,
            "query": self.query,
            "created_at": self.created_at,
            "backend": self.backend,
            "items": [item.to_dict() for item in self.items],
        }


def default_context_results_path(codex_home: Path | str) -> Path:
    return Path(codex_home).expanduser() / "supervisor" / "context_results.jsonl"


def request_project_context(
    *,
    codex_home: Path | str,
    cwd: Path | str,
    query: str,
    max_results: int = 5,
    now: Callable[[], datetime] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    rg_bin: str | None = "auto",
) -> ContextResult:
    workspace = Path(cwd).expanduser()
    query_text = query.strip()
    if not workspace.is_dir():
        raise ValueError(f"cwd must be an existing directory: {workspace}")
    if not query_text:
        raise ValueError("query must not be empty")
    if max_results <= 0:
        raise ValueError("max_results must be positive")

    items, backend = _search_workspace(
        workspace,
        query_text,
        max_results=max_results,
        run=run,
        rg_bin=rg_bin,
    )
    result = ContextResult(
        result_id="context-" + uuid.uuid4().hex[:12],
        cwd=str(workspace),
        query=query_text,
        created_at=_ensure_aware_utc((now or _utc_now)()).isoformat(),
        items=tuple(items),
        backend=backend,
    )
    append_context_result(default_context_results_path(codex_home), result)
    return result


def read_recent_context_results(
    *,
    codex_home: Path | str,
    cwd: Path | str | None = None,
    limit: int = 3,
) -> tuple[ContextResult, ...]:
    path = default_context_results_path(codex_home)
    if not path.is_file():
        return ()
    cwd_text = str(Path(cwd).expanduser()) if cwd is not None else None
    results: list[ContextResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        result = _result_from_dict(raw)
        if result is None:
            continue
        if cwd_text is not None and result.cwd != cwd_text:
            continue
        results.append(result)
    return tuple(results[-limit:])


def append_context_result(path: Path | str, result: ContextResult) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _search_workspace(
    workspace: Path,
    query: str,
    *,
    max_results: int,
    run: Callable[..., subprocess.CompletedProcess[str]],
    rg_bin: str | None,
) -> tuple[list[ContextItem], str]:
    rg_items = _search_workspace_with_rg(
        workspace,
        query,
        max_results=max_results,
        run=run,
        rg_bin=rg_bin,
    )
    if rg_items is not None:
        return rg_items, "rg"
    return _search_workspace_with_python(workspace, query, max_results=max_results), "python"


def _search_workspace_with_python(
    workspace: Path,
    query: str,
    *,
    max_results: int,
) -> list[ContextItem]:
    query_lower = query.lower()
    terms = _query_terms(query)
    candidates: list[ContextItem] = []
    for file_path in _candidate_files(workspace):
        relative = file_path.relative_to(workspace).as_posix()
        path_score = _score_text(relative.lower(), query_lower, terms)
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            text = " ".join(line.split())
            if not text:
                continue
            line_score = _score_text(text.lower(), query_lower, terms)
            score = line_score + path_score
            if score <= 0:
                continue
            candidates.append(
                ContextItem(
                    path=relative,
                    line=line_number,
                    text=_clip(text),
                    score=score,
                )
            )
    candidates.sort(key=lambda item: (-item.score, item.path, item.line))
    return candidates[:max_results]


def _search_workspace_with_rg(
    workspace: Path,
    query: str,
    *,
    max_results: int,
    run: Callable[..., subprocess.CompletedProcess[str]],
    rg_bin: str | None,
) -> list[ContextItem] | None:
    if rg_bin is None:
        return None
    executable = shutil.which("rg") if rg_bin == "auto" else rg_bin
    if not executable:
        return None
    terms = _query_terms(query)
    if not terms:
        return None
    pattern = "|".join(re.escape(term) for term in terms)
    command = [
        executable,
        "--json",
        "--line-number",
        "--ignore-case",
        "--glob",
        "!.git/**",
        "--glob",
        "!.venv/**",
        "--glob",
        "!.worktrees/**",
        "--glob",
        "!node_modules/**",
        "--glob",
        "!__pycache__/**",
        "-e",
        pattern,
        ".",
    ]
    try:
        completed = run(
            command,
            cwd=str(workspace),
            text=True,
            capture_output=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode not in {0, 1}:
        return None
    candidates = _context_items_from_rg_json(completed.stdout, query)
    candidates.sort(key=lambda item: (-item.score, item.path, item.line))
    return candidates[:max_results]


def _context_items_from_rg_json(output: str, query: str) -> list[ContextItem]:
    query_lower = query.lower()
    terms = _query_terms(query)
    items: list[ContextItem] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "match":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        path = _rg_text(data.get("path"))
        line_text = _rg_text(data.get("lines"))
        line_number = data.get("line_number")
        if not path or not line_text or not isinstance(line_number, int):
            continue
        submatches = data.get("submatches")
        submatch_score = len(submatches) if isinstance(submatches, list) else 0
        score = _score_text(path.lower(), query_lower, terms)
        score += _score_text(line_text.lower(), query_lower, terms)
        score += submatch_score
        items.append(
            ContextItem(
                path=path.lstrip("./"),
                line=line_number,
                text=_clip(" ".join(line_text.split())),
                score=score,
            )
        )
    return items


def _rg_text(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    text = value.get("text")
    return text if isinstance(text, str) else None


def _candidate_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIPPED_DIRS for part in path.relative_to(workspace).parts):
            continue
        if path.suffix.lower() not in SEARCH_SUFFIXES:
            continue
        files.append(path)
        if len(files) >= 800:
            break
    return files


def _query_terms(query: str) -> list[str]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_./-]{2,}", query)]
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}", query))
    return list(dict.fromkeys(terms))


def _score_text(text: str, query: str, terms: list[str]) -> int:
    score = 0
    if query and query in text:
        score += 8
    for term in terms:
        if term.lower() in text:
            score += 2
    return score


def _result_from_dict(raw: dict[str, Any]) -> ContextResult | None:
    result_id = raw.get("result_id")
    cwd = raw.get("cwd")
    query = raw.get("query")
    created_at = raw.get("created_at")
    backend = raw.get("backend")
    raw_items = raw.get("items")
    if not all(isinstance(value, str) and value for value in (result_id, cwd, query, created_at)):
        return None
    if not isinstance(raw_items, list):
        return None
    items: list[ContextItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        line = item.get("line")
        text = item.get("text")
        score = item.get("score")
        if (
            isinstance(path, str)
            and isinstance(line, int)
            and isinstance(text, str)
            and isinstance(score, int)
        ):
            items.append(ContextItem(path=path, line=line, text=text, score=score))
    return ContextResult(
        result_id=result_id,
        cwd=cwd,
        query=query,
        created_at=created_at,
        items=tuple(items),
        backend=backend if isinstance(backend, str) and backend else "python",
    )


def _clip(text: str, *, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
