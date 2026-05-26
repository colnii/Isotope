"""Provider boundaries for web research."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from ...integrations.codex.cli import CodexCliBackend, CodexCliBackendConfig
from ...integrations.codex.task import CodexTaskConfig, CodexTaskRequest


class ResearchProvider(Protocol):
    provider_name: str

    def run(self, query: str) -> dict[str, Any]:
        """Return a structured WebResearchRun-like payload."""


class ResearchProviderError(RuntimeError):
    """Raised when a delegated provider fails before returning research data."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ):
        super().__init__(message)
        self.details = dict(details or {})
        if retryable is None:
            detail_retryable = self.details.get("retryable")
            retryable = detail_retryable if isinstance(detail_retryable, bool) else True
        self.retryable = retryable


@dataclass(frozen=True)
class ResearchProviderDescriptor:
    provider_id: str
    provider_name: str
    label: str
    status: str
    entrypoint: str
    requires: tuple[str, ...] = ()
    notes: str = ""
    selectable: bool = False

    @property
    def implemented(self) -> bool:
        return self.status == "implemented"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "label": self.label,
            "status": self.status,
            "implemented": self.implemented,
            "entrypoint": self.entrypoint,
            "requires": list(self.requires),
            "notes": self.notes,
            "selectable": self.selectable,
        }


_PROVIDER_DESCRIPTORS: tuple[ResearchProviderDescriptor, ...] = (
    ResearchProviderDescriptor(
        provider_id="fake",
        provider_name="fake",
        label="Fake deterministic provider",
        status="implemented",
        entrypoint="local_fake",
        notes="Deterministic provider for tests and smoke checks.",
        selectable=True,
    ),
    ResearchProviderDescriptor(
        provider_id="codex",
        provider_name="codex_delegated",
        label="Codex delegated provider",
        status="implemented",
        entrypoint="codex_cli",
        requires=("codex_cli",),
        notes="Delegates the research prompt to a Codex CLI task and stores provider traces on failure.",
        selectable=True,
    ),
    ResearchProviderDescriptor(
        provider_id="tavily",
        provider_name="tavily",
        label="Tavily API provider",
        status="implemented",
        entrypoint="api",
        requires=("TAVILY_API_KEY",),
        notes="Network execution is available behind an explicit command flag; preflight remains the default.",
        selectable=True,
    ),
    ResearchProviderDescriptor(
        provider_id="searxng",
        provider_name="searxng",
        label="SearXNG provider",
        status="planned",
        entrypoint="self_hosted_or_fallback",
        requires=("base_url",),
        notes="Planned optional self-hosted/fallback search provider.",
    ),
    ResearchProviderDescriptor(
        provider_id="browser",
        provider_name="browser",
        label="Local browser/crawler fallback",
        status="planned",
        entrypoint="local_browser_or_crawler",
        requires=("explicit_approval",),
        notes="Planned lowest-level fetch fallback, gated separately from API providers.",
    ),
)


def list_research_provider_descriptors() -> tuple[ResearchProviderDescriptor, ...]:
    return _PROVIDER_DESCRIPTORS


def get_research_provider_descriptor(provider_id: str) -> ResearchProviderDescriptor:
    for descriptor in _PROVIDER_DESCRIPTORS:
        if descriptor.provider_id == provider_id:
            return descriptor
    raise ValueError(f"unknown research provider: {provider_id}")


def research_provider_choices() -> tuple[str, ...]:
    return tuple(descriptor.provider_id for descriptor in _PROVIDER_DESCRIPTORS)


def _tavily_api_key_from_env() -> str | None:
    import os

    return os.environ.get("TAVILY_API_KEY")


def build_research_provider(
    provider_id: str,
    *,
    workspace_root: str | Path | None = None,
    codex_executable: str = "codex",
    codex_home: str | None = None,
    model: str | None = None,
    timeout_seconds: int = 120,
    max_attempts: int = 2,
    tavily_api_key: str | None = None,
    tavily_enable_network: bool = False,
    tavily_timeout_seconds: int = 30,
    tavily_max_results: int = 5,
) -> ResearchProvider:
    descriptor = get_research_provider_descriptor(provider_id)
    if not descriptor.implemented and not descriptor.selectable:
        raise ValueError(
            f"research provider {provider_id} is registered but not implemented yet; "
            "run `isotope-research providers` to inspect provider status"
        )
    if provider_id == "fake":
        return FakeResearchProvider()
    if provider_id == "codex":
        return CodexDelegatedResearchProvider(
            build_codex_cli_research_backend(
                workspace_root=workspace_root or Path.cwd(),
                executable=codex_executable,
                codex_home=codex_home,
                model=model,
                timeout_seconds=timeout_seconds,
            ),
            max_attempts=max_attempts,
        )
    if provider_id == "tavily":
        from .tavily import TavilyResearchProvider

        return TavilyResearchProvider(
            api_key=(
                tavily_api_key
                if tavily_api_key is not None
                else _tavily_api_key_from_env()
            ),
            enable_network=tavily_enable_network,
            timeout_seconds=tavily_timeout_seconds,
            max_results=tavily_max_results,
        )
    raise RuntimeError(f"research provider registry is missing builder for: {provider_id}")


