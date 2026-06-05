"""Rank local Codex sessions against a natural-language description."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from isotope.integrations.codex.session_reader import read_codex_session


MIN_CLEAR_SCORE = 3.0
MIN_MATCH_SCORE = 1.5
CLEAR_MARGIN = 1.0
STOP_TERMS = {
    "continue",
    "resume",
    "接着",
    "继续",
    "推进",
    "那个",
    "会话",
}


@dataclass(frozen=True)
class SessionMatchCandidate:
    session_id: str
    cwd: str
    source_path: str
    score: float
    matched_terms: tuple[str, ...]
    title: str | None = None
    recent_user: str | None = None
    recent_assistant: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "source_path": self.source_path,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "title": self.title,
            "recent_user": self.recent_user,
            "recent_assistant": self.recent_assistant,
        }


@dataclass(frozen=True)
class SessionMatchResult:
    status: str
    description: str
    selected: SessionMatchCandidate | None
    candidates: tuple[SessionMatchCandidate, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "description": self.description,
            "selected": self.selected.to_dict() if self.selected else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def match_codex_sessions_by_description(
    *,
    codex_home: Path | str,
    description: str,
    limit: int = 5,
) -> SessionMatchResult:
    query = description.strip()
    if not query:
        raise ValueError("description must not be empty")
    candidates = tuple(
        sorted(
            _candidate_scores(codex_home=codex_home, description=query),
            key=lambda candidate: candidate.score,
            reverse=True,
        )[: max(1, limit)]
    )
    if not candidates or candidates[0].score < MIN_MATCH_SCORE:
        return SessionMatchResult(
            status="no_match",
            description=query,
            selected=None,
            candidates=candidates,
        )
    if _is_clear_match(candidates):
        return SessionMatchResult(
            status="clear",
            description=query,
            selected=candidates[0],
            candidates=candidates,
        )
    return SessionMatchResult(
        status="ambiguous",
        description=query,
        selected=None,
        candidates=candidates,
    )


def _candidate_scores(
    *,
    codex_home: Path | str,
    description: str,
) -> list[SessionMatchCandidate]:
    query_terms = _terms(description)
    sessions_root = Path(codex_home).expanduser() / "sessions"
    if not sessions_root.exists():
        return []
    candidates: list[SessionMatchCandidate] = []
    for path in sorted(sessions_root.rglob("*.jsonl")):
        snapshot = read_codex_session(path)
        if snapshot is None:
            continue
        recent_user = _recent_message(snapshot.messages, role="user")
        recent_assistant = _recent_message(snapshot.messages, role="assistant")
        title = _thread_title(snapshot)
        weighted_text = " ".join(
            [
                snapshot.cwd,
                snapshot.cwd,
                title or "",
                title or "",
                recent_user or "",
                recent_user or "",
                recent_assistant or "",
            ]
        )
        candidate_terms = _terms(weighted_text)
        matched = tuple(sorted(query_terms & candidate_terms))
        score = float(len(matched))
        if _substring_match(description, weighted_text):
            score += 2.0
        candidates.append(
            SessionMatchCandidate(
                session_id=snapshot.session_id,
                cwd=snapshot.cwd,
                source_path=str(path),
                score=score,
                matched_terms=matched,
                title=title,
                recent_user=recent_user,
                recent_assistant=recent_assistant,
            )
        )
    return candidates


def _is_clear_match(candidates: tuple[SessionMatchCandidate, ...]) -> bool:
    if candidates[0].score < MIN_CLEAR_SCORE:
        return False
    if len(candidates) == 1:
        return True
    return candidates[0].score - candidates[1].score >= CLEAR_MARGIN


def _terms(text: str) -> set[str]:
    normalized = text.lower().replace("_", " ")
    raw_terms = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", normalized)
    terms: set[str] = set()
    for term in raw_terms:
        if len(term) <= 1:
            continue
        if term in STOP_TERMS:
            continue
        terms.add(term)
        if len(term) >= 4 and re.search(r"[\u4e00-\u9fff]", term):
            terms.update(_chinese_bigrams(term))
    return terms


def _chinese_bigrams(text: str) -> set[str]:
    return {text[index : index + 2] for index in range(0, len(text) - 1)}


def _substring_match(query: str, candidate: str) -> bool:
    query_text = query.lower().strip()
    candidate_text = candidate.lower()
    return bool(query_text and query_text in candidate_text)


def _thread_title(snapshot) -> str | None:
    for update in reversed(snapshot.thread_updates):
        if update.thread_name:
            return update.thread_name
    return None


def _recent_message(messages, *, role: str) -> str | None:
    for message in reversed(messages):
        if message.role == role and message.text:
            return message.text
    return None
