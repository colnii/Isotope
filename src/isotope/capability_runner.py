"""Compatibility exports and CLI entry for the capability runner."""

from isotope.capabilities.runner import *  # noqa: F401,F403
from isotope.capabilities.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
