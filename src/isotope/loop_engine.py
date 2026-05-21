"""Reusable one-step loop engine with pluggable handlers and interrupts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoopStepContext:
    """Inputs shared by the engine with step handlers and interrupt policies."""

    run_id: str
    step: str
    request: dict[str, Any]
    control: dict[str, Any]


StepHandler = Callable[[LoopStepContext], dict[str, Any]]
InterruptPolicy = Callable[[LoopStepContext], str | None]


class LoopInterrupted(RuntimeError):
    """Raised when a loop interrupt policy stops before a step handler runs."""

    def __init__(self, reason: str, control: dict[str, Any]):
        super().__init__(f"loop interrupted: {reason}")
        self.reason = reason
        self.control = control


class LoopEngine:
    """Run one symbolic loop step through registered handlers."""

    def __init__(
        self,
        *,
        get_control: Callable[[str], dict[str, Any]],
        step_handlers: Mapping[str, StepHandler],
        interrupt_policy: InterruptPolicy | None = None,
    ):
        self._get_control = get_control
        self._step_handlers = dict(step_handlers)
        self._interrupt_policy = interrupt_policy or self._default_interrupt_policy

    def run_step(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("loop step request must be a dict")
        step = request.get("step")
        if not isinstance(step, str) or not step:
            raise ValueError("step must be a non-empty string")

        control = self._get_control(run_id)
        context = LoopStepContext(
            run_id=run_id,
            step=step,
            request=request,
            control=control,
        )
        interrupt_reason = self._interrupt_policy(context)
        if interrupt_reason is not None:
            raise LoopInterrupted(interrupt_reason, control)

        handler = self._step_handlers.get(step)
        if handler is None:
            raise ValueError(f"unsupported loop step: {step}")
        action_result = handler(context)
        updated_control = self._get_control(run_id)
        return {
            "step": step,
            "status": str(
                action_result.get(
                    "step_status",
                    action_result.get("status", updated_control["status"]),
                )
            ),
            "action_result": action_result,
            "control": updated_control,
        }

    @staticmethod
    def _default_interrupt_policy(context: LoopStepContext) -> str | None:
        next_actions = context.control.get("next_actions", [])
        if context.step in next_actions:
            return None
        phase = context.control.get("phase")
        raise ValueError(f"loop step {context.step} is not available in current phase {phase}")
