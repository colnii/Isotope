"""Low-sensitive quality gate for structured research reports."""

from __future__ import annotations

from typing import Any, Mapping


def research_quality_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    sources = _list_of_mappings(payload.get("sources"))
    report = payload.get("report") if isinstance(payload.get("report"), Mapping) else {}
    claims = _list_of_mappings(report.get("claims") if isinstance(report, Mapping) else None)
    source_count = len(sources)
    high_authority_source_count = sum(
        1 for source in sources if _string(source.get("source_authority")) == "high"
    )
    unknown_source_count = sum(
        1
        for source in sources
        if _string(source.get("source_authority")) in {"", "unknown"}
        or _string(source.get("source_kind")) in {"", "unknown"}
    )
    claim_count = len(claims)
    source_backed_claim_count = sum(1 for claim in claims if _claim_has_source_ids(claim))
    uncited_claim_count = claim_count - source_backed_claim_count
    evidence_status = _string(payload.get("evidence_status")) or "partial"

    reasons: list[str] = []
    if evidence_status != "complete":
        reasons.append("evidence_status_not_complete")
    if source_count == 0:
        reasons.append("no_sources")
    if uncited_claim_count:
        reasons.append("uncited_claims")

    return {
        "status": "promotable" if not reasons else "review_required",
        "source_count": source_count,
        "high_authority_source_count": high_authority_source_count,
        "unknown_source_count": unknown_source_count,
        "claim_count": claim_count,
        "source_backed_claim_count": source_backed_claim_count,
        "uncited_claim_count": uncited_claim_count,
        "evidence_status": evidence_status,
        "reasons": reasons,
    }


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _claim_has_source_ids(claim: Mapping[str, Any]) -> bool:
    source_ids = claim.get("source_ids")
    return isinstance(source_ids, list) and any(
        isinstance(source_id, str) and source_id.strip()
        for source_id in source_ids
    )


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
