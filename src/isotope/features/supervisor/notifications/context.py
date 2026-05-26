"""Supervisor project context capability."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ....rag.retrieval import (
    SummarySearchDocument,
    rank_summary_documents,
)


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
PROJECT_CONTEXT_ANCHOR_SCORE_BOOST = 80
PROJECT_CONTEXT_ANCHORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "docs/current/status.md",
        (
            "当前状态",
            "status",
            "状态文档",
            "项目状态",
            "AI-first",
            "产品方向",
        ),
    ),
    (
        "docs/current/supervisor-capability-map.md",
        (
            "Supervisor 能力地图",
            "能力图",
            "能力地图",
            "capability map",
            "request_context",
            "LLM planner",
            "上下文能力",
        ),
    ),
    (
        "docs/current/docs-map.md",
        (
            "docs/current",
            "文档地图",
            "docs map",
            "入口文档",
            "当前入口",
        ),
    ),
    (
        "docs/current/agent-task-queue.md",
        (
            "任务队列",
            "agent task queue",
            "下一步",
            "current queue",
        ),
    ),
    (
        "src/isotope/features/supervisor/context.py",
        (
            "request_context",
            "request_project_context",
            "ranked evidence",
            "上下文检索",
            "代码入口",
        ),
    ),
    (
        "src/isotope/features/supervisor/llm_summary.py",
        (
            "LLM planner",
            "generate_llm_action_decision",
            "request_context action",
            "ask_user gate",
            "规划器",
        ),
    ),
    (
        "src/isotope/features/supervisor/runner.py",
        (
            "isotope-supervisor",
            "supervise",
            "loop",
            "_execute_context_action",
            "CLI 入口",
        ),
    ),
)


@dataclass(frozen=True)
class ContextItem:
    path: str
    line: int
    text: str
    score: float
    title: str = ""
    snippet: str = ""
    match_reason: str = ""
    source_group: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "title": self.title,
            "text": self.text,
            "snippet": self.snippet,
            "score": self.score,
            "match_reason": self.match_reason,
            "source_group": self.source_group or _source_group_for_path(self.path),
        }


@dataclass(frozen=True)
class ContextResult:
    result_id: str
    cwd: str
    query: str
    created_at: str
    items: tuple[ContextItem, ...]
    backend: str = "bm25"

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
    del run, rg_bin
    bm25_items = _search_workspace_with_bm25(
        workspace,
        query,
        max_results=max_results,
    )
    return _with_project_context_anchors(
        workspace,
        query,
        bm25_items,
        max_results=max_results,
    ), "bm25"


def _search_workspace_with_bm25(
    workspace: Path,
    query: str,
    *,
    max_results: int,
) -> list[ContextItem]:
    documents = _build_bm25_context_index(workspace)
    terms = _query_terms(query)
    try:
        hits = rank_summary_documents(query, documents)
    except ValueError:
        return []
    items: list[ContextItem] = []
    ranked_hits = sorted(
        hits,
        key=lambda hit: (-hit.score, hit.document.document_id),
    )
    for hit in ranked_hits[: max(max_results * 4, 20)]:
        metadata = hit.document.metadata or {}
        item = metadata.get("item")
        if not isinstance(item, ContextItem):
            continue
        items.append(
            ContextItem(
                path=item.path,
                line=item.line,
                text=item.text,
                score=round(float(hit.score) + float(item.score) / 10.0, 4),
                title=item.title,
                snippet=item.snippet,
                match_reason=_match_reason(
                    path=item.path,
                    title=item.title,
                    snippet=item.snippet,
                    terms=terms,
                    source_group=item.source_group,
                ),
                source_group=item.source_group,
            )
        )
    return items


def _build_bm25_context_index(workspace: Path) -> list[SummarySearchDocument]:
    documents: list[SummarySearchDocument] = []
    title_cache: dict[str, str] = {}
    for file_path in _candidate_files(workspace):
        relative = file_path.relative_to(workspace).as_posix()
        source_group = _source_group_for_path(relative)
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            text = " ".join(line.split())
            if not text:
                continue
            snippet = _clip(text)
            title = _title_for_path(
                workspace,
                relative,
                fallback_text=snippet,
                title_cache=title_cache,
            )
            item = ContextItem(
                path=relative,
                line=line_number,
                text=snippet,
                score=0.0,
                title=title,
                snippet=snippet,
                match_reason=_match_reason(
                    path=relative,
                    title=title,
                    snippet=snippet,
                    terms=[],
                    source_group=source_group,
                ),
                source_group=source_group,
            )
            documents.append(
                SummarySearchDocument(
                    document_id=f"{relative}:{line_number}",
                    title=title,
                    summary=_bm25_context_document_text(item),
                    metadata={"item": item, "source_group": source_group},
                )
            )
    return documents


def _bm25_context_document_text(item: ContextItem) -> str:
    return " ".join(
        part
        for part in (
            item.source_group,
            item.path,
            _identifier_search_text(item.path),
            item.title,
            _identifier_search_text(item.title),
            item.snippet,
            _identifier_search_text(item.snippet),
        )
        if part
    )


def _identifier_search_text(value: str) -> str:
    words = re.findall(r"[A-Za-z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]|$)|[0-9]+", value)
    underscored = re.findall(r"[A-Za-z0-9_./-]{2,}", value)
    split_parts: list[str] = []
    for token in underscored:
        split_parts.extend(part for part in re.split(r"[_./-]+", token) if len(part) >= 2)
    return " ".join([*words, *split_parts])


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


def _rank_context_items(query: str, items: list[ContextItem]) -> list[ContextItem]:
    if not items:
        return []
    documents = [
        SummarySearchDocument(
            document_id=str(position),
            title=item.title,
            summary=(
                f"{item.source_group or _source_group_for_path(item.path)} "
                f"{item.path} {item.snippet} {item.match_reason}"
            ),
            metadata={
                "item": item,
                "base_score": item.score,
                "source_group": item.source_group,
            },
        )
        for position, item in enumerate(items)
    ]
    try:
        hits = rank_summary_documents(query, documents)
    except ValueError:
        hits = []
    if not hits:
        return sorted(items, key=lambda item: (-item.score, item.path, item.line))

    ranked: list[ContextItem] = []
    for hit in hits:
        metadata = hit.document.metadata or {}
        item = metadata.get("item")
        base_score = metadata.get("base_score", 0.0)
        if not isinstance(item, ContextItem):
            continue
        ranked.append(
            ContextItem(
                path=item.path,
                line=item.line,
                text=item.text,
                score=round(float(hit.score) + float(base_score) / 10.0, 4),
                title=item.title,
                snippet=item.snippet,
                match_reason=item.match_reason,
                source_group=item.source_group,
            )
        )
    ranked_item_ids = {(item.path, item.line, item.text) for item in ranked}
    for item in sorted(items, key=lambda item: (-item.score, item.path, item.line)):
        if (item.path, item.line, item.text) not in ranked_item_ids:
            ranked.append(item)
    return sorted(ranked, key=lambda item: (-item.score, item.path, item.line))


def _with_project_context_anchors(
    workspace: Path,
    query: str,
    items: list[ContextItem],
    *,
    max_results: int,
) -> list[ContextItem]:
    anchors = _project_context_anchor_items(workspace, query)
    combined = _dedupe_context_items([*items, *anchors])
    return _rank_context_items(query, combined)[:max_results]


def _project_context_anchor_items(workspace: Path, query: str) -> list[ContextItem]:
    query_lower = query.lower()
    terms = _query_terms(query)
    items: list[ContextItem] = []
    for relative, aliases in PROJECT_CONTEXT_ANCHORS:
        file_path = workspace / relative
        if not file_path.is_file():
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        title = (
            _heading_from_lines(lines)
            or _python_symbol_from_lines(lines)
            or Path(relative).name
        )
        source_group = _source_group_for_path(relative)
        alias_text = " ".join(aliases)
        anchor_score = _score_text(
            f"{relative} {title} {alias_text}".lower(),
            query_lower,
            terms,
        )
        snippet_line, snippet = _best_anchor_snippet(
            lines,
            query=query,
            terms=terms,
            aliases=aliases,
        )
        if file_path.suffix.lower() == ".py":
            title = _python_symbol_title(snippet) or title
        content_score = _score_text(snippet.lower(), query_lower, terms)
        score = anchor_score + content_score
        if score <= 0:
            continue
        items.append(
            ContextItem(
                path=relative,
                line=snippet_line,
                text=snippet,
                score=score + PROJECT_CONTEXT_ANCHOR_SCORE_BOOST,
                title=title,
                snippet=snippet,
                match_reason=_anchor_match_reason(
                    path=relative,
                    title=title,
                    snippet=snippet,
                    terms=terms,
                    aliases=aliases,
                    source_group=source_group,
                ),
                source_group=source_group,
            )
        )
    return items


def _heading_from_lines(lines: list[str]) -> str | None:
    for line in lines:
        heading = line.strip()
        if heading.startswith("#"):
            return heading.lstrip("#").strip() or None
    return None


def _python_symbol_from_lines(lines: list[str]) -> str | None:
    for line in lines:
        title = _python_symbol_title(line.strip())
        if title:
            return title
    return None


def _best_anchor_snippet(
    lines: list[str],
    *,
    query: str,
    terms: list[str],
    aliases: tuple[str, ...],
) -> tuple[int, str]:
    query_lower = query.lower()
    alias_terms = _query_terms(" ".join(aliases))
    best_line_number = 1
    best_text = ""
    best_score = -1
    for line_number, line in enumerate(lines, start=1):
        text = " ".join(line.split())
        if not text:
            continue
        score = _score_text(text.lower(), query_lower, terms)
        score += _score_text(text.lower(), "", alias_terms)
        if symbol_title := _python_symbol_title(text):
            score += 6
            if symbol_title.casefold() in " ".join(aliases).casefold():
                score += 6
        if score > best_score:
            best_line_number = line_number
            best_text = text
            best_score = score
    return best_line_number, _clip(best_text or aliases[0])


def _anchor_match_reason(
    *,
    path: str,
    title: str,
    snippet: str,
    terms: list[str],
    aliases: tuple[str, ...],
    source_group: str,
) -> str:
    searchable = f"{path} {title} {snippet} {' '.join(aliases)}".casefold()
    matched_terms = [term for term in terms if term.casefold() in searchable]
    matched_aliases = _matched_aliases(aliases, terms)
    parts = [f"group: {source_group}", "project context anchor"]
    if matched_terms:
        parts.append("matched query terms: " + ", ".join(matched_terms[:8]))
    if matched_aliases:
        parts.append("matched aliases: " + ", ".join(matched_aliases[:4]))
    return "; ".join(parts)


def _matched_aliases(aliases: tuple[str, ...], terms: list[str]) -> list[str]:
    matched: list[str] = []
    term_text = " ".join(terms).casefold()
    for alias in aliases:
        alias_text = alias.casefold()
        if alias_text in term_text or any(term.casefold() in alias_text for term in terms):
            matched.append(alias)
    return matched


def _dedupe_context_items(items: list[ContextItem]) -> list[ContextItem]:
    merged: dict[tuple[str, int, str], ContextItem] = {}
    for item in items:
        key = (item.path, item.line, item.text)
        existing = merged.get(key)
        if existing is None or item.score > existing.score:
            merged[key] = item
    return list(merged.values())


def _score_text(text: str, query: str, terms: list[str]) -> int:
    score = 0
    if query and query in text:
        score += 8
    for term in terms:
        if term.lower() in text:
            score += 2
    return score


def _title_for_path(
    workspace: Path,
    relative: str,
    *,
    fallback_text: str,
    title_cache: dict[str, str] | None = None,
) -> str:
    if title_cache is not None and relative in title_cache:
        return title_cache[relative]
    file_path = workspace / relative
    title: str | None = None
    if file_path.suffix.lower() == ".md":
        try:
            for line in file_path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines():
                heading = line.strip()
                if heading.startswith("#"):
                    title = heading.lstrip("#").strip() or Path(relative).name
                    break
        except OSError:
            pass
    if title is None and file_path.suffix.lower() == ".py":
        symbol_title = _python_symbol_title(fallback_text)
        if symbol_title:
            title = symbol_title
    if title is None:
        title = Path(relative).name
    if title_cache is not None:
        title_cache[relative] = title
    return title


def _python_symbol_title(text: str) -> str | None:
    match = re.match(r"(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    if match:
        return match.group(1)
    return None


def _match_reason(
    *,
    path: str,
    title: str,
    snippet: str,
    terms: list[str],
    source_group: str,
) -> str:
    searchable = f"{path} {title} {snippet}".casefold()
    matched_terms = [term for term in terms if term.casefold() in searchable]
    prefix = f"group: {source_group}; "
    if matched_terms:
        return prefix + "matched query terms: " + ", ".join(matched_terms[:8])
    return prefix + "matched by bm25 candidate score"


def _source_group_for_path(path: str) -> str:
    if path.startswith("docs/current/"):
        return "docs/current"
    if path.startswith("src/isotope/features/supervisor/"):
        return "supervisor feature code"
    if path.startswith("tests/"):
        return "isotope tests"
    if path.startswith("docs/"):
        return "docs"
    if path.startswith("src/isotope/"):
        return "isotope source"
    return "workspace"


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
        title = item.get("title")
        snippet = item.get("snippet")
        score = item.get("score")
        match_reason = item.get("match_reason")
        source_group = item.get("source_group")
        if (
            isinstance(path, str)
            and isinstance(line, int)
            and isinstance(text, str)
            and isinstance(score, (int, float))
        ):
            items.append(
                ContextItem(
                    path=path,
                    line=line,
                    text=text,
                    score=score,
                    title=title if isinstance(title, str) and title else Path(path).name,
                    snippet=snippet if isinstance(snippet, str) and snippet else text,
                    match_reason=(
                        match_reason
                        if isinstance(match_reason, str) and match_reason
                        else "legacy context result"
                    ),
                    source_group=(
                        source_group
                        if isinstance(source_group, str) and source_group
                        else _source_group_for_path(path)
                    ),
                )
            )
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
