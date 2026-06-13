# Research Artifact RAG Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `research.recall` as a non-memory caller of the generic local RAG index, using only `research.report` artifact preview metadata.

**Architecture:** Keep artifact-specific enumeration and preview mapping in `src/isotope/features/research/recall.py`. Wire the capability through the existing `src/isotope/capabilities/research.py` and catalog/runner dispatch. The generic dense index stays in `src/isotope/rag/index.py`.

**Tech Stack:** Python 3.13, pytest, existing `ArtifactStore`, `RetrievalDocument`, `HybridRetriever`, and `build_rag_index`.

---

### Task 1: Research Preview Recall Helper

**Files:**
- Create: `tests/unit/features/research/test_research_recall.py`
- Create: `src/isotope/features/research/recall.py`

- [ ] **Step 1: Write failing helper tests**

Cover preview-only artifact recall, dense local retrieval, default
`bm25/not_configured`, and `run_id` filtering.

- [ ] **Step 2: Implement helper**

Scan `runs/*/artifacts/*.json`, keep `research.report`, map top-level metadata
to `RetrievalDocument`, build an optional RAG index, run `HybridRetriever`, and
return preview-safe payloads.

### Task 2: Capability Runner Integration

**Files:**
- Create: `tests/unit/capabilities/research/test_recall.py`
- Modify: `src/isotope/capabilities/research.py`
- Modify: `src/isotope/capabilities/runner.py`
- Modify: `src/isotope/capabilities/catalog.py`

- [ ] **Step 1: Write failing capability tests**

Assert default catalog discovers `research.recall`, run plans are launchable with
`root/query`, and runner output hides report content while returning artifact
metadata and retrieval status.

- [ ] **Step 2: Implement capability**

Add validation for `root`, `query`, optional `run_id`, positive `limit`, and
optional `dense_retrieval`. Dispatch to the research preview recall helper and
return `research_recall`.

### Task 3: Docs, Verification, Commit

**Files:**
- Modify: `docs/current/terminology.md`
- Modify: `docs/current/agent-task-queue.md`

- [ ] **Step 1: Update docs**

Document `research.recall` as preview-only artifact recall and the second caller
of `rag.index`.

- [ ] **Step 2: Run verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/research/test_research_recall.py tests/unit/capabilities/research/test_recall.py tests/unit/capabilities/test_research.py tests/unit/rag -q
git diff --check
scripts/dev-eval changed_surface --base origin/main --json
```

If `changed_surface` requires an eval, run its recommended command and inspect
the generated reviewer prompt.

- [ ] **Step 3: Commit and push**

Commit with `feat(research): add artifact preview recall` and push the feature
branch for review.
