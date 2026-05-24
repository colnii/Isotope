# Web Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Codex delegated web research slice with shared research substrate, artifact/provenance persistence, and convenient CLI test entrypoints.

**Architecture:** Add a focused `src/isotope/features/research/` package. `ResearchFlow` owns validation, provider invocation, artifact persistence, and low-sensitive output; `CodexDelegatedResearchProvider` adapts the existing Codex CLI backend; Supervisor CLI remains a thin proxy over `ResearchFlow`.

**Tech Stack:** Python 3.13, dataclasses, existing `ProductCore` / `InProcessServer`, `ArtifactStore`, existing Codex CLI integration, pytest, subprocess CLI tests.

---

## File Structure

- Create `src/isotope/features/research/__init__.py`: public exports for research feature.
- Create `src/isotope/features/research/models.py`: dataclasses and validation for `ResearchSource`, `ResearchClaim`, `ResearchReport`, `WebResearchRun`, `ResearchFlowResult`.
- Create `src/isotope/features/research/providers.py`: provider protocol, fake provider, Codex delegated provider, prompt construction, JSON extraction.
- Create `src/isotope/features/research/flow.py`: shared `ResearchFlow` over `ProductCore`; invokes provider, validates, persists `research.raw_transcript` and `research.report` artifacts.
- Create `src/isotope/features/research/runner.py`: standalone CLI test entrypoint.
- Modify `src/isotope/runtime/in_process_workspace_artifacts.py`: allow `create_source_artifact` to persist `artifact_type="research.report"` and `artifact_type="research.raw_transcript"`.
- Modify `src/isotope/execution/executor.py`: preserve optional write-artifact `artifact_type` from proposal payload instead of hardcoding `"text"`.
- Modify `src/isotope/features/supervisor/commands/parser.py`: add `research` command arguments.
- Modify `src/isotope/features/supervisor/runner.py`: add handler that calls `ResearchFlow`.
- Modify `pyproject.toml`: add `isotope-research = "isotope.features.research.runner:main"` next to existing user-facing scripts.
- Create `tests/isotope/test_research_models.py`.
- Create `tests/isotope/test_research_flow.py`.
- Create `tests/isotope/test_research_cli.py`.
- Create `tests/isotope/test_supervisor_research_cli.py`.
- Modify or extend `tests/isotope/test_source_artifact_setup_helper.py` for research artifact type support.

## Task 1: Research Artifact Types

**Files:**
- Modify: `src/isotope/runtime/in_process_workspace_artifacts.py`
- Modify: `src/isotope/execution/executor.py`
- Test: `tests/isotope/test_source_artifact_setup_helper.py`

- [ ] **Step 1: Write failing test for allowed research artifact types**

Append this test to `tests/isotope/test_source_artifact_setup_helper.py`:

```python
def test_source_artifact_helper_allows_research_artifact_types(tmp_path):
    api = InProcessServer(tmp_path)
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="store research artifacts")

    report = api.create_source_artifact(
        run["run_id"],
        summary="research report for agent memory",
        content='{"status": "ok", "sources": []}',
        artifact_type="research.report",
    )
    raw = api.create_source_artifact(
        run["run_id"],
        summary="raw Codex research transcript",
        content='{"stdout": "raw"}',
        artifact_type="research.raw_transcript",
    )

    assert report["artifact_type"] == "research.report"
    assert raw["artifact_type"] == "research.raw_transcript"
    assert api.get_artifact_record(report["artifact_ref"])["artifact_type"] == "research.report"
    assert api.get_artifact_record(raw["artifact_ref"])["artifact_type"] == "research.raw_transcript"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_source_artifact_setup_helper.py::test_source_artifact_helper_allows_research_artifact_types -q
```

Expected: FAIL with `ValueError: artifact_type must be text`.

- [ ] **Step 3: Allow explicit source artifact types**

In `src/isotope/runtime/in_process_workspace_artifacts.py`, add a small allowlist near the imports:

```python
SOURCE_ARTIFACT_TYPES = {
    "text",
    "research.report",
    "research.raw_transcript",
}
```

Change the validation and compiler intent inside `create_source_artifact`:

```python
        if artifact_type not in SOURCE_ARTIFACT_TYPES:
            raise ValueError("artifact_type is not supported")
```

After compiling the proposal, preserve the artifact type:

