"""Codex session supervisor flow."""

from __future__ import annotations

import sys

# Re-import the full module contents
from . import _flow_impl as _impl
from ._flow_impl import *

# Re-export all private names needed by downstream importers
from ._flow_impl import (
    _empty_tmux_pane,
    _ensure_aware_utc,
    _git_branch_for,
    _is_title_noise,
    _managed_failure_detail,
    _managed_failure_payload,
    _managed_process_log_excerpt,
    _optional_string,
    _parse_timestamp,
    _pid_is_running,
    _read_session_summary,
    _shorten,
    _shorten_optional,
    _supervisor_protocol_from_text,
    _terminal_anchor_line_index,
    _terminal_has_active_work_marker,
    _terminal_ready_for_input,
    _terminal_tail_excerpt,
    _title_from_user_message,
    _tmux_bell_hook_installed,
    _tmux_capture_pane,
    _tmux_session_exists,
    _tmux_window_has_bell,
    _utc_now,
)

sys.modules[__name__] = _impl
