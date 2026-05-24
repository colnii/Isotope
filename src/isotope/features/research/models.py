"""Structured models for the web research feature."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


COMPLETE_EVIDENCE_STATUSES = {"complete", "partial", "incomplete_evidence"}
RUN_STATUSES = {"ok", "partial", "provider_failed", "validation_failed"}


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    title: str
    url: str
    snippet: str
    why_used: str
    retrieved_at: str
    provider_rank: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchSource":
        return cls(
            source_id=_required_string(data, "source_id"),
            title=_required_string(data, "title"),
            url=_required_string(data, "url"),
            snippet=_required_string(data, "snippet"),
            why_used=_required_string(data, "why_used"),
            retrieved_at=_required_string(data, "retrieved_at"),
            provider_rank=_optional_int(data, "provider_rank"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "why_used": self.why_used,
            "retrieved_at": self.retrieved_at,
        }
        if self.provider_rank is not None:
            payload["provider_rank"] = self.provider_rank
        return payload


@dataclass(frozen=True)
class ResearchClaim:
    text: str
    source_ids: tuple[str, ...]
    confidence: str = "unverified"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchClaim":
        return cls(
            text=_required_string(data, "text"),
            source_ids=tuple(_required_string_list(data, "source_ids")),
            confidence=_optional_string(data, "confidence", default="unverified"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_ids": list(self.source_ids),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ResearchReport:
    summary: str
    claims: tuple[ResearchClaim, ...] = ()
    limitations: tuple[str, ...] = ()
    next_queries: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ResearchReport":
        if data is None:
            return cls(summary="")
        if not isinstance(data, dict):
            raise ValueError("report must be a dict")
        return cls(
            summary=_optional_string(data, "summary", default=""),
            claims=tuple(ResearchClaim.from_dict(item) for item in _optional_dict_list(data, "claims")),
            limitations=tuple(_optional_string_list(data, "limitations")),
            next_queries=tuple(_optional_string_list(data, "next_queries")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "claims": [claim.to_dict() for claim in self.claims],
            "limitations": list(self.limitations),
            "next_queries": list(self.next_queries),
        }


@dataclass(frozen=True)
class WebResearchRun:
    research_id: str
    query: str
    provider: str
    created_at: str
    status: str
    evidence_status: str
    sources: tuple[ResearchSource, ...]
    report: ResearchReport
    provenance: dict[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebResearchRun":
        if not isinstance(data, dict):
            raise ValueError("web research run must be a dict")
        sources = tuple(ResearchSource.from_dict(item) for item in _required_dict_list(data, "sources"))
        source_ids = {source.source_id for source in sources}
        report = ResearchReport.from_dict(data.get("report"))
        evidence_status = _optional_string(data, "evidence_status", default="partial")
        if not sources:
            evidence_status = "incomplete_evidence"
        else:
            for claim in report.claims:
                for source_id in claim.source_ids:
                    if source_id not in source_ids:
                        raise ValueError(f"unknown source_id in report claim: {source_id}")
        if evidence_status not in COMPLETE_EVIDENCE_STATUSES:
            raise ValueError("evidence_status is not supported")
        status = _optional_string(data, "status", default="ok")
        if status not in RUN_STATUSES:
            raise ValueError("status is not supported")
        return cls(
            research_id=_required_string(data, "research_id"),
            query=_required_string(data, "query"),
            provider=_required_string(data, "provider"),
            created_at=_required_string(data, "created_at"),
            status=status,
            evidence_status=evidence_status,
            sources=sources,
            report=report,
            provenance=dict(data.get("provenance", {})),
            artifact_refs=tuple(dict(ref) for ref in data.get("artifact_refs", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_id": self.research_id,
            "query": self.query,
            "provider": self.provider,
            "created_at": self.created_at,
            "status": self.status,
            "evidence_status": self.evidence_status,
            "sources": [source.to_dict() for source in self.sources],
            "report": self.report.to_dict(),
            "artifact_refs": [dict(ref) for ref in self.artifact_refs],
            "provenance": dict(self.provenance),
        }


def _required_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(data: dict[str, Any], field_name: str, *, default: str) -> str:
    value = data.get(field_name, default)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value.strip()


def _optional_int(data: dict[str, Any], field_name: str) -> int | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _required_dict_list(data: dict[str, Any], field_name: str) -> list[dict[str, Any]]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field_name} items must be dicts")
    return value


def _optional_dict_list(data: dict[str, Any], field_name: str) -> list[dict[str, Any]]:
    value = data.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{field_name} items must be dicts")
    return value


def _required_string_list(data: dict[str, Any], field_name: str) -> list[str]:
    values = _optional_string_list(data, field_name)
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return values


def _optional_string_list(data: dict[str, Any], field_name: str) -> list[str]:
    value = data.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    values: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings")
        values.append(item.strip())
    return values
