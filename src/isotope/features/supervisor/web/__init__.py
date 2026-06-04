"""Local web view for Codex Supervisor dashboard."""

from __future__ import annotations

import sys

from . import _impl
from ._impl import *  # noqa: F403
from ._impl import _DashboardRequestHandler
from .routes.service_actions import (
    start_supervisor_daemon,
    start_supervisor_watcher,
    stop_supervisor_daemon,
    stop_supervisor_watcher,
)

_impl._DashboardRequestHandler = _DashboardRequestHandler
_impl.start_supervisor_daemon = start_supervisor_daemon
_impl.stop_supervisor_daemon = stop_supervisor_daemon
_impl.start_supervisor_watcher = start_supervisor_watcher
_impl.stop_supervisor_watcher = stop_supervisor_watcher

sys.modules[__name__] = _impl
