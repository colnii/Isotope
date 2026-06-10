from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence

from .models import SurfaceDecision


SUITE = "supervisor_capacity_basic"
RECOMMENDED_COMMAND = (
    "PYTHONPATH=src .venv/bin/python -m "
    "isotope.dev_evals.supervisor_capacity_eval "
    "--suite supervisor_capacity_basic --json"
)

SEMANTIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "capability_contract_changed",
        (
            "capability_id",
            "input_contract",
            "output_contract",
            "Capability",
            "CapabilityCatalog",
            "run_capability",
        ),
    ),
    (
        "conversation_contract_changed",
        (
            "capacity_manifest",
            "capacity_observation",
            "call_capability",
            "call_capabilities",
            "direct_answer",
            "report_capability_gap",
        ),
    ),
    (
        "llm_prompt_changed",
        (
            "SYSTEM_PROMPT_NAMES",
            "USER_PROMPT_TEMPLATE_NAMES",
            "supervisor_conversation_loop",
            "capacity_calling",
            "src/isotope/llm/prompts/",
        ),
    ),
    (
        "agent_loop_projection_changed",
        (
            "model_observation",
            "agent_loop_json_result",
            "capacity_start",
            "capacity_result",
            "low-sensitive",
        ),
    ),
    (
        "public_command_contract_changed",
        (
            "capacity plan",
            "research --root",
            "isotope-capability",
            "golden event",
            "result schema",
        ),
    ),
)


def detect_changed_surface(diff_text: str) -> SurfaceDecision:
    reason_codes: list[str] = []
    for reason_code, needles in SEMANTIC_PATTERNS:
        if any(needle in diff_text for needle in needles):
            reason_codes.append(reason_code)
    return SurfaceDecision(
        eval_required=bool(reason_codes),
        suite=SUITE if reason_codes else None,
        reason_codes=reason_codes,
        recommended_command=RECOMMENDED_COMMAND if reason_codes else None,
    )


def diff_against_base(base: str) -> str:
    completed = subprocess.run(
        ["git", "diff", "--no-ext-diff", base, "--"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    decision = detect_changed_surface(diff_against_base(args.base))
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print("eval_required:", str(decision.eval_required).lower())
        print("suite:", decision.suite or "")
        if decision.reason_codes:
            print("reason_codes:", ", ".join(decision.reason_codes))
        if decision.recommended_command:
            print("recommended_command:", decision.recommended_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
