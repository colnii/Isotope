"""Shared web research feature flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ...platform.schemas.refs import ResourceRef
from .models import WebResearchRun
from .providers import FakeResearchProvider, ResearchProvider, ResearchProviderError


@dataclass(frozen=True)
class ResearchFlowResult:
    status: str
    research: WebResearchRun | None
    query: str = ""
    artifact_refs: tuple[ResourceRef, ...] = ()
    artifacts: tuple[dict[str, Any], ...] = ()
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "artifact_refs": [ref.to_dict() for ref in self.artifact_refs],
            "artifacts": [dict(artifact) for artifact in self.artifacts],
        }
        if self.query:
            payload["query"] = self.query
        if self.research is not None:
            payload["research"] = self.research.to_dict()
        if self.error is not None:
            payload["error"] = dict(self.error)
        return payload


class ResearchFlow:
    """Run delegated research and persist source-backed artifacts."""

    def __init__(self, core: ProductCore, provider: ResearchProvider | None = None):
        self.core = core
        self.provider = provider if provider is not None else FakeResearchProvider()

    @classmethod
    def in_process(
        cls,
        root: Path | str,
        *,
        provider: ResearchProvider | None = None,
    ) -> "ResearchFlow":
        return cls(ProductCore.in_process(root), provider=provider)

    def search(self, query: str) -> ResearchFlowResult:
        clean_query = _require_query(query)
        try:
            provider_payload = self.provider.run(clean_query)
            research = WebResearchRun.from_dict(provider_payload)
        except ResearchProviderError as exc:
            session = self.core.start_session()
            run = self.core.start_run(session.session_id, goal=f"research: {clean_query}")
            error = {
                "code": "research_provider_failed",
                "message": str(exc),
                "retryable": True,
            }
            if exc.details:
                error["details"] = exc.details
            trace_artifact = self.core.runtime.create_source_artifact(
                run.run_id,
                summary=f"provider failure trace: {clean_query}",
                content=json.dumps(
                    {
                        "query": clean_query,
                        "provider": getattr(self.provider, "provider_name", "unknown"),
                        "status": "provider_failed",
                        "error": error,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                artifact_type="research.provider_trace",
            )
            return ResearchFlowResult(
                status="provider_failed",
                research=None,
                query=clean_query,
                artifact_refs=(trace_artifact["artifact_ref"],),
                artifacts=(_artifact_summary(trace_artifact),),
                error=error,
            )
        except Exception as exc:
            return ResearchFlowResult(
                status="validation_failed",
                research=None,
                query=clean_query,
                error={
                    "code": "research_validation_failed",
                    "message": str(exc),
                    "retryable": False,
                },
            )

        session = self.core.start_session()
        run = self.core.start_run(session.session_id, goal=f"research: {clean_query}")
        raw_artifact = self.core.runtime.create_source_artifact(
            run.run_id,
            summary=f"raw research provider output: {clean_query}",
            content=json.dumps(provider_payload, ensure_ascii=False, sort_keys=True),
            artifact_type="research.raw_transcript",
        )
        normalized_payload = research.to_dict()
        normalized_payload["artifact_refs"] = [raw_artifact["artifact_ref"].to_dict()]
        normalized = WebResearchRun.from_dict(normalized_payload)
        report_artifact = self.core.runtime.create_source_artifact(
            run.run_id,
            summary=normalized.report.summary or f"research report: {clean_query}",
            content=json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True),
            artifact_type="research.report",
            source_refs=[raw_artifact["artifact_ref"]],
        )
        artifact_refs = (
            raw_artifact["artifact_ref"],
            report_artifact["artifact_ref"],
        )
        final_payload = normalized.to_dict()
        final_payload["artifact_refs"] = [ref.to_dict() for ref in artifact_refs]
        return ResearchFlowResult(
            status=normalized.status,
            research=WebResearchRun.from_dict(final_payload),
            query=clean_query,
            artifact_refs=artifact_refs,
            artifacts=(
                _artifact_summary(raw_artifact),
                _artifact_summary(report_artifact),
            ),
        )


def _require_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return query.strip()


def _artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": artifact["artifact_type"],
        "ref": artifact["artifact_ref"].to_dict(),
        "summary": artifact["artifact_summary"],
    }
