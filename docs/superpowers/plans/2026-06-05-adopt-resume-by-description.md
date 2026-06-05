# Adopt Resume By Description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Supervisor operation that accepts a natural-language description, finds the matching local Codex session, adopts it if needed, and starts a managed resume worker.

**Architecture:** Introduce a small `session_matcher` module under Supervisor registry for deterministic candidate ranking. Wire a new `adopt_resume_by_description` operation through `supervisor.codex_operation`, reusing existing `adopt_codex_session` and `resume_managed_codex` helpers.

**Tech Stack:** Python 3.13, pytest, existing Isotope Supervisor registry, scan, and capability runner.

---

### Task 1: Session Matcher

**Files:**
- Create: `src/isotope/features/supervisor/registry/session_matcher.py`
- Test: `tests/integration/codex/scan/test_adopt_resume_by_description.py`

- [x] **Step 1: Write failing tests for clear, ambiguous, and no match**

Create local Codex rollout fixtures and assert `match_codex_sessions_by_description(...)`
returns `clear`, `ambiguous`, and `no_match` for the three cases.

- [x] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/codex/scan/test_adopt_resume_by_description.py::test_session_matcher_selects_clear_description_match -q
```

Expected: import failure because the matcher module does not exist.

- [x] **Step 3: Implement the matcher**

Read Codex sessions under `codex_home/sessions`, create weighted text from cwd,
title, recent user messages, and recent assistant messages, compute normalized
token overlap, and classify the top candidates.

- [x] **Step 4: Verify GREEN**

Run the matcher tests and expect pass.

### Task 2: Adopt And Resume Operation

**Files:**
- Modify: `src/isotope/capabilities/supervisor.py`
- Test: `tests/integration/codex/scan/test_adopt_resume_by_description.py`

- [x] **Step 1: Write failing operation tests**

Assert `supervisor.codex_operation` with operation
`adopt_resume_by_description` returns `resumed` for a clear match and
`ambiguous` for close matches.

- [x] **Step 2: Verify RED**

Run the operation tests and expect unknown operation failure.

- [x] **Step 3: Implement operation**

Add the new enum, dispatch operation, reuse existing managed record when a
matching `resume_session_id` exists, otherwise adopt the session, then call
`resume_managed_codex`.

- [x] **Step 4: Verify GREEN**

Run the operation tests and expect pass.

### Task 3: Desktop Chat Capability Metadata

**Files:**
- Modify: `src/isotope/capabilities/catalog.py`
- Test: `tests/integration/codex/scan/test_adopt_resume_by_description.py`

- [x] **Step 1: Write failing manifest test**

Assert `supervisor.codex_operation` input contract includes
`description` and enum `adopt_resume_by_description`.

- [x] **Step 2: Verify RED**

Run the manifest test and expect failure.

- [x] **Step 3: Update metadata**

Expose `description` as the natural-language matching input and include the new
operation enum.

- [x] **Step 4: Verify GREEN**

Run the manifest test and expect pass.

### Task 4: Verification And Commit

**Files:**
- All modified files above
- Modify: `docs/current/supervisor-command-reference.md`

- [x] **Step 1: Update docs**

Document the description-driven path as an AI/capability route, separate from
manual `adopt --session-id`.

- [x] **Step 2: Run focused regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/codex/scan/test_adopt_resume_by_description.py tests/integration/codex/scan/test_adopt_codex_session.py tests/integration/codex/llm/test_llm_action.py -q
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-05-adopt-resume-by-description-design.md docs/superpowers/plans/2026-06-05-adopt-resume-by-description.md docs/current/refactoring-debt.md docs/current/supervisor-command-reference.md src/isotope/features/supervisor/registry/session_matcher.py src/isotope/capabilities/supervisor.py src/isotope/capabilities/catalog.py tests/integration/codex/scan/test_adopt_resume_by_description.py tests/unit/capabilities/test_supervisor_codex_operation.py
git commit -m "feat(supervisor): resume codex sessions by description"
```
