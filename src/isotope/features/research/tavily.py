"""Tavily provider implementation for web research."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request as urlrequest

from .providers import ResearchProviderError, _require_query, _utc_now


class TavilyResearchProvider:
    provider_name = "tavily"
    endpoint_url = "https://api.tavily.com/search"

    def __init__(
        self,
        *,
        api_key: str | None,
        enable_network: bool = False,
        timeout_seconds: int = 120,
        max_results: int = 5,
        search_depth: str = "basic",
        http_post: Callable[..., dict[str, Any]] | None = None,
    ):
        self.api_key = api_key.strip() if isinstance(api_key, str) else None
        self.enable_network = enable_network
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.search_depth = search_depth
        self.http_post = http_post or _post_json

    def run(self, query: str) -> dict[str, Any]:
        clean_query = _require_query(query)
        if not self.api_key:
            raise ResearchProviderError(
                "tavily provider requires TAVILY_API_KEY",
                details={
                    "provider_id": "tavily",
                    "error_code": "missing_api_key",
                    "required_env": "TAVILY_API_KEY",
                    "retryable": False,
                },
                retryable=False,
            )
        if not self.enable_network:
            raise ResearchProviderError(
                "tavily provider is preflight only; network execution is deferred",
                details={
                    "provider_id": "tavily",
                    "error_code": "network_execution_deferred",
                    "api_key_configured": True,
                    "timeout_seconds": self.timeout_seconds,
                    "max_results": self.max_results,
                    "retryable": False,
                },
                retryable=False,
            )
        request_payload = {
            "query": clean_query,
            "search_depth": self.search_depth,
            "max_results": self.max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_usage": True,
        }
        response_payload = self.http_post(
            self.endpoint_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload=request_payload,
            timeout_seconds=self.timeout_seconds,
        )
        return _normalize_tavily_search_payload(
            response_payload,
            query=clean_query,
            request_payload=request_payload,
            timeout_seconds=self.timeout_seconds,
        )


TavilyPreflightResearchProvider = TavilyResearchProvider


def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urlrequest.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout_seconds) as response:
            raw_text = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        retryable = exc.code == 429 or exc.code >= 500
        raise ResearchProviderError(
            "tavily request failed",
            details={
                "provider_id": "tavily",
                "error_code": "http_error",
                "http_status": exc.code,
                "retryable": retryable,
            },
            retryable=retryable,
        ) from exc
    except (TimeoutError, OSError) as exc:
        raise ResearchProviderError(
            "tavily request failed",
            details={
                "provider_id": "tavily",
                "error_code": "network_error",
                "retryable": True,
            },
            retryable=True,
        ) from exc
    try:
        decoded = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ResearchProviderError(
            "tavily response was not valid JSON",
            details={
                "provider_id": "tavily",
                "error_code": "invalid_json",
                "retryable": False,
            },
            retryable=False,
        ) from exc
    if not isinstance(decoded, dict):
        raise ResearchProviderError(
            "tavily response must be a JSON object",
            details={
                "provider_id": "tavily",
                "error_code": "invalid_response_shape",
                "retryable": False,
            },
            retryable=False,
        )
    return decoded


def _normalize_tavily_search_payload(
    payload: dict[str, Any],
    *,
    query: str,
    request_payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ResearchProviderError(
            "tavily response results must be a list",
            details={
                "provider_id": "tavily",
                "error_code": "invalid_response_shape",
                "retryable": False,
            },
            retryable=False,
        )
    retrieved_at = _utc_now()
    sources: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            continue
        url = _clean_optional_string(result.get("url"))
        content = _clean_optional_string(result.get("content"))
        if not url or not content:
            continue
        title = _clean_optional_string(result.get("title")) or url
        source_id = f"src_{len(sources) + 1:03d}"
        score = result.get("score")
        why_used = f"Tavily search result rank {index}"
        if isinstance(score, (int, float)):
            why_used = f"{why_used}, score {score:g}"
        source = {
            "source_id": source_id,
            "title": title,
            "url": url,
            "snippet": _truncate_text(content, 500),
            "why_used": why_used,
            "retrieved_at": retrieved_at,
            "provider_rank": index,
        }
        sources.append(source)
        claims.append(
            {
                "text": _truncate_text(content, 500),
                "source_ids": [source_id],
                "confidence": "medium",
            }
        )
    source_count = len(sources)
    suffix = "s" if source_count != 1 else ""
    summary = f"Tavily returned {source_count} source-backed result{suffix} for {query}."
    limitations = [
        "Tavily response was normalized from search result snippets.",
    ]
    if not sources:
        limitations.append("No valid Tavily results were returned.")
    return {
        "research_id": "research_tavily",
        "query": query,
        "provider": "tavily",
        "created_at": _utc_now(),
        "status": "ok",
        "evidence_status": "complete" if sources else "incomplete_evidence",
        "sources": sources,
        "report": {
            "summary": summary,
            "claims": claims,
            "limitations": limitations,
            "next_queries": [],
        },
        "provenance": {
            "provider": "tavily",
            "tavily": {
                "endpoint": TavilyResearchProvider.endpoint_url,
                "search_depth": request_payload.get("search_depth"),
                "max_results": request_payload.get("max_results"),
                "timeout_seconds": timeout_seconds,
                "response_time": payload.get("response_time"),
                "usage": payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            },
        },
    }


def _clean_optional_string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _truncate_text(value: str, limit: int) -> str:
    stripped = value.strip()
    return stripped if len(stripped) <= limit else stripped[: limit - 1].rstrip() + "..."
