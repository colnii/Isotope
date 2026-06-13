# Research Recall Product Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `research.recall` readable in capacity result summaries and desktop capacity card details.

**Architecture:** Project `research.recall` into low-sensitive `agent_loop_research_recall_*` fields in the existing capacity result module. Keep desktop extraction/formatting in `capacityCallView.ts`, and let `CapacityCallDetails.svelte` render already-filtered preview records.

**Tech Stack:** Python 3.13, pytest, Svelte 5, Vitest, existing desktop view helpers.

---

### Task 1: Capacity Result Projection

**Files:**
- Modify: `tests/unit/features/supervisor/test_capacity_module_boundaries.py`
- Modify: `src/isotope/features/supervisor/commands/capacity/capacity_result.py`

- [ ] **Step 1: Write the failing projection test**

Add a test that builds an `agent_loop` payload whose capability run is:

```python
{
    "capability_id": "research.recall",
    "research_recall": {
        "status": "ok",
        "content_policy": "research_report_artifact_preview_only",
        "retrieval": {"backend": "hybrid", "dense_status": "ok"},
        "results": [
            {
                "run_id": "run_research",
                "artifact_id": "artifact_report",
                "artifact_type": "research.report",
                "summary": "Stored research report preview.",
                "ref": {"ref_type": "artifact", "scope": "run", "run_id": "run_research", "artifact_id": "artifact_report"},
                "source_refs": [{"ref_type": "url", "url": "https://example.com"}],
                "provenance": {"execution_id": "exec_research"},
                "content": "raw report body must not leak",
            }
        ],
    },
}
```

Expected summary fields include status, count, content policy, retrieval backend,
dense status, and a preview list without `content`.

- [ ] **Step 2: Run the test to verify failure**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_capacity_module_boundaries.py::test_capacity_result_extracts_research_recall_preview_fields -q
```

Expected: FAIL because `agent_loop_research_recall_*` fields do not exist.

- [ ] **Step 3: Implement the projection**

Add `_agent_loop_research_recall_result(...)` next to the existing research
search/promote helpers. It should copy only preview-safe keys and cap previews to
five records.

- [ ] **Step 4: Run focused tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_capacity_module_boundaries.py tests/unit/features/supervisor/test_supervisor_capacity_path.py -q
```

Expected: PASS.

### Task 2: Desktop View Helpers

**Files:**
- Modify: `apps/desktop/src/lib/view/capacityCallView.test.ts`
- Modify: `apps/desktop/src/lib/view/capacityCallView.ts`

- [ ] **Step 1: Write failing helper tests**

Add tests that:

- `capacityCallSummary(...)` returns `召回研究 · reports: 1 · hybrid/ok`;
- `researchRecallPreviewsForDetailSection(...)` extracts one valid preview and
  ignores invalid items.

- [ ] **Step 2: Run helper tests to verify failure**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/view/capacityCallView.test.ts
```

Expected: FAIL because the helper and summary logic do not exist.

- [ ] **Step 3: Implement helper logic**

Add a `ResearchRecallPreview` type, a `researchRecallPreviewsForDetailSection`
export, and a `research.recall` branch in `capacityCallSummary(...)`.

- [ ] **Step 4: Run helper tests**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/view/capacityCallView.test.ts
```

Expected: PASS.

### Task 3: Desktop Detail Rendering

**Files:**
- Modify: `apps/desktop/src/lib/components/main/CapacityCallDetails.test.ts`
- Modify: `apps/desktop/src/lib/components/main/CapacityCallDetails.svelte`

- [ ] **Step 1: Write failing component contract test**

Assert that `CapacityCallDetails.svelte` imports
`researchRecallPreviewsForDetailSection(section)`, renders preview summary,
artifact id, and run id, and keeps the `结果原文` disclosure.

- [ ] **Step 2: Run component test to verify failure**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/components/main/CapacityCallDetails.test.ts
```

Expected: FAIL because the component does not reference research recall previews.

- [ ] **Step 3: Implement rendering**

In each detail section, compute both source previews and recall previews. Render
source previews first when present; otherwise render recall previews; otherwise
fall back to raw JSON.

- [ ] **Step 4: Run desktop tests**

Run:

```bash
cd apps/desktop && npm test -- --run src/lib/view/capacityCallView.test.ts src/lib/components/main/CapacityCallDetails.test.ts
```

Expected: PASS.

### Task 4: Verification and Commit

**Files:**
- Modify: `docs/current/agent-task-queue.md`
- Modify: `docs/current/supervisor-command-reference.md`

- [ ] **Step 1: Update docs**

Document that `research.recall` now has readable capacity/desktop projection but
is not yet auto-selected by planner prompts.

- [ ] **Step 2: Run verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_capacity_module_boundaries.py tests/unit/features/supervisor/test_supervisor_capacity_path.py tests/unit/capabilities/research/test_recall.py -q
cd apps/desktop && npm test -- --run src/lib/view/capacityCallView.test.ts src/lib/components/main/CapacityCallDetails.test.ts
git diff --check
scripts/dev-eval changed_surface --base origin/main --json
```

If the dev-eval gate returns `eval_required=true`, run its
`recommended_command` and read the generated reviewer prompt.

- [ ] **Step 3: Commit and push**

Commit with:

```bash
git commit -m "feat(desktop): render research recall previews"
git push
```
