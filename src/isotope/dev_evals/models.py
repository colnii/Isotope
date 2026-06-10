from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SurfaceDecision:
    eval_required: bool
    suite: str | None
    reason_codes: list[str]
    recommended_command: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_required": self.eval_required,
            "suite": self.suite,
            "reason_codes": list(self.reason_codes),
            "recommended_command": self.recommended_command,
        }
