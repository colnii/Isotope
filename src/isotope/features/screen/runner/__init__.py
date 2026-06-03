"""Screen CLI runner package."""

from __future__ import annotations

from ._impl import *

# Private re-exports for test compatibility
from ._impl import (
    _build_click_action,
    _build_observe_intent,
    _build_parser,
    _build_restore_window_action,
    _default_smoke_matrix,
    _print_json,
    _real_smoke_commands,
    _target_allowlist_from_args,
    _target_selector_from_args,
)
