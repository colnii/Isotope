"""Choose non-conflicting social action candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .candidates import SocialActionCandidate


@dataclass(frozen=True)
class SocialArbiterResult:
    selected: tuple[SocialActionCandidate, ...]
    rejected: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.selected, tuple):
            raise ValueError("selected candidates must be a tuple")
        for candidate in self.selected:
            if not isinstance(candidate, SocialActionCandidate):
                raise ValueError("selected items must be SocialActionCandidate")
        if not isinstance(self.rejected, dict):
            raise ValueError("rejected candidates must be a dict")
        for key, value in self.rejected.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("rejected candidate ids must be non-empty strings")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("rejected reasons must be non-empty strings")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "selected": [candidate.to_public_dict() for candidate in self.selected],
            "rejected": dict(self.rejected),
        }


@dataclass(frozen=True)
class SocialArbiter:
    def choose(
        self,
        candidates: tuple[SocialActionCandidate, ...],
    ) -> SocialArbiterResult:
        if not isinstance(candidates, tuple):
            raise ValueError("candidates must be a tuple")
        ordered = sorted(
            candidates,
            key=lambda candidate: (-candidate.confidence, candidate.candidate_id),
        )
        selected: list[SocialActionCandidate] = []
        rejected: dict[str, str] = {}
        selected_send_id: str | None = None
        lock_owners: dict[str, str] = {}

        for candidate in ordered:
            if not isinstance(candidate, SocialActionCandidate):
                raise ValueError("candidates items must be SocialActionCandidate")
            if candidate.is_send_action and selected_send_id is not None:
                rejected[candidate.candidate_id] = (
                    f"duplicate_send:{selected_send_id} already selected"
                )
                continue
            conflict = _first_lock_conflict(candidate, lock_owners)
            if conflict is not None:
                lock, owner = conflict
                rejected[candidate.candidate_id] = (
                    f"state_lock_conflict:{lock} owned by {owner}"
                )
                continue
            selected.append(candidate)
            if candidate.is_send_action:
                selected_send_id = candidate.candidate_id
            for lock in candidate.state_locks:
                lock_owners[lock] = candidate.candidate_id

        return SocialArbiterResult(selected=tuple(selected), rejected=rejected)


def _first_lock_conflict(
    candidate: SocialActionCandidate,
    lock_owners: dict[str, str],
) -> tuple[str, str] | None:
    for lock in candidate.state_locks:
        owner = lock_owners.get(lock)
        if owner is not None:
            return lock, owner
    return None