```python
        proposal.payload["artifact_type"] = artifact_type
```

In `src/isotope/execution/executor.py`, change the write-artifact creation block from hardcoded `"text"` to:

```python
                artifact_type = proposal.payload.get("artifact_type", "text")
                if not isinstance(artifact_type, str) or not artifact_type:
                    artifact_type = "text"
                artifact = self.artifact_store.create_artifact(
                    run_id=proposal.run_id,
                    execution_id=execution.execution_id,
                    artifact_type=artifact_type,
                    summary=summary,
                    content=str(proposal.payload.get("text", "")),
                    proposal_id=proposal.proposal_id,
                    decision_id=decision.decision_id,
                    basis_refs=proposal.payload.get("basis_refs"),
                    source_refs=proposal.payload.get("source_refs"),
                )
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_source_artifact_setup_helper.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/runtime/in_process_workspace_artifacts.py src/isotope/execution/executor.py tests/isotope/test_source_artifact_setup_helper.py
git commit -m "feat(research): allow research artifact types"
```

## Task 2: Research Models and Validation

**Files:**
- Create: `src/isotope/features/research/__init__.py`
- Create: `src/isotope/features/research/models.py`
- Test: `tests/isotope/test_research_models.py`

- [ ] **Step 1: Write model validation tests**

Create `tests/isotope/test_research_models.py`:

```python
from __future__ import annotations

import pytest

from isotope.features.research.models import WebResearchRun


def _valid_payload() -> dict:
    return {
        "research_id": "research_001",
        "query": "agent memory retrieval",
        "provider": "fake",
        "created_at": "2026-05-24T00:00:00Z",
        "status": "ok",
        "evidence_status": "complete",
        "sources": [
            {
                "source_id": "src_001",
                "title": "Retrieval design",
                "url": "https://example.com/retrieval",
                "snippet": "retrieval with provenance",
                "why_used": "explains source-backed retrieval",
                "retrieved_at": "2026-05-24T00:00:00Z",
                "provider_rank": 1,
            }
        ],
        "report": {
            "summary": "Retrieval should keep provenance.",
            "claims": [
                {
                    "text": "Claims need source refs.",
                    "source_ids": ["src_001"],
                    "confidence": "medium",
                }
            ],
            "limitations": ["single source"],
            "next_queries": ["controlled expand grants"],
        },
        "provenance": {"provider": "fake"},
    }


def test_web_research_run_requires_source_backed_claims():
    run = WebResearchRun.from_dict(_valid_payload())

    assert run.evidence_status == "complete"
    assert run.to_dict()["report"]["claims"][0]["source_ids"] == ["src_001"]


def test_web_research_run_marks_missing_sources_as_incomplete_evidence():
    payload = _valid_payload()
    payload["sources"] = []
    payload["evidence_status"] = "complete"

    run = WebResearchRun.from_dict(payload)

    assert run.evidence_status == "incomplete_evidence"


def test_web_research_run_rejects_claims_with_unknown_source_ids():
    payload = _valid_payload()
    payload["report"]["claims"][0]["source_ids"] = ["missing_src"]

    with pytest.raises(ValueError, match="unknown source_id"):
        WebResearchRun.from_dict(payload)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_models.py -q
```

Expected: FAIL because `isotope.features.research.models` does not exist.

- [ ] **Step 3: Implement models**

Create `src/isotope/features/research/__init__.py`:

```python
"""Web research feature helpers."""

from .models import ResearchClaim, ResearchReport, ResearchSource, WebResearchRun

__all__ = [
    "ResearchClaim",
    "ResearchReport",
    "ResearchSource",
    "WebResearchRun",
]
```

Create `src/isotope/features/research/models.py` with focused dataclasses:

```python
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
        for claim in report.claims:
            for source_id in claim.source_ids:
                if source_id not in source_ids:
                    raise ValueError(f"unknown source_id in report claim: {source_id}")
        evidence_status = _optional_string(data, "evidence_status", default="partial")
        if not sources:
            evidence_status = "incomplete_evidence"
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
```

- [ ] **Step 4: Run model tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_models.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/research tests/isotope/test_research_models.py
git commit -m "feat(research): add web research models"
```

## Task 3: Provider Contract and Fake Provider

**Files:**
- Create: `src/isotope/features/research/providers.py`
- Test: `tests/isotope/test_research_provider.py`

- [ ] **Step 1: Write provider tests**

Create `tests/isotope/test_research_provider.py`:

```python
from __future__ import annotations

