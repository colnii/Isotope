"""Provider boundaries for web research."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from ...integrations.codex.cli import CodexCliBackend, CodexCliBackendConfig
from ...integrations.codex.task import CodexTaskConfig, CodexTaskRequest


class ResearchProvider(Protocol):
    provider_name: str

    def run(self, query: str) -> dict[str, Any]:
        """Return a structured WebResearchRun-like payload."""


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

    def __init__(self, backend: Callable[[str], str]):
        self.backend = backend

    def run(self, query: str) -> dict[str, Any]:
        clean_query = _require_query(query)
        prompt = build_codex_research_prompt(clean_query)
        raw_output = self.backend(prompt)
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
                return extract_codex_agent_message_text(content) or content
            stdout = transcript.get("stdout")
            if isinstance(stdout, str):
                return extract_codex_agent_message_text(stdout) or stdout
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


def _require_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return query.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
