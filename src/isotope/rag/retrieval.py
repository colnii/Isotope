"""Retrieval service boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from ..platform.schemas.refs import ResourceRef


@dataclass(frozen=True)
class SummarySearchDocument:
    document_id: str
    title: str
    summary: str | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class SummarySearchHit:
    document: SummarySearchDocument
    score: float


class RetrievalService:
    """Minimal artifact-summary retrieval boundary for the v0.1 slice."""

    def __init__(self, artifact_store):
        self.artifact_store = artifact_store

    def get_artifact_summary(self, ref: ResourceRef, grants: dict) -> dict:
        self._validate_artifact_ref(ref, label="artifact summary retrieval")
        artifact_grants = self._artifact_grants(
            grants,
            missing_message="artifact summary read is not granted",
        )
        if not isinstance(artifact_grants, dict) or artifact_grants.get("read") != "summary":
            raise PermissionError("artifact summary read is not granted")

        metadata = self.artifact_store.get_metadata(ref, include_provenance=True)
        return {
            "ref": ref.to_dict(),
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "provenance": dict(metadata["provenance"]),
        }

    def get_artifact_content(
        self,
        ref: ResourceRef,
        *,
        grants: dict,
        caller_context: dict,
        purpose: str,
    ) -> dict:
        self._validate_artifact_ref(ref, label="artifact full content retrieval")
        if not isinstance(caller_context, dict) or not caller_context:
            raise TypeError("caller_context must be a non-empty dict")
        if not isinstance(caller_context.get("caller"), str) or not caller_context["caller"]:
            raise ValueError("caller_context must include caller")
        if not isinstance(purpose, str) or not purpose:
            raise ValueError("purpose must be a non-empty string")

        artifact_grants = self._artifact_grants(
            grants,
            missing_message="artifact full content read is not granted",
        )
        if not isinstance(artifact_grants, dict) or artifact_grants.get("read") != "full":
            raise PermissionError("artifact full content read is not granted")

        metadata = self.artifact_store.get_metadata(ref, include_provenance=True)
        content = self.artifact_store.get_content(ref)
        return {
            "status": "ok",
            "view": "full",
            "ref": ref.to_dict(),
            "artifact_type": metadata["artifact_type"],
            "summary": metadata["summary"],
            "content": content,
            "provenance": dict(metadata["provenance"]),
        }

    def _validate_artifact_ref(self, ref: ResourceRef, *, label: str) -> None:
        if not isinstance(ref, ResourceRef):
            raise TypeError(f"{label} requires a structured ResourceRef")
        if ref.ref_type != "artifact":
            raise ValueError(f"{label} requires an artifact ResourceRef")

    def _artifact_grants(self, grants: dict, *, missing_message: str) -> dict:
        if not isinstance(grants, dict):
            raise TypeError("retrieval grants must be a dict")
        artifact_grants = grants.get("artifact")
        if not isinstance(artifact_grants, dict):
            raise PermissionError(missing_message)
        return artifact_grants


def rank_summary_documents(
    query: str,
    documents: list[SummarySearchDocument],
) -> list[SummarySearchHit]:
    """Rank public title/summary documents with a small BM25 scorer."""
    query_terms = _tokenize(query)
    if not query_terms:
        raise ValueError("query must not be empty")
    if not documents:
        return []

    tokenized_documents = [_document_tokens(document) for document in documents]
    average_length = (
        sum(len(tokens) for tokens in tokenized_documents) / len(tokenized_documents)
    ) or 1.0
    document_frequencies = {
        term: sum(1 for tokens in tokenized_documents if term in tokens)
        for term in set(query_terms)
    }
    hits: list[tuple[int, int, SummarySearchHit]] = []
    for position, (document, tokens) in enumerate(zip(documents, tokenized_documents)):
        score = _bm25_score(
            query_terms=query_terms,
            document_terms=tokens,
            document_frequencies=document_frequencies,
            document_count=len(documents),
            average_document_length=average_length,
        )
        if score > 0:
            hits.append(
                (
                    position,
                    _matched_query_term_count(query_terms, tokens),
                    SummarySearchHit(document=document, score=score),
                )
            )

    if len({matched_terms for _, matched_terms, _ in hits}) <= 1:
        return [hit for _, _, hit in hits]
    return [
        hit
        for _, _, hit in sorted(
            hits,
            key=lambda item: (-item[1], -item[2].score, item[0]),
        )
    ]


def _document_tokens(document: SummarySearchDocument) -> list[str]:
    if not isinstance(document, SummarySearchDocument):
        raise TypeError("documents must contain SummarySearchDocument values")
    return _tokenize(f"{document.title} {document.summary or ''}")


def _bm25_score(
    *,
    query_terms: list[str],
    document_terms: list[str],
    document_frequencies: dict[str, int],
    document_count: int,
    average_document_length: float,
) -> float:
    if not document_terms:
        return 0.0
    score = 0.0
    k1 = 1.2
    b = 0.75
    document_length = len(document_terms)
    for term in dict.fromkeys(query_terms):
        term_frequency = document_terms.count(term)
        if term_frequency == 0:
            continue
        frequency = document_frequencies[term]
        inverse_document_frequency = math.log(
            1 + (document_count - frequency + 0.5) / (frequency + 0.5)
        )
        denominator = term_frequency + k1 * (
            1 - b + b * document_length / average_document_length
        )
        score += inverse_document_frequency * (
            term_frequency * (k1 + 1) / denominator
        )
    return score


def _matched_query_term_count(query_terms: list[str], document_terms: list[str]) -> int:
    document_term_set = set(document_terms)
    return sum(1 for term in dict.fromkeys(query_terms) if term in document_term_set)


def _tokenize(value: str | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, str):
        raise TypeError("search text must be a string")
    return re.findall(r"\w+", value.casefold())
