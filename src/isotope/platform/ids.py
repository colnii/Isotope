"""ID helpers for the Isotope v0.1 slice."""

from __future__ import annotations

import re
from collections.abc import Iterable

_ID_PATTERN = re.compile(r"^(?P<prefix>[A-Za-z][A-Za-z0-9_]*)_(?P<number>[0-9]+)$")

_counters: dict[str, int] = {}


def new_id(prefix: str) -> str:
    next_value = _counters.setdefault(prefix, 1)
    _counters[prefix] = next_value + 1
    return f"{prefix}_{next_value:03d}"


def reserve_ids(values: Iterable[str]) -> None:
    for value in values:
        match = _ID_PATTERN.match(value)
        if match is None:
            continue
        prefix = match.group("prefix")
        next_value = int(match.group("number")) + 1
        _counters[prefix] = max(_counters.get(prefix, 1), next_value)
