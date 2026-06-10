from __future__ import annotations

import json
from typing import Any


def render_reviewer_prompt(*, diff_summary: str, report: dict[str, Any]) -> str:
    report_json = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "You are reviewing the current Codex development work for Isotope.\n"
        "Inspect the current git diff, eval trace, scores, and failure gates "
        "before making more changes.\n\n"
        "Current git diff summary:\n"
        f"{diff_summary}\n\n"
        "Eval report:\n"
        f"{report_json}\n\n"
        "Review instructions:\n"
        "- Identify whether each failure is a product-direction problem, "
        "capability-contract problem, prompt problem, or implementation bug.\n"
        "- When maturity or latest-practice judgment is needed, perform fresh "
        "research first instead of relying on memory.\n"
        "- Compare behavior with mature AI product and agent practice only as far "
        "as the diff and trace justify.\n"
        "- Make the smallest necessary correction.\n"
        "- rerun the required eval or deterministic fallback.\n"
        "- report what changed, which gate now passes, which gate still fails, "
        "and the remaining risk.\n"
    )
