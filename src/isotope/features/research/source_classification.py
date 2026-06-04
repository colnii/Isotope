"""Public source classification for research reports."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse


SOURCE_KINDS = {
    "official_docs",
    "paper",
    "news",
    "community",
    "reference",
    "unknown",
}
SOURCE_AUTHORITIES = {"high", "medium", "low", "unknown"}

_OFFICIAL_DOC_HOST_HINTS = (
    "docs.",
    "developer.",
    "developers.",
)
_PAPER_HOSTS = {
    "arxiv.org",
    "pubmed.ncbi.nlm.nih.gov",
    "doi.org",
    "aclanthology.org",
    "papers.nips.cc",
    "proceedings.mlr.press",
}
_NEWS_HOSTS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "nytimes.com",
    "theguardian.com",
    "wsj.com",
}
_COMMUNITY_HOSTS = {
    "reddit.com",
    "news.ycombinator.com",
    "stackoverflow.com",
    "stackexchange.com",
    "medium.com",
    "dev.to",
}
_REFERENCE_HOSTS = {
    "wikipedia.org",
    "wikidata.org",
}


def classify_research_source(source: Mapping[str, Any]) -> dict[str, str]:
    """Classify a source by stable URL/title signals."""
    host = _normalized_host(source.get("url"))
    title = _clean_string(source.get("title"))

    if _is_official_docs(host, title):
        return {"source_kind": "official_docs", "source_authority": "high"}
    if _host_matches(host, _PAPER_HOSTS):
        return {"source_kind": "paper", "source_authority": "high"}
    if _host_matches(host, _NEWS_HOSTS):
        return {"source_kind": "news", "source_authority": "medium"}
    if _host_matches(host, _COMMUNITY_HOSTS):
        return {"source_kind": "community", "source_authority": "low"}
    if _host_matches(host, _REFERENCE_HOSTS):
        return {"source_kind": "reference", "source_authority": "medium"}
    return {"source_kind": "unknown", "source_authority": "unknown"}


def normalize_source_kind(value: Any) -> str:
    text = _clean_string(value)
    return text if text in SOURCE_KINDS else "unknown"


def normalize_source_authority(value: Any) -> str:
    text = _clean_string(value)
    return text if text in SOURCE_AUTHORITIES else "unknown"


def _normalized_host(value: Any) -> str:
    url = _clean_string(value)
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower()
    return host.removeprefix("www.")


def _is_official_docs(host: str, title: str) -> bool:
    if not host:
        return False
    if host.startswith(_OFFICIAL_DOC_HOST_HINTS):
        return True
    return host.endswith(".gov") and ("doc" in title or "manual" in title)


def _host_matches(host: str, suffixes: set[str]) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def _clean_string(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""
