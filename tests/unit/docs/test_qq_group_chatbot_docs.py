from __future__ import annotations

from pathlib import Path


DOCS = (
    Path("docs/current/qq-group-chatbot.md"),
    Path("docs/current/qq-group-chatbot-operations.md"),
)


def test_qq_group_chatbot_runbooks_cover_beta_operations() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)

    for required in (
        "Setup",
        "Config",
        "Run",
        "Pause",
        "Inspect",
        "Shutdown",
        "live-run",
        "init-beta",
        "beta-check",
        "startup-check",
        "ready",
        "profile_assets",
        "replay_report",
        "review-dry-run",
        "beta-day-report",
        "regression-intake",
        "dry-run-review.json",
        "beta-day-report.json",
        "regression-intake.json",
        "regressions/",
        "failures.json",
        "ready_for_send",
        "open_failure_count",
        "next_actions",
        "warnings",
        "init-profile",
        "apply-profile",
        "init-replay",
        "replay",
        "replay.json",
        "replay-report.json",
        "expectations",
        "passed",
        "min_sticker_candidates",
        "require_all_dry_run",
        "role-card.json",
        "sticker-library.json",
        "send-run.sh",
        "ISOTOPE_QQ_ENABLE_SEND",
        "--send",
        "--max-events 0",
        "ISOTOPE_QQ_REAL_SMOKE",
        "ISOTOPE_QQ_REAL_SMOKE_MODE",
        "dry-run",
        "Automated real smoke must not send messages",
        "Role-Card Tuning",
        "Sticker Pack Setup",
        "Failure Log",
        "Multi-Day Checklist",
    ):
        assert required in combined
