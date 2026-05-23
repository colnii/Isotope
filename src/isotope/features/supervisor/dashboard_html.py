"""Static HTML template for the local Supervisor dashboard."""

from __future__ import annotations

from .dashboard_body import DASHBOARD_BODY
from .dashboard_script_batches import DASHBOARD_SCRIPT_BATCHES
from .dashboard_script_core import DASHBOARD_SCRIPT_CORE
from .dashboard_script_goals import DASHBOARD_SCRIPT_GOALS
from .dashboard_script_interactions import DASHBOARD_SCRIPT_INTERACTIONS
from .dashboard_script_managed import DASHBOARD_SCRIPT_MANAGED
from .dashboard_style_base import DASHBOARD_STYLE_BASE
from .dashboard_style_panels import DASHBOARD_STYLE_PANELS
from .dashboard_style_responsive import DASHBOARD_STYLE_RESPONSIVE


def dashboard_page_html() -> str:
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Codex Supervisor</title>\n  <style>\n'
        + DASHBOARD_STYLE_BASE
        + DASHBOARD_STYLE_PANELS
        + DASHBOARD_STYLE_RESPONSIVE
        + '  </style>\n</head>\n<body>\n'
        + DASHBOARD_BODY
        + '  <script>\n'
        + DASHBOARD_SCRIPT_CORE
        + DASHBOARD_SCRIPT_GOALS
        + DASHBOARD_SCRIPT_BATCHES
        + DASHBOARD_SCRIPT_MANAGED
        + DASHBOARD_SCRIPT_INTERACTIONS
        + '  </script>\n</body>\n</html>\n'
    )
