"""Local web view for Codex Supervisor dashboard."""

from __future__ import annotations

import sys

from . import _impl
from ._impl import *

sys.modules[__name__] = _impl
