"""Embedding provider contracts for dense retrieval."""

from __future__ import annotations

import hashlib
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a dense vector for text."""


class DeterministicEmbeddingProvider:
    """Small deterministic embedding provider for tests and local fallback demos."""

    def __init__(self, *, dimensions: int = 16) -> None:
        if (
            isinstance(dimensions, bool)
            or not isinstance(dimensions, int)
            or dimensions <= 0
        ):
            raise ValueError("dimensions must be a positive integer")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("embedding text must be a string")
        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for byte in digest:
                values.append((byte / 127.5) - 1.0)
                if len(values) == self.dimensions:
                    break
            counter += 1
        return values
