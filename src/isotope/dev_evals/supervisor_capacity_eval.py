from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from isotope.features.supervisor.conversation_loop import (
    run_supervisor_conversation_events,
)
from isotope.llm.provider import LLMResponse

from .cases import scenario_catalog
from .fixtures import prepare_fixture
from .reporting import build_case_report, build_suite_report


SUITE = "supervisor_capacity_basic"


class DeterministicScenarioProvider:
    provider = "deterministic_dev_eval"
    model = "deterministic-dev-eval"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        if not self.responses:
            payload = {
                "kind": "direct_answer",
                "answer": "No deterministic response remained.",
                "answer_basis": {
                    "kind": "no_capability_needed",
                    "reason": "deterministic fallback",
                },
                "rationale": "fallback",
            }
        else:
            payload = self.responses.pop(0)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(payload, ensure_ascii=False),
            finish_reason="stop",
            usage={},
            raw={"raw_response": "MUST_NOT_LEAK"},
        )


def _step_from_capacity_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "capacity_id": str(payload.get("capacity_id", "")),
        "status": str(payload.get("status", "")),
        "input_summary": payload.get("inputs", {})
        if isinstance(payload.get("inputs"), dict)
        else {},
        "result_summary": result,
    }


def run_scenarios(
    scenarios: list[Any],
    *,
    root: Path,
    provider: Any,
    live: bool,
) -> dict[str, Any]:
    case_reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        state_root, workspace = prepare_fixture(root / scenario.case_id, scenario.fixture)
        events = list(
            run_supervisor_conversation_events(
                state_root=state_root,
                cwd=workspace,
                user_message=scenario.user_message,
                provider=provider,
                max_turns=scenario.max_turns,
                timeout_seconds=30,
            )
        )
        steps = [
            _step_from_capacity_result(event.payload)
            for event in events
            if event.event == "capacity_result"
        ]
        final_answer = "".join(
            str(event.payload.get("text", ""))
            for event in events
            if event.event == "delta"
        )
        case_reports.append(
            build_case_report(scenario, steps=steps, final_answer=final_answer)
        )
    return build_suite_report(suite=SUITE, cases=case_reports)


def _default_deterministic_provider_for_case(
    capability_id: str,
) -> DeterministicScenarioProvider:
    return DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": capability_id,
                "arguments": {},
                "rationale": "Run requested capability.",
            },
            {
                "kind": "direct_answer",
                "answer": "Capability observation captured.",
                "answer_basis": {
                    "kind": "observation",
                    "capacity_ids": [capability_id],
                    "reason": "Observation exists.",
                },
                "rationale": "Stop.",
            },
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default=SUITE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--case-id")
    args = parser.parse_args(argv)
    if args.suite != SUITE:
        raise SystemExit(f"unknown suite: {args.suite}")
    scenarios = scenario_catalog()
    if args.case_id:
        scenarios = [item for item in scenarios if item.case_id == args.case_id]
    if not scenarios:
        raise SystemExit("no scenarios selected")
    provider = _default_deterministic_provider_for_case(scenarios[0].capability_ids[0])
    report = run_scenarios(
        scenarios[:1],
        root=Path(".dev-eval-runs"),
        provider=provider,
        live=False,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