class FakeResearchProvider:
    provider_name = "fake"

    def run(self, query: str) -> dict[str, Any]:
        clean_query = _require_query(query)
        return {
            "research_id": "research_fake_001",
            "query": clean_query,
            "provider": self.provider_name,
            "created_at": _utc_now(),
            "status": "ok",
            "evidence_status": "complete",
            "sources": [
                {
                    "source_id": "src_001",
                    "title": "Fake source-backed research note",
                    "url": "https://example.com/isotope-research",
                    "snippet": "Research claims should cite source ids.",
                    "why_used": "deterministic fake source for tests",
                    "retrieved_at": _utc_now(),
                    "provider_rank": 1,
                }
            ],
            "report": {
                "summary": f"Fake research summary for {clean_query}.",
                "claims": [
                    {
                        "text": "Research reports must keep source-backed claims.",
                        "source_ids": ["src_001"],
                        "confidence": "high",
                    }
                ],
                "limitations": ["fake provider"],
                "next_queries": [],
            },
            "provenance": {"provider": self.provider_name},
        }


class CodexDelegatedResearchProvider:
    provider_name = "codex_delegated"

    def __init__(self, backend: Callable[[str], str], *, max_attempts: int = 1):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.backend = backend
        self.max_attempts = max_attempts

    def run(self, query: str) -> dict[str, Any]:
        clean_query = _require_query(query)
        prompt = build_codex_research_prompt(clean_query)
        raw_output = self._run_backend_with_retry(prompt)
        payload = _normalize_codex_research_payload(extract_research_json(raw_output))
        payload["query"] = clean_query
        payload["provider"] = self.provider_name
        payload.setdefault("provenance", {})
        payload["provenance"]["provider"] = self.provider_name
        payload["provenance"]["raw_output"] = raw_output
        payload.setdefault("created_at", _utc_now())
        payload.setdefault("research_id", "research_codex_delegated")
        payload.setdefault("status", "ok")
        payload.setdefault("evidence_status", "partial")
        return payload

    def _run_backend_with_retry(self, prompt: str) -> str:
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.backend(prompt)
            except ResearchProviderError as exc:
                attempt_record = _provider_error_attempt(attempt, exc)
                attempts.append(attempt_record)
                if attempt == self.max_attempts or not attempt_record["retryable"]:
                    raise _provider_error_with_attempts(
                        exc,
                        attempts=attempts,
                        retry_exhausted=attempt_record["retryable"] and attempt == self.max_attempts,
                    ) from exc
        raise RuntimeError("unreachable research provider retry state")


def build_codex_research_prompt(query: str) -> str:
    clean_query = _require_query(query)
    return (
        "Research this query using web/search-capable reasoning if available. "
        "Return exactly one JSON object, no prose outside JSON. "
        "Required keys: research_id, created_at, status, evidence_status, sources, report. "
        "Each source must include source_id, title, url, snippet, why_used, retrieved_at. "
        "Each report claim must include text, source_ids, confidence. "
        f"Query: {clean_query}"
    )


def extract_research_json(raw_output: str) -> dict[str, Any]:
    if not isinstance(raw_output, str):
        raise ValueError("research output must be text")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else raw_output.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("research JSON object was not found") from exc
    if not isinstance(payload, dict):
        raise ValueError("research JSON object must be a dict")
    return payload


