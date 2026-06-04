"""Tavily provider implementation for web research."""

from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import re
from typing import Any, Callable
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .providers import ResearchProviderError, _require_query, _utc_now
from .source_classification import classify_research_source


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
        http_get: Callable[..., dict[str, Any]] | None = None,
    ):
        self.api_key = api_key.strip() if isinstance(api_key, str) else None
        self.enable_network = enable_network
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.search_depth = search_depth
        self.http_post = http_post or _post_json
        self.http_get = http_get or _get_url_text

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
                "tavily provider is readiness_check only; network execution is queued",
                details={
                    "provider_id": "tavily",
                    "error_code": "network_execution_queued",
                    "api_key_configured": True,
                    "timeout_seconds": self.timeout_seconds,
                    "max_results": self.max_results,
                    "retryable": False,
                },
                retryable=False,
            )
        if _is_http_url(clean_query):
            fetched = self.http_get(clean_query, timeout_seconds=self.timeout_seconds)
            return _normalize_exact_url_payload(
                fetched,
                query=clean_query,
                timeout_seconds=self.timeout_seconds,
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


TavilyReadinessCheckResearchProvider = TavilyResearchProvider


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


def _get_url_text(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    request = urlrequest.Request(
        url,
        headers={
            "User-Agent": "IsotopeResearch/0.1",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout_seconds) as response:
            raw_bytes = response.read()
            content_type = response.headers.get("content-type", "")
            final_url = response.geturl()
    except urlerror.HTTPError as exc:
        retryable = exc.code == 429 or exc.code >= 500
        raise ResearchProviderError(
            "exact URL fetch failed",
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
            "exact URL fetch failed",
            details={
                "provider_id": "tavily",
                "error_code": "network_error",
                "retryable": True,
            },
            retryable=True,
        ) from exc
    return {
        "url": final_url,
        "content_type": content_type,
        "text": _decode_response_text(raw_bytes, content_type),
    }


def _decode_response_text(raw_bytes: bytes, content_type: str) -> str:
    charset = ""
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
    if match:
        charset = match.group(1).strip("\"'")
    candidates = [charset, "utf-8", "gb18030", "latin-1"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return raw_bytes.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _normalize_exact_url_payload(
    payload: dict[str, Any],
    *,
    query: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    url = _clean_optional_string(payload.get("url")) or query
    raw_text = _clean_optional_string(payload.get("text"))
    if not raw_text:
        raise ResearchProviderError(
            "exact URL fetch returned no readable text",
            details={
                "provider_id": "tavily",
                "error_code": "empty_url_text",
                "retryable": False,
            },
            retryable=False,
        )
    title, extracted_text = _extract_page_text(raw_text)
    if not extracted_text:
        raise ResearchProviderError(
            "exact URL fetch returned no readable text",
            details={
                "provider_id": "tavily",
                "error_code": "empty_extracted_text",
                "retryable": False,
            },
            retryable=False,
        )
    retrieved_at = _utc_now()
    source_title = title or url
    snippet = _truncate_text(extracted_text, 1200)
    summary = _truncate_text(extracted_text, 1600)
    return {
        "research_id": "research_tavily_exact_url",
        "query": query,
        "provider": "tavily",
        "created_at": _utc_now(),
        "status": "ok",
        "evidence_status": "complete",
        "sources": [
            {
                "source_id": "src_001",
                "title": source_title,
                "url": url,
                "snippet": snippet,
                "why_used": "Exact URL content fetched for the user-provided URL.",
                "retrieved_at": retrieved_at,
                "provider_rank": 1,
                **classify_research_source({"title": source_title, "url": url}),
            }
        ],
        "report": {
            "summary": summary,
            "claims": [
                {
                    "text": snippet,
                    "source_ids": ["src_001"],
                    "confidence": "medium",
                }
            ],
            "limitations": [
                "Exact URL content was extracted with a lightweight HTML/text parser.",
            ],
            "next_queries": [],
        },
        "provenance": {
            "provider": "tavily",
            "tavily": {
                "mode": "exact_url_fetch",
                "url": url,
                "content_type": payload.get("content_type"),
                "timeout_seconds": timeout_seconds,
            },
        },
    }


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
            **classify_research_source({"title": title, "url": url}),
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


def _is_http_url(value: str) -> bool:
    parsed = urlparse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_page_text(raw_text: str) -> tuple[str, str]:
    parser = _ReadableHtmlParser()
    try:
        parser.feed(raw_text)
        parser.close()
    except Exception:
        text = raw_text
        title = ""
    else:
        text = parser.readable_text()
        title = parser.title_text()
    if not text:
        text = re.sub(r"<[^>]+>", " ", raw_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


class _ReadableHtmlParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}
    _BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if lowered == "title":
            self._in_title = True
        if lowered in self._BLOCK_TAGS:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if lowered == "title":
            self._in_title = False
        if lowered in self._BLOCK_TAGS:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        stripped = data.strip()
        if not stripped:
            return
        if self._in_title:
            self._title_parts.append(stripped)
            return
        self._parts.append(stripped)

    def readable_text(self) -> str:
        return " ".join(self._parts).strip()

    def title_text(self) -> str:
        return " ".join(self._title_parts).strip()
