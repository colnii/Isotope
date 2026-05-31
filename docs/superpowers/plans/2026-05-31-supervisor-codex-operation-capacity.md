# Supervisor Codex Operation Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Supervisor Codex operations through a unified `supervisor.codex_operation` capacity and prove one legacy Supervisor action can execute through an agent-loop `call_capability` tick.

**Architecture:** Add a small capability adapter that exposes low-sensitive Codex operations as one capability with an `operation` enum. Keep legacy direct actions as wrappers while introducing a shared agent-loop execution helper that calls `supervisor.codex_operation`.

**Tech Stack:** Python 3.13, pytest, existing `CapabilityRunner`, existing in-process agent loop, existing Supervisor command helpers.

---

### Task 1: Unified Capability Metadata

**Files:**
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/supervisor.py`
- Modify: `src/isotope/capabilities/runner.py`
- Test: `tests/unit/capabilities/test_supervisor_codex_operation.py`

- [ ] **Step 1: Write failing tests**

Add tests proving `supervisor.codex_operation` is listed, can be planned with missing inputs, and can run `worker_review` through the unified entry.

- [ ] **Step 2: Run tests and verify red**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_supervisor_codex_operation.py -q`

Expected: fail because `supervisor.codex_operation` is not registered.

- [ ] **Step 3: Implement capability metadata and read-only dispatch**

Add `SUPERVISOR_CODEX_OPERATION_CAPABILITY = "supervisor.codex_operation"` and `run_supervisor_codex_operation(...)`.

- [ ] **Step 4: Run tests and verify green**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_supervisor_codex_operation.py -q`

Expected: pass.

### Task 2: Agent Loop Routing Helper

**Files:**
- Modify: `src/isotope/features/supervisor/commands/handlers/capacity.py`
- Test: `tests/unit/supervisor/test_codex_operation_agent_loop.py`

- [ ] **Step 1: Write failing test**

Add a test proving a `request_context` operation is converted into a one-tick agent loop call to `supervisor.codex_operation`.

- [ ] **Step 2: Run test and verify red**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/supervisor/test_codex_operation_agent_loop.py -q`

Expected: fail because the helper does not exist.

- [ ] **Step 3: Implement helper**

Add `execute_codex_operation_via_agent_loop(...)`, reusing `_execute_agent_loop_capacity_step(...)`.

- [ ] **Step 4: Run tests and verify green**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/supervisor/test_codex_operation_agent_loop.py -q`

Expected: pass.

### Task 3: Legacy Action Compatibility Routing

**Files:**
- Modify: `src/isotope/features/supervisor/commands/llm/action.py`
- Test: existing or new Supervisor LLM action tests

- [ ] **Step 1: Write failing test**

Prove `request_context` action execution returns a `call_capacity` result for `supervisor.codex_operation`.

- [ ] **Step 2: Run test and verify red**

Run the focused Supervisor LLM action test.

- [ ] **Step 3: Route request_context through the helper**

Keep direct `_execute_context_action` available as fallback helper code, but make LLM action execution call the unified capacity route.

- [ ] **Step 4: Run focused tests and integration smoke**

Run focused Python tests and the existing capacity integration tests.
