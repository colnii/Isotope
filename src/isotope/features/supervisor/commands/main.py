"""Command dispatch entrypoint for the Supervisor CLI."""

from __future__ import annotations

from typing import Any


def run_cli(argv: list[str] | None = None, *, api: Any | None = None) -> int:
    """Run the Supervisor CLI through the legacy runner API surface."""
    if api is None:
        from isotope.features.supervisor import runner as api

    return api._run_cli_impl(argv)
