"""File loading helpers for social character cards."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .character_card import CharacterCard


def load_character_card(path: Path | str) -> CharacterCard:
    card_path = Path(path).expanduser()
    try:
        data: Any = json.loads(card_path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ValueError("character card JSON is invalid") from exc
    if not isinstance(data, dict):
        raise ValueError("character card JSON must be an object")
    return CharacterCard.from_dict(data)
