"""Argument parser entrypoint for the Supervisor CLI."""

from __future__ import annotations

import argparse
from typing import Any


def build_parser(*, api: Any | None = None) -> argparse.ArgumentParser:
    """Build the Supervisor CLI parser through the legacy runner implementation."""
    if api is None:
        from isotope.features.supervisor import runner as api

    return api._build_parser_impl()
