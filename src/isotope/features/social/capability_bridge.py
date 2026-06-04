"""Bridge social capability intents to Isotope capability runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ...capabilities.runner import CapabilityRunner
from .candidates import SocialActionCandidate
from .character_card import CharacterCard
from .information_report import SocialInformationReport
from .messages import _required_string_value, _string_tuple


@dataclass(frozen=True)
class SocialCapabilityPolicy:
    approval_required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _string_tuple(
            self.approval_required_capabilities,
            "approval_required_capabilities",
        )


@dataclass(frozen=True)
class SocialCapabilityBridge:
    runner: Any = None
    policy: SocialCapabilityPolicy = SocialCapabilityPolicy()
    root_path: Path | str | None = None
    env: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.runner is None:
            object.__setattr__(self, "runner", CapabilityRunner())
        if not isinstance(self.policy, SocialCapabilityPolicy):
            raise ValueError("policy must be a SocialCapabilityPolicy")
        if self.env is not None and not isinstance(self.env, Mapping):
            raise ValueError("env must be a mapping")

    def run(
        self,
        candidate: SocialActionCandidate,
        *,
        character_card: CharacterCard,
        group_id: str,
        inputs: Mapping[str, Any] | None = None,
        operator_approved: bool = False,
    ) -> SocialInformationReport:
        capability_id = _capability_id(candidate)
        if not isinstance(character_card, CharacterCard):
            raise ValueError("character_card must be a CharacterCard")
        _required_string_value(group_id, "group_id")
        input_mapping = _input_mapping(inputs)
        if not operator_approved and capability_id in (
            self.policy.approval_required_capabilities
        ):
            return SocialInformationReport(
                status="requires_operator_approval",
                capability_id=capability_id,
                target=capability_id,
                reason=f"operator_approval_required:{capability_id}",
                content=f"{capability_id} requires operator approval before running.",
            )
        if capability_id not in character_card.tools.allowed_capabilities:
            return SocialInformationReport(
                status="blocked",
                capability_id=capability_id,
                target=capability_id,
                reason=f"capability_not_allowed_by_role:{capability_id}",
                content=f"{capability_id} is not allowed by this role card.",
            )

        plan = self.runner.plan_capability_run(
            capability_id,
            inputs=input_mapping,
            env=self.env,
        )
        if not bool(plan.get("can_launch")):
            return _report_from_launch_plan(capability_id, plan)

        try:
            result = self.runner.run_capability(
                capability_id,
                inputs=input_mapping,
                root_path=self.root_path,
                env=self.env,
            )
        except Exception as exc:  # pragma: no cover - exact exception class is runner-specific.
            error = str(exc)
            return SocialInformationReport(
                status="failed",
                capability_id=capability_id,
                target=capability_id,
                reason=f"runner_error:{error}",
                content=f"{capability_id} failed: {error}",
            )
        return SocialInformationReport(
            status="completed",
            capability_id=capability_id,
            target=capability_id,
            reason="capability_completed",
            content=_content_from_result(capability_id, result),
            raw_result=dict(result),
        )


def _capability_id(candidate: SocialActionCandidate) -> str:
    if not isinstance(candidate, SocialActionCandidate):
        raise ValueError("candidate must be a SocialActionCandidate")
    if candidate.kind != "call_capability":
        raise ValueError("candidate kind must be call_capability")
    return _required_string_value(candidate.capability_id, "candidate capability_id")


def _input_mapping(inputs: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if inputs is None:
        return {}
    if not isinstance(inputs, Mapping):
        raise ValueError("inputs must be a mapping")
    return inputs


def _report_from_launch_plan(
    capability_id: str,
    plan: Mapping[str, Any],
) -> SocialInformationReport:
    missing_inputs = plan.get("missing_inputs", [])
    if isinstance(missing_inputs, list) and missing_inputs:
        reason = "missing_inputs:" + ",".join(str(item) for item in missing_inputs)
        return SocialInformationReport(
            status="missing_inputs",
            capability_id=capability_id,
            target=capability_id,
            reason=reason,
            content=f"{capability_id} is missing inputs: {', '.join(missing_inputs)}",
            raw_result=dict(plan),
        )
    blocking = plan.get("blocking_reasons", [])
    blocking_text = ",".join(str(item) for item in blocking) if isinstance(blocking, list) else ""
    status = str(plan.get("status", "not_launchable"))
    suffix = f":{blocking_text}" if blocking_text else ""
    return SocialInformationReport(
        status="blocked",
        capability_id=capability_id,
        target=capability_id,
        reason=f"launch_plan_blocked:{status}{suffix}",
        content=f"{capability_id} cannot launch: {status}{suffix}",
        raw_result=dict(plan),
    )


def _content_from_result(capability_id: str, result: Mapping[str, Any]) -> str:
    for key in ("answer", "content", "summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    status = result.get("status", "completed")
    return f"{capability_id} returned status: {status}"
