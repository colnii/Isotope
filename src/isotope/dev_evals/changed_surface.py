from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence

from .models import SurfaceDecision


SUITE = "supervisor_capacity_basic"
DEFAULT_SMOKE_CASE_ID = "code_search_fixture"
CONVERSATION_CONTRACT_CASE_ID = "supervisor_project_status_fixture"
SELF_REPAIR_CASE_ID = "isotope_self_repair_fixture"
INTEGRATION_REVIEW_CASE_ID = "supervisor_integration_review_fixture"
FULL_COMMAND = (
    "scripts/dev-eval supervisor_capacity_eval "
    "--suite supervisor_capacity_basic --json"
)

REASON_CODE_ORDER = (
    "capability_contract_changed",
    "conversation_contract_changed",
    "llm_prompt_changed",
    "agent_loop_projection_changed",
    "public_command_contract_changed",
    "dev_eval_contract_changed",
    "self_repair_contract_changed",
    "integration_review_contract_changed",
)

PATH_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "llm_prompt_changed",
        (
            "src/isotope/llm/prompts/",
        ),
    ),
    (
        "dev_eval_contract_changed",
        (
            "src/isotope/dev_evals/",
            "tests/unit/dev_evals/",
            "scripts/dev-eval",
        ),
    ),
    (
        "self_repair_contract_changed",
        (
            "src/isotope/features/supervisor/self_repair.py",
        ),
    ),
    (
        "integration_review_contract_changed",
        (
            "src/isotope/features/supervisor/workers/integration_review.py",
        ),
    ),
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
    (
        "self_repair_contract_changed",
        (
            "isotope.self_repair",
        ),
    ),
    (
        "integration_review_contract_changed",
        (
            "supervisor.integration_review",
        ),
    ),
)


def detect_changed_surface(diff_text: str) -> SurfaceDecision:
    sections = _diff_sections(diff_text)
    reason_hits: set[str] = set()
    for reason_code, path_patterns in PATH_PATTERNS:
        if any(
            _path_matches(changed_path, path_patterns)
            for changed_path, _section_text in sections
        ):
            reason_hits.add(reason_code)
    for reason_code, needles in SEMANTIC_PATTERNS:
        if any(
            any(needle in section_text for needle in needles)
            for changed_path, section_text in sections
            if not _path_matches(changed_path, _DEV_EVAL_PATH_PATTERNS)
        ):
            reason_hits.add(reason_code)
    reason_codes = [
        reason_code for reason_code in REASON_CODE_ORDER if reason_code in reason_hits
    ]
    return SurfaceDecision(
        eval_required=bool(reason_codes),
        suite=SUITE if reason_codes else None,
        reason_codes=reason_codes,
        recommended_command=_recommended_command(reason_codes)
        if reason_codes
        else None,
        full_command=FULL_COMMAND if reason_codes else None,
    )


def _recommended_command(reason_codes: Sequence[str]) -> str:
    return (
        "scripts/dev-eval supervisor_capacity_eval "
        f"--suite {SUITE} --case-id {_recommended_case_id(reason_codes)} --json"
    )


def _recommended_case_id(reason_codes: Sequence[str]) -> str:
    reason_set = set(reason_codes)
    if "self_repair_contract_changed" in reason_set:
        return SELF_REPAIR_CASE_ID
    if "integration_review_contract_changed" in reason_set:
        return INTEGRATION_REVIEW_CASE_ID
    if reason_set.intersection({"conversation_contract_changed", "llm_prompt_changed"}):
        return CONVERSATION_CONTRACT_CASE_ID
    return DEFAULT_SMOKE_CASE_ID


_DEV_EVAL_PATH_PATTERNS = (
    "src/isotope/dev_evals/",
    "tests/unit/dev_evals/",
    "scripts/dev-eval",
)


def _diff_sections(diff_text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_path = ""
    current_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_path or current_lines:
                sections.append((current_path, current_lines))
            current_path = _path_from_diff_header(line)
            current_lines = []
        elif _is_changed_diff_line(line):
            current_lines.append(line[1:])
    if current_path or current_lines:
        sections.append((current_path, current_lines))
    return [(path, "\n".join(lines)) for path, lines in sections]


def _path_from_diff_header(line: str) -> str:
    parts = line.split()
    if len(parts) >= 4 and parts[3].startswith("b/"):
        return parts[3][2:]
    return ""


def _path_matches(changed_path: str, patterns: tuple[str, ...]) -> bool:
    return any(
        changed_path == pattern or changed_path.startswith(pattern)
        for pattern in patterns
    )


def _is_changed_diff_line(line: str) -> bool:
    if line.startswith("+++") or line.startswith("---"):
        return False
    return line.startswith("+") or line.startswith("-")


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
        if decision.full_command:
            print("full_command:", decision.full_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
