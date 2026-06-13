"""Screen CLI runner package."""

from __future__ import annotations

from ._impl import *
from .actions import (
    _build_button_down_action,
    _build_button_up_action,
    _build_click_action,
    _build_double_click_action,
    _build_drag_action,
    _build_key_down_action,
    _build_key_press_action,
    _build_key_up_action,
    _build_restore_window_action,
    _build_wheel_action,
)

# Private re-exports for test compatibility
from ._impl import (
    _build_observe_intent,
    _build_parser,
    _default_smoke_matrix,
    _print_json,
    _real_smoke_commands,
    _target_allowlist_from_args,
    _target_selector_from_args,
)
