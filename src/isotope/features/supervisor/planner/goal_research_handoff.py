"""Attach Supervisor-selected research handoff text to worker goals."""

from __future__ import annotations

from dataclasses import replace
from typing import TypeVar

MAX_SELECTED_HANDOFF_CHARS = 1200

CandidateT = TypeVar("CandidateT")


def attach_selected_research_handoff_to_candidates(
    candidates: list[CandidateT],
) -> list[CandidateT]:
    return [
        _with_selected_handoff(candidate)
        for candidate in candidates
    ]


def _with_selected_handoff(candidate: CandidateT) -> CandidateT:
    goal = str(getattr(candidate, "goal", ""))
    handoff = _optional_string(getattr(candidate, "research_handoff", None))
    if handoff is None or _has_handoff(goal):
        return candidate
    clipped_handoff = _clip(handoff, MAX_SELECTED_HANDOFF_CHARS)
    return replace(
        candidate,
        goal=f"{goal}\n\nResearch handoff for worker:\n{clipped_handoff}",
        research_handoff=clipped_handoff,
    )


def _has_handoff(goal: str) -> bool:
    return "Research handoff for worker:" in goal


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _clip(text: str, limit: int) -> str:
    clean = "\n".join(
        " ".join(line.split()) for line in text.splitlines() if line.strip()
    )
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "..."
