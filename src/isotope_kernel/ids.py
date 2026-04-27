"""ID helpers for the Isotope v0.1 slice."""

from __future__ import annotations

from itertools import count

_counters: dict[str, count] = {}


def new_id(prefix: str) -> str:
    counter = _counters.setdefault(prefix, count(1))
    return f"{prefix}_{next(counter):03d}"
