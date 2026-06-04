# State Memory Artifact Projections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new Supervisor-facing views consume `SupervisorStateSnapshot`, `MemoryRecord` records, and artifact summaries instead of reassembling private state.

**Architecture:** Extend the existing projected snapshot with memory and artifact sections. Keep file access inside established store/retrieval boundaries, and make view helpers accept already projected inputs where they currently require separately assembled lists.

**Tech Stack:** Python 3.13, pytest, existing Isotope dataclasses and projection helpers.

---

### Task 1: Extend Supervisor State Snapshot

**Files:**
- Modify: `src/isotope/platform/state/supervisor_snapshot.py`
- Modify: `src/isotope/features/supervisor/state/projection.py`
- Test: `tests/integration/supervisor/test_supervisor_state_projection.py`

- [ ] **Step 1: Write the failing memory/artifact projection test**

Add a test that creates one `MemoryRecord` and one artifact with secret full content, builds `build_supervisor_state_snapshot(...)`, and asserts the snapshot includes structured memory/artifact summaries.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_state_projection.py::test_supervisor_state_snapshot_includes_memory_and_artifact_summaries_without_content -q`

Expected: FAIL because `memory` and `artifacts` are not present in the snapshot.

- [ ] **Step 3: Implement minimal snapshot fields**

Add `memory` and `artifacts` dict fields to `SupervisorStateSnapshot`, include them in `empty(...)` and `to_dict()`, then build them in `build_supervisor_state_snapshot(...)` using `FileMemoryStore`, `ArtifactStore`, and `RetrievalService.get_artifact_summary(...)`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_state_projection.py::test_supervisor_state_snapshot_includes_memory_and_artifact_summaries_without_content -q`

Expected: PASS.

### Task 2: Make Multi-Worker View Record-Oriented

**Files:**
- Modify: `src/isotope/platform/state/multi_worker.py`
- Test: `tests/unit/memory/test_memory_views.py`

- [ ] **Step 1: Write the failing record-input test**

Add a unit test that calls `build_multi_worker_status_from_records(records=[...])` directly with `MemoryRecord` objects and asserts worker/capacity counts without raw content leakage.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/memory/test_memory_views.py::test_multi_worker_status_can_be_built_from_memory_records -q`

Expected: FAIL because `build_multi_worker_status_from_records` does not exist.

- [ ] **Step 3: Extract the record-input helper**

Move the record filtering and worker payload construction from `build_multi_worker_status_payload(...)` into `build_multi_worker_status_from_records(...)`. Keep the root-reading wrapper as the store boundary.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/memory/test_memory_views.py::test_multi_worker_status_can_be_built_from_memory_records -q`

Expected: PASS.

### Task 3: Let Current-Batch Consume Snapshot Goals

**Files:**
- Modify: `src/isotope/features/supervisor/dashboard/presentation.py`
- Test: `tests/unit/features/supervisor/test_supervisor_dashboard_current_payload.py`

- [ ] **Step 1: Write the failing snapshot-input test**

Add a test that calls `dashboard_current_payload(display_sessions=[], state_snapshot={"active_goals": [...]})` without passing `active_goals` separately and asserts the current view contains the projected goal.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_dashboard_current_payload.py::test_dashboard_current_payload_can_read_active_goals_from_state_snapshot -q`

Expected: FAIL because `dashboard_current_payload` does not accept `state_snapshot`.

- [ ] **Step 3: Add optional snapshot input**

Add `state_snapshot: dict[str, Any] | None = None` to `dashboard_current_payload(...)`, `current_batch_payload(...)`, and `current_batch_payload_from_display_sessions(...)`. When `active_goals` is not supplied, derive it from `state_snapshot["active_goals"]`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_dashboard_current_payload.py::test_dashboard_current_payload_can_read_active_goals_from_state_snapshot -q`

Expected: PASS.

### Task 4: Verify Existing View Contracts

**Files:**
- Modify only if previous tasks reveal an integration mismatch.

- [ ] **Step 1: Run targeted regression tests**

Run: `.venv/bin/python -m pytest tests/integration/supervisor/test_supervisor_state_projection.py tests/integration/supervisor/test_supervisor_desktop_snapshot.py tests/unit/memory/test_memory_views.py tests/integration/supervisor/test_supervisor_multi_worker_manager.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run diff hygiene check**

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 3: Inspect changed files**

Run: `git diff --stat && git diff -- src/isotope/platform/state/supervisor_snapshot.py src/isotope/features/supervisor/state/projection.py src/isotope/platform/state/multi_worker.py src/isotope/features/supervisor/dashboard/presentation.py`

Expected: changes are limited to the projection/view boundary and tests/docs.

- [ ] **Step 4: Commit implementation**

Commit message: `feat(supervisor): unify state memory artifact projections`