def build_codex_cli_research_backend(
    *,
    workspace_root: str | Path,
    executable: str = "codex",
    codex_home: str | None = None,
    model: str | None = None,
    timeout_seconds: int = 120,
    executable_resolver=None,
    process_runner=None,
) -> Callable[[str], str]:
    backend = CodexCliBackend(
        CodexCliBackendConfig(
            workspace_root=str(workspace_root),
            executable=executable,
            codex_home=codex_home,
            model=model,
            skip_git_repo_check=True,
        ),
        **{
            key: value
            for key, value in {
                "executable_resolver": executable_resolver,
                "process_runner": process_runner,
            }.items()
            if value is not None
        },
    )

    def run_prompt(prompt: str) -> str:
        request = CodexTaskRequest(
            run_id="run_research_cli",
            proposal_id="prop_research_cli",
            decision_id="dec_research_cli",
            execution_id="exec_research_cli",
            policy_profile_id="default",
            policy_version="v0.2",
            registry_id="default",
            registry_version="v0.2",
            grants={
                "tools": ["codex_task"],
                "workspace": {"mode": "shared_ro"},
                "budget": {"seconds": timeout_seconds},
                "codex_task": {"adapter_required": True},
            },
            workspace_binding={
                "workspace_id": "workspace_research_cli",
                "mode": "shared_ro",
                "lease_status": "active",
            },
            task_request={"kind": "codex_prompt", "prompt": prompt},
            budget={"seconds": timeout_seconds},
            artifact_policy={
                "capture": ["transcript"],
                "full_content_in_events": False,
                "full_content_in_read_model": False,
            },
            basis_event_ids=["research_cli"],
            adapter_config=CodexTaskConfig(
                adapter_id="codex_cli_research",
                adapter_version="v0.1",
            ).to_dict(),
        )
        result = backend.run(request)
        for output in result.output_artifacts:
            content = output.content if hasattr(output, "content") else output["content"]
            try:
                transcript = json.loads(content)
            except json.JSONDecodeError:
                agent_text = extract_codex_agent_message_text(content)
                if agent_text is not None:
                    return agent_text
                _raise_if_codex_error_only_jsonl(content, timeout_seconds=timeout_seconds)
                return content
            stdout = transcript.get("stdout")
            if isinstance(stdout, str):
                agent_text = extract_codex_agent_message_text(stdout)
                if agent_text is not None:
                    return agent_text
                _raise_if_codex_error_only_jsonl(stdout, timeout_seconds=timeout_seconds)
                return stdout
            return content
        return result.summary

    return run_prompt


def _normalize_codex_research_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if normalized.get("status") in {"complete", "completed", "success"}:
        normalized["status"] = "ok"
    if normalized.get("evidence_status") not in {"complete", "partial", "incomplete_evidence"}:
        normalized["evidence_status"] = "complete" if normalized.get("sources") else "incomplete_evidence"
    report = normalized.get("report")
    if isinstance(report, list):
        claims = [dict(item) for item in report if isinstance(item, dict)]
        summary = " ".join(
            str(claim.get("text", "")).strip()
            for claim in claims[:1]
            if isinstance(claim.get("text"), str)
        )
        normalized["report"] = {
            "summary": summary,
            "claims": claims,
            "limitations": [],
            "next_queries": [],
        }
    return normalized


def extract_codex_agent_message_text(stdout: str) -> str | None:
    if not isinstance(stdout, str):
        return None
    latest_text: str | None = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            latest_text = text.strip()
    return latest_text


def _raise_if_codex_error_only_jsonl(stdout: str, *, timeout_seconds: int) -> None:
    diagnostics = _codex_jsonl_diagnostics(stdout, timeout_seconds=timeout_seconds)
    error_messages = diagnostics["codex_error_messages"]
    if error_messages:
        raise ResearchProviderError(
            "codex cli did not return an agent message: " + "; ".join(error_messages),
            details=diagnostics,
        )


_RETRYABLE_PROVIDER_ERROR_SNIPPETS = (
    "request timed out",
    "timed out",
    "timeout",
    "stream disconnected",
    "error sending request",
    "temporarily unavailable",
    "network",
    "connection reset",
    "connection refused",
    "reconnecting",
)


def _provider_error_attempt(attempt: int, exc: ResearchProviderError) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "message": str(exc),
        "retryable": _is_retryable_provider_error(exc),
        "details": dict(exc.details),
    }


def _provider_error_with_attempts(
    exc: ResearchProviderError,
    *,
    attempts: list[dict[str, Any]],
    retry_exhausted: bool,
) -> ResearchProviderError:
    details = dict(exc.details)
    details["attempt_count"] = len(attempts)
    details["attempts"] = attempts
    details["retry_exhausted"] = retry_exhausted
    return ResearchProviderError(str(exc), details=details)


def _is_retryable_provider_error(exc: ResearchProviderError) -> bool:
    texts = [str(exc)]
    messages = exc.details.get("codex_error_messages")
    if isinstance(messages, list):
        texts.extend(message for message in messages if isinstance(message, str))
    return any(
        snippet in text.lower()
        for text in texts
        for snippet in _RETRYABLE_PROVIDER_ERROR_SNIPPETS
    )


def _codex_jsonl_diagnostics(stdout: str, *, timeout_seconds: int) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "codex_event_counts": {},
        "codex_error_messages": [],
        "codex_has_agent_message": False,
        "codex_timeout_seconds": timeout_seconds,
    }
    if not isinstance(stdout, str):
        return diagnostics
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type:
            counts = diagnostics["codex_event_counts"]
            counts[event_type] = counts.get(event_type, 0) + 1
        if event_type == "item.completed":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                diagnostics["codex_has_agent_message"] = True
        if event_type != "error":
            continue
        message = event.get("message")
        if isinstance(message, str) and message.strip():
            diagnostics["codex_error_messages"].append(message.strip())
    return diagnostics


def _require_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return query.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
