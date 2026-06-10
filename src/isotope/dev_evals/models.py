from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SurfaceDecision:
    eval_required: bool
    suite: str | None
    reason_codes: list[str]
    recommended_command: str | None
    full_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_required": self.eval_required,
            "suite": self.suite,
            "reason_codes": list(self.reason_codes),
            "recommended_command": self.recommended_command,
            "full_command": self.full_command,
        }


@dataclass(frozen=True)
class CapabilityScenario:
    case_id: str
    capability_ids: tuple[str, ...]
    user_message: str
    fixture: str
    required_gates: tuple[str, ...] = (
        "required_capacity_called",
        "low_sensitive_report",
    )
    required_input_fragments: tuple[str, ...] = ()
    allowed_result_statuses: tuple[str, ...] = ("ok",)
    combination_only: bool = False
    configuration_gated: bool = False
    max_turns: int = 12


@dataclass(frozen=True)
class EvalStep:
    capacity_id: str
    status: str
    input_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewerPromptRef:
    path: str