import json

import pytest

from isotope.features.research.providers import (
    CodexDelegatedResearchProvider,
    FakeResearchProvider,
    extract_research_json,
)


def test_fake_research_provider_returns_source_backed_report():
    provider = FakeResearchProvider()

    payload = provider.run("agent memory retrieval")

    assert payload["query"] == "agent memory retrieval"
    assert payload["provider"] == "fake"
    assert payload["sources"][0]["source_id"] == "src_001"
    assert payload["report"]["claims"][0]["source_ids"] == ["src_001"]


def test_extract_research_json_accepts_fenced_json():
    raw = 'prefix\\n```json\\n{"status":"ok","sources":[]}\\n```\\nsuffix'

    assert extract_research_json(raw) == {"status": "ok", "sources": []}


def test_extract_research_json_rejects_missing_json_object():
    with pytest.raises(ValueError, match="research JSON object"):
        extract_research_json("no structured payload")


def test_codex_delegated_provider_builds_research_prompt():
    calls = []

    def backend(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps(FakeResearchProvider().run("agent memory retrieval"))

    provider = CodexDelegatedResearchProvider(backend=backend)
    payload = provider.run("agent memory retrieval")

    assert payload["provider"] == "codex_delegated"
    assert "sources" in calls[0]
    assert "report" in calls[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_provider.py -q
```

Expected: FAIL because `providers.py` does not exist.

- [ ] **Step 3: Implement providers**

Create `src/isotope/features/research/providers.py`:

```python
"""Provider boundaries for web research."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Protocol


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
        payload = extract_research_json(raw_output)
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
    fenced = re.search(r"```(?:json)?\\s*(\\{.*?\\})\\s*```", raw_output, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else raw_output.strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("research JSON object was not found") from exc
    if not isinstance(payload, dict):
        raise ValueError("research JSON object must be a dict")
    return payload


def _require_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return query.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

- [ ] **Step 4: Run provider tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_provider.py -q
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/research/providers.py tests/isotope/test_research_provider.py
git commit -m "feat(research): add delegated provider contract"
```

## Task 4: ResearchFlow Persistence

**Files:**
- Create: `src/isotope/features/research/flow.py`
- Test: `tests/isotope/test_research_flow.py`

- [ ] **Step 1: Write flow tests**

Create `tests/isotope/test_research_flow.py`:

```python
from __future__ import annotations

import json

from isotope.features.research.flow import ResearchFlow
from isotope.features.research.providers import FakeResearchProvider


def test_research_flow_persists_raw_and_normalized_artifacts(tmp_path):
    flow = ResearchFlow.in_process(tmp_path, provider=FakeResearchProvider())

    result = flow.search("agent memory retrieval")

    payload = result.to_dict()
    assert payload["status"] == "ok"
    assert payload["research"]["evidence_status"] == "complete"
    assert len(payload["artifact_refs"]) == 2
    records = [
        flow.core.runtime.get_artifact_record(ref)
        for ref in result.artifact_refs
    ]
    assert [record["artifact_type"] for record in records] == [
        "research.raw_transcript",
        "research.report",
    ]
    assert records[1]["summary"] == "Fake research summary for agent memory retrieval."


def test_research_flow_marks_missing_sources_incomplete(tmp_path):
    class NoSourcesProvider:
        provider_name = "no_sources"

        def run(self, query: str) -> dict:
            return {
                "research_id": "research_no_sources",
                "query": query,
                "provider": "no_sources",
                "created_at": "2026-05-24T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [],
                "report": {"summary": "no sources"},
                "provenance": {"provider": "no_sources"},
            }

    flow = ResearchFlow.in_process(tmp_path, provider=NoSourcesProvider())

    result = flow.search("unsupported claim")

    assert result.research.evidence_status == "incomplete_evidence"
    normalized = flow.core.runtime.get_artifact_record(result.artifact_refs[1])
    assert normalized["artifact_type"] == "research.report"


def test_research_flow_rejects_unknown_claim_source_without_success_artifact(tmp_path):
    class BadClaimProvider:
        provider_name = "bad_claim"

        def run(self, query: str) -> dict:
            return {
                "research_id": "research_bad_claim",
                "query": query,
                "provider": "bad_claim",
                "created_at": "2026-05-24T00:00:00Z",
                "status": "ok",
                "evidence_status": "complete",
                "sources": [],
                "report": {
                    "summary": "bad claim",
                    "claims": [{"text": "bad", "source_ids": ["missing"]}],
                },
                "provenance": {"provider": "bad_claim"},
            }

    flow = ResearchFlow.in_process(tmp_path, provider=BadClaimProvider())

    result = flow.search("bad claim")

    assert result.status == "validation_failed"
    assert result.research is None
    assert result.artifact_refs == ()
    assert "unknown source_id" in result.error["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_flow.py -q
```

Expected: FAIL because `flow.py` does not exist.

- [ ] **Step 3: Implement `ResearchFlow`**

Create `src/isotope/features/research/flow.py`:

```python
"""Shared web research feature flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core import ProductCore
from ...platform.schemas.refs import ResourceRef
from .models import WebResearchRun
from .providers import FakeResearchProvider, ResearchProvider


@dataclass(frozen=True)
class ResearchFlowResult:
    status: str
    research: WebResearchRun | None
    artifact_refs: tuple[ResourceRef, ...] = ()
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "artifact_refs": [ref.to_dict() for ref in self.artifact_refs],
        }
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
        except Exception as exc:
            return ResearchFlowResult(
                status="validation_failed",
                research=None,
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
            artifact_refs=artifact_refs,
        )


def _require_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    return query.strip()
```

- [ ] **Step 4: Run flow tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_flow.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/research/flow.py tests/isotope/test_research_flow.py
git commit -m "feat(research): persist delegated research artifacts"
```

## Task 5: Standalone Research CLI

**Files:**
- Create: `src/isotope/features/research/runner.py`
- Modify: `pyproject.toml`
- Test: `tests/isotope/test_research_cli.py`

- [ ] **Step 1: Write CLI tests**

Create `tests/isotope/test_research_cli.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.research.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_research_cli_search_returns_json(tmp_path):
    result = _run_cli(
        "search",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["research"]["provider"] == "fake"
    assert payload["research"]["sources"][0]["url"] == "https://example.com/isotope-research"
    assert len(payload["artifact_refs"]) == 2


def test_research_cli_requires_query(tmp_path):
    result = _run_cli("search", "--root", str(tmp_path), "--provider", "fake", "--json")

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "research_runner_error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_cli.py -q
```

Expected: FAIL because `runner.py` does not exist.

- [ ] **Step 3: Implement CLI runner**

Create `src/isotope/features/research/runner.py`:

```python
"""CLI runner for the web research feature."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .flow import ResearchFlow
from .providers import FakeResearchProvider


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Isotope research feature flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    search_parser = subparsers.add_parser("search", help="Run delegated research.")
    search_parser.add_argument("--root", required=True, help="Runtime root directory.")
    search_parser.add_argument("--query", help="Research query.")
    search_parser.add_argument(
        "--provider",
        default="fake",
        choices=("fake",),
        help="Research provider. First implementation supports fake for tests.",
    )
    search_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            if not args.query:
                raise ValueError("research search requires --query")
            flow = ResearchFlow.in_process(
                Path(args.root),
                provider=FakeResearchProvider(),
            )
            payload = flow.search(args.query).to_dict()
            if args.json:
                _print_json(payload)
            else:
                _print_plain(payload)
            return 0
    except ValueError as exc:
        error = {
            "status": "error",
            "error": {"code": "research_runner_error", "message": str(exc)},
        }
        if getattr(args, "json", False):
            _print_json(error)
        else:
            print(f"error: {exc}")
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


def _print_plain(payload: dict[str, Any]) -> None:
    research = payload.get("research") or {}
    print(f"status: {payload['status']}")
    print(f"query: {research.get('query', '')}")
    print(f"evidence: {research.get('evidence_status', '')}")
    for source in research.get("sources", []):
        print(f"- {source['title']} {source['url']}")


if __name__ == "__main__":
    raise SystemExit(main())
```

If `pyproject.toml` user-facing scripts are kept current, add:

```toml
isotope-research = "isotope.features.research.runner:main"
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_cli.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/research/runner.py tests/isotope/test_research_cli.py pyproject.toml
git commit -m "feat(research): add research CLI entrypoint"
```

## Task 6: Supervisor Research Thin Proxy

**Files:**
- Modify: `src/isotope/features/supervisor/commands/parser.py`
- Modify: `src/isotope/features/supervisor/runner.py`
- Test: `tests/isotope/test_supervisor_research_cli.py`

- [ ] **Step 1: Write Supervisor CLI test**

Create `tests/isotope/test_supervisor_research_cli.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "isotope.features.supervisor.runner", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_supervisor_research_command_proxies_research_flow(tmp_path):
    result = _run_cli(
        "research",
        "--root",
        str(tmp_path),
        "--query",
        "agent memory retrieval",
        "--provider",
        "fake",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["research"]["query"] == "agent memory retrieval"
    assert payload["research"]["provider"] == "fake"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_supervisor_research_cli.py -q
```

Expected: FAIL with argparse rejecting `research`.

- [ ] **Step 3: Add parser command**

In `src/isotope/features/supervisor/commands/parser.py`, add near other top-level commands:

```python
    research_parser = subparsers.add_parser(
        "research",
        help="Run delegated research through the shared research flow.",
    )
    research_parser.add_argument("--root", required=True, help="Runtime root directory.")
    research_parser.add_argument("--query", required=True, help="Research query.")
    research_parser.add_argument(
        "--provider",
        default="fake",
        choices=("fake",),
        help="Research provider. First implementation supports fake for tests.",
    )
    research_parser.add_argument("--json", action="store_true", help="Print JSON output.")
```

- [ ] **Step 4: Add runner handler**

In `src/isotope/features/supervisor/runner.py`, import research helpers:

```python
from ..research.flow import ResearchFlow
from ..research.providers import FakeResearchProvider
```

Add handler:

```python
def _handle_research_command(args: argparse.Namespace, *, api) -> int:
    flow = ResearchFlow.in_process(
        Path(args.root),
        provider=FakeResearchProvider(),
    )
    payload = flow.search(args.query).to_dict()
    if args.json:
        _print_json(payload)
    else:
        research = payload.get("research") or {}
        print("[Codex Supervisor Research]")
        print(f"status: {payload['status']}")
        print(f"query: {research.get('query', '')}")
        print(f"evidence: {research.get('evidence_status', '')}")
    return 0
```

Add it to `_COMMAND_HANDLERS`:

```python
    "research": _handle_research_command,
```

- [ ] **Step 5: Run Supervisor CLI test**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_supervisor_research_cli.py -q
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/features/supervisor/commands/parser.py src/isotope/features/supervisor/runner.py tests/isotope/test_supervisor_research_cli.py
git commit -m "feat(supervisor): proxy research command"
```

## Task 7: Codex Delegated Provider Smoke Path

**Files:**
- Modify: `src/isotope/features/research/providers.py`
- Modify: `src/isotope/features/research/runner.py`
- Test: `tests/isotope/test_research_provider.py`

- [ ] **Step 1: Add backend construction tests without launching Codex**

Append to `tests/isotope/test_research_provider.py`:

```python
from isotope.features.research.providers import build_codex_cli_research_backend


def test_build_codex_cli_research_backend_returns_callable(tmp_path):
    backend = build_codex_cli_research_backend(
        workspace_root=tmp_path,
        executable="codex",
        executable_resolver=lambda name: "/usr/bin/codex",
        process_runner=lambda *args, **kwargs: type(
            "Completed",
            (),
            {"stdout": '{"sources":[],"report":{"summary":"empty"}}', "stderr": "", "returncode": 0},
        )(),
    )

    assert callable(backend)
    assert json.loads(backend("research prompt")) == {
        "sources": [],
        "report": {"summary": "empty"},
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_provider.py::test_build_codex_cli_research_backend_returns_callable -q
```

Expected: FAIL because helper does not exist.

- [ ] **Step 3: Implement backend helper**

In `src/isotope/features/research/providers.py`, add imports:

```python
from pathlib import Path

from ...integrations.codex.cli import CodexCliBackend, CodexCliBackendConfig
from ...integrations.codex.task import (
    CodexTaskConfig,
    CodexTaskRequest,
)
```

Add helper:

```python
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
            artifact_policy={"capture": ["transcript"], "full_content_in_events": False, "full_content_in_read_model": False},
            basis_event_ids=[],
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
                return content
            stdout = transcript.get("stdout")
            return stdout if isinstance(stdout, str) else content
        return result.summary

    return run_prompt
```

Extend `runner.py` provider choices to include `"codex"` and resolve:

```python
from .providers import (
    CodexDelegatedResearchProvider,
    FakeResearchProvider,
    build_codex_cli_research_backend,
)
```

Add CLI args `--workspace-root`, `--codex-executable`, `--codex-home`, `--model`, `--timeout-seconds`.

Provider resolution:

```python
def _provider_from_args(args):
    if args.provider == "fake":
        return FakeResearchProvider()
    if args.provider == "codex":
        return CodexDelegatedResearchProvider(
            build_codex_cli_research_backend(
                workspace_root=args.workspace_root or Path.cwd(),
                executable=args.codex_executable,
                codex_home=args.codex_home,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
            )
        )
    raise ValueError(f"unsupported research provider: {args.provider}")
```

- [ ] **Step 4: Run provider and CLI tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_provider.py tests/isotope/test_research_cli.py -q
```

Expected: all tests pass. No real Codex process is launched by pytest.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/features/research/providers.py src/isotope/features/research/runner.py tests/isotope/test_research_provider.py tests/isotope/test_research_cli.py
git commit -m "feat(research): add Codex delegated provider entry"
```

## Task 8: Retrieval/Search Integration and Docs Sync

**Files:**
- No change: `src/isotope/features/search/flow.py` remains local project/task/file search in this slice.
- Test: `tests/isotope/test_research_flow.py`
- Modify: `docs/superpowers/specs/2026-05-24-web-research-design.md`

- [ ] **Step 1: Add retrieval/search assertion**

Extend `tests/isotope/test_research_flow.py` with:

```python
def test_research_report_can_be_found_through_file_artifact_record(tmp_path):
    flow = ResearchFlow.in_process(tmp_path, provider=FakeResearchProvider())

    result = flow.search("agent memory retrieval")
    record = flow.core.runtime.get_artifact_record(result.artifact_refs[1])

    assert record["artifact_type"] == "research.report"
    assert "Fake research summary" in record["summary"]
    assert record["source_refs"] == [result.artifact_refs[0].to_dict()]
```

- [ ] **Step 2: Run test**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_flow.py -q
```

Expected: pass because Task 4 already passed `source_refs=[raw_artifact["artifact_ref"]]` when creating `research.report`.

- [ ] **Step 3: Update design status**

In `docs/superpowers/specs/2026-05-24-web-research-design.md`, change:

```markdown
状态：`draft for user review`
```

to:

```markdown
状态：`implementation slice planned`
```

Add a short note under section 9:

```markdown
Implementation plan: `docs/superpowers/plans/2026-05-24-web-research-implementation-plan.md`.
```

- [ ] **Step 4: Run focused docs and tests**

Run:

```bash
git diff --check
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope/test_research_flow.py tests/isotope/test_research_cli.py tests/isotope/test_supervisor_research_cli.py -q
```

Expected: diff check passes; focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/isotope/test_research_flow.py docs/superpowers/specs/2026-05-24-web-research-design.md
git commit -m "docs(research): link implementation plan"
```

## Final Verification

- [ ] Run the targeted test suite:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/isotope/test_source_artifact_setup_helper.py \
  tests/isotope/test_research_models.py \
  tests/isotope/test_research_provider.py \
  tests/isotope/test_research_flow.py \
  tests/isotope/test_research_cli.py \
  tests/isotope/test_supervisor_research_cli.py \
  -q
```

Expected: all selected tests pass.

- [ ] Run the manual fake-provider smoke:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.research.runner search \
  --root /tmp/isotope-research-smoke \
  --query "agent memory retrieval" \
  --provider fake \
  --json
```

Expected: JSON output has `status: ok`, `research.sources`, `research.report`, and two artifact refs.

- [ ] Run the Supervisor fake-provider smoke:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.features.supervisor.runner research \
  --root /tmp/isotope-supervisor-research-smoke \
  --query "agent memory retrieval" \
  --provider fake \
  --json
```

Expected: same research payload shape through Supervisor thin proxy.

- [ ] Run full relevant regression:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/isotope -q
```

Expected: pass. If skipped due runtime, report that targeted suite passed and full suite was not run.
