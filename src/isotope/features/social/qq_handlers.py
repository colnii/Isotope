"""QQ command dispatch table for the social CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from .qq_beta_commands import (
    handle_beta_check,
    handle_beta_diagnostics,
    handle_beta_day_report,
    handle_init_beta,
    handle_regression_intake,
    handle_review_dry_run,
    handle_startup_check,
)
from .qq_operations_commands import (
    handle_export_log,
    handle_health,
    handle_inspect,
    handle_pause_resume,
)
from .qq_profile_commands import handle_apply_profile, handle_init_profile
from .qq_replay_commands import handle_init_replay
from .qq_runtime_commands import handle_live_run, handle_replay, handle_run


def qq_handlers() -> dict[str, Callable[[argparse.Namespace], dict[str, Any]]]:
    return {
        "run": handle_run,
        "live_run": handle_live_run,
        "init_beta": handle_init_beta,
        "init_profile": handle_init_profile,
        "apply_profile": handle_apply_profile,
        "init_replay": handle_init_replay,
        "replay": handle_replay,
        "beta_check": handle_beta_check,
        "beta_diagnostics": handle_beta_diagnostics,
        "startup_check": handle_startup_check,
        "review_dry_run": handle_review_dry_run,
        "beta_day_report": handle_beta_day_report,
        "regression_intake": handle_regression_intake,
        "pause_resume": handle_pause_resume,
        "inspect": handle_inspect,
        "health": handle_health,
        "export_log": handle_export_log,
    }
