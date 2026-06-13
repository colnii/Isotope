# Research Recall Live LLM Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded dev-eval slice that checks whether a real LLM can choose and call `research.recall` against an existing stored `research.report`.

**Architecture:** Reuse the existing Supervisor conversation eval harness so the model still chooses from capability metadata instead of a fixed route. Seed a low-sensitivity `research.report` artifact fixture, add one scenario with input-fragment gates, and expose it through the existing opt-in live eval test.

**Tech Stack:** Python 3.13, pytest, Isotope `run_supervisor_conversation_events`, `ArtifactStore`, `research.recall`.

---

### Task 1: Scenario And Fixture Red Test

**Files:**
- Modify: `tests/unit/dev_evals/test_cases.py`
- Modify: `tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py`
- Modify later: `src/isotope/dev_evals/cases.py`
- Modify later: `src/isotope/dev_evals/fixtures.py`

- [ ] **Step 1: Write failing catalog and fixture tests**

Add tests that expect `research_recall_seeded` to be a valid fixture and verify it seeds a `research.report` with `RAG_RECALL_EVAL_MARKER`.

```python
def test_research_recall_scenario_requires_marker_input():
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "research_recall_fixture"
    )

    assert "RAG_RECALL_EVAL_MARKER" in scenario.user_message
    assert scenario.fixture == "research_recall_seeded"
    assert scenario.required_input_fragments == ("RAG_RECALL_EVAL_MARKER",)
```

```python
def test_research_recall_fixture_seeds_preview_only_report(tmp_path):
    state_root, _workspace = prepare_fixture(tmp_path, "research_recall_seeded")
    artifacts = ArtifactStore(state_root).list_artifacts("run_research_recall_eval")

    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "research.report"
    assert "RAG_RECALL_EVAL_MARKER" in artifacts[0].summary
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/dev_evals/test_cases.py::test_research_recall_scenario_requires_marker_input \
  tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py::test_research_recall_fixture_seeds_preview_only_report \
  -q
```

Expected: fail because the scenario and fixture do not exist yet.

- [ ] **Step 3: Add scenario and seeded fixture**

Add a `research_recall_fixture` scenario and a `research_recall_seeded` fixture that writes one `research.report` artifact. The fixture content may include `must_not_leak`; the scenario should only expose summary/metadata through `research.recall`.

```python
CapabilityScenario(
    "research_recall_fixture",
    ("research.recall",),
    (
        "Use existing stored research reports to recall what we already learned "
        "about RAG_RECALL_EVAL_MARKER. Do not run a new web search."
    ),
    "research_recall_seeded",
    required_input_fragments=("RAG_RECALL_EVAL_MARKER",),
)
```

- [ ] **Step 4: Verify green**

Run the same targeted pytest command and expect both tests to pass.

### Task 2: Conversation Harness Gate

**Files:**
- Modify: `tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py`

- [ ] **Step 1: Write failing harness test**

Add a deterministic provider test that calls `research.recall` with the marker and expects the case to pass without leaking raw content.

```python
def test_harness_runs_research_recall_case_against_seeded_report(tmp_path):
    scenario = next(
        item for item in scenario_catalog() if item.case_id == "research_recall_fixture"
    )
    provider = DeterministicScenarioProvider([
        {
            "kind": "call_capability",
            "capacity_id": "research.recall",
            "arguments": {"query": "RAG_RECALL_EVAL_MARKER", "limit": 5},
            "rationale": "Need existing research report recall.",
        },
        {
            "kind": "direct_answer",
            "answer": "Recalled the stored report preview.",
            "answer_basis": {
                "kind": "observation",
                "capacity_ids": ["research.recall"],
                "reason": "Research recall observation returned the marker.",
            },
            "rationale": "Observation is enough.",
        },
    ])

    report = run_scenarios([scenario], root=tmp_path, provider=provider, live=False)

    assert report["status"] == "passed"
    assert report["cases"][0]["steps"][0]["capacity_id"] == "research.recall"
    assert "raw_response" not in json.dumps(report)
    assert "must_not_leak" not in json.dumps(report).lower()
```

- [ ] **Step 2: Run test to verify red or current integration gap**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py::test_harness_runs_research_recall_case_against_seeded_report \
  -q
```

Expected before implementation: fail because fixture/scenario is missing.

- [ ] **Step 3: Verify green after Task 1 implementation**

Run the same command and expect pass.

### Task 3: Opt-In Real LLM Smoke

**Files:**
- Modify: `tests/evals/test_supervisor_capacity_live_eval.py`
- Modify: `docs/current/agent-task-queue.md`

- [ ] **Step 1: Add live eval test**

Add a second opt-in test that runs `run_live_suite(case_id="research_recall_fixture")`. If no provider is configured, it should assert the existing blocked fallback; if a provider is configured, it should require the suite to pass.

```python
def test_live_supervisor_research_recall_eval_records_real_provider_choice(tmp_path):
    resolution = resolve_llm_chat_provider()
    report = run_live_suite(root=tmp_path, case_id="research_recall_fixture", case_limit=1)

    if resolution.provider is None:
        assert report["status"] == "blocked"
        assert report["deterministic_fallback"]["status"] == "passed"
    else:
        assert report["status"] == "passed"
        assert report["cases"][0]["capability_under_test"] == ["research.recall"]
        assert "raw_response" not in repr(report)
```

- [ ] **Step 2: Run skipped-by-default test**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/evals/test_supervisor_capacity_live_eval.py -q
```

Expected: skipped unless `ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL=1`.

- [ ] **Step 3: Run real provider smoke**

Run:

```bash
ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL=1 PYTHONPATH=src \
  /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/evals/test_supervisor_capacity_live_eval.py::test_live_supervisor_research_recall_eval_records_real_provider_choice \
  -q
```

Expected with the currently configured provider: pass if the model selects `research.recall`; fail with reviewer prompt evidence if model behavior diverges.

### Task 4: Required Verification And Commit

**Files:**
- All changed files

- [ ] **Step 1: Run targeted tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/dev_evals/test_cases.py \
  tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py \
  tests/evals/test_supervisor_capacity_live_eval.py \
  -q
```

- [ ] **Step 2: Run changed-surface dev eval gate**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python scripts/dev-eval changed_surface --base origin/main --json
```

If `eval_required=true`, run the recommended smoke command and inspect reviewer prompts.

- [ ] **Step 3: Commit and push**

```bash
git add docs/superpowers/plans/2026-06-14-research-recall-live-llm-eval.md \
  src/isotope/dev_evals/cases.py src/isotope/dev_evals/fixtures.py \
  tests/unit/dev_evals/test_cases.py tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py \
  tests/evals/test_supervisor_capacity_live_eval.py docs/current/agent-task-queue.md
git commit -m "test(rag): add research recall live llm eval"
git push
```

### Execution Note

The first real `research_recall_fixture` smoke selected and called
`research.recall` correctly, but the final answer mentioned `controlled_expand`,
which belongs to memory expansion rather than the `research.recall` input
contract. The implemented slice therefore also tightens `research.recall`
capability metadata to point detail reads at artifact inspect/expand, and the
opt-in live eval asserts that `controlled_expand` does not reappear in the
report.
