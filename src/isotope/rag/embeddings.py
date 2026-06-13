"""Embedding provider contracts for dense retrieval."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Protocol


DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a dense vector for text."""


class EmbeddingProviderUnavailable(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class UnavailableEmbeddingProvider:
    def __init__(self, *, reason_code: str) -> None:
        self.reason_code = reason_code

    def embed(self, text: str) -> list[float]:
        raise RuntimeError(self.reason_code)


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


class FastEmbedEmbeddingProvider:
    """Local embedding provider backed by fastembed.TextEmbedding."""

    def __init__(self, *, model_name: str | None = None) -> None:
        self.model_name = model_name or DEFAULT_FASTEMBED_MODEL
        try:
            fastembed = __import__("fastembed", fromlist=["TextEmbedding"])
        except ModuleNotFoundError as exc:
            raise EmbeddingProviderUnavailable("fastembed_not_installed") from exc
        try:
            self._model = fastembed.TextEmbedding(model_name=self.model_name)
        except Exception as exc:
            raise EmbeddingProviderUnavailable("fastembed_model_unavailable") from exc

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("embedding text must be a string")
        vectors = self._model.embed([text])
        vector = next(iter(vectors))
        if not isinstance(vector, Iterable):
            raise RuntimeError("fastembed returned a non-iterable vector")
        return [float(value) for value in vector]
