# Screen Control Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `screen.control` as a product capability and route real screen input through the existing desktop approval UI.

**Architecture:** Reuse the existing `screen_control` runtime tool, policy gate, in-process approval events, desktop snapshot approval projection, and `resolve_approval` API. Add only a capability-level wrapper plus user-facing summaries for screen control approvals; do not create a second approval subsystem.

**Tech Stack:** Python 3.13, pytest, Isotope capability catalog/runner, in-process runtime, Svelte 5, Vitest.

---

### Task 1: Backend Capability Contract

**Files:**
- Modify: `src/isotope/capabilities/screen.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/runner.py`
- Test: `tests/unit/capabilities/test_screen.py`
- Test: `tests/integration/capability/test_capability_runner_cli.py`

- [x] **Step 1: Write failing tests**
  Add tests that `screen.control` appears in the catalog, validates `target_selector`, `execution_mode`, and `actions`, runs `dry_run` to produce a `screen_control_plan`, and returns pending approval for `execute`.

- [x] **Step 2: Verify red**
  Run `PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/capabilities/test_screen.py tests/integration/capability/test_capability_runner_cli.py -q`.
  Expected: new `screen.control` assertions fail because the capability is not registered or executable.

- [x] **Step 3: Implement minimal backend**
  Add `SCREEN_CONTROL_CAPABILITY`, input validation, `run_screen_control`, catalog registration, and runner dispatch. Preserve existing `screen_control` policy behavior: `dry_run` does not require approval; `execute` requests approval and does not call the backend until resolved.

- [x] **Step 4: Verify green**
  Re-run the command from Step 2. Expected: pass.

### Task 2: Conversation Loop and Result Projection

**Files:**
- Modify: `src/isotope/features/supervisor/commands/capacity/capacity_result.py`
- Modify: `src/isotope/features/supervisor/conversation_observations.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_supervisor_capacity_path.py`

- [x] **Step 1: Write failing tests**
  Add tests proving `screen.control` can be selected by the generic capability loop and that control plans/results project as `agent_loop_screen_control_status`.

- [x] **Step 2: Verify red**
  Run the targeted supervisor tests. Expected: failure until `screen.control` returns the shared `screen_report` shape.

- [x] **Step 3: Implement minimal projection**
  Reuse the existing `screen_report` summary fields; only add small branches if code currently keys strictly on `screen.observe` or `screen.report`.

- [x] **Step 4: Verify green**
  Re-run the targeted supervisor tests. Expected: pass.

### Task 3: Desktop Approval Presentation

**Files:**
- Modify: `apps/desktop/src/lib/components/main/ConversationWorkspace.svelte`
- Modify: `apps/desktop/src/lib/view/capacityCallView.ts`
- Test: `apps/desktop/src/lib/components/main/ConversationWorkspace.test.ts`
- Test: `apps/desktop/src/lib/view/capacityCallView.test.ts`

- [x] **Step 1: Write failing tests**
  Add tests that pending `screen_control` approval cards show a screen-control-specific summary, keep approve/deny buttons, and render low-sensitive action labels without raw private payload dumps.

- [x] **Step 2: Verify red**
  Run `npm test -- src/lib/components/main/ConversationWorkspace.test.ts src/lib/view/capacityCallView.test.ts`.
  Expected: screen-control summary expectations fail.

- [x] **Step 3: Implement minimal UI**
  Enhance existing approval summary helpers and capability labels. Keep the current approval buttons and `onResolveApproval(...)` path unchanged.

- [x] **Step 4: Verify green**
  Re-run the Vitest command. Expected: pass.

### Task 4: Docs and Gate

**Files:**
- Modify: `docs/current/terminology.md`
- Modify: `docs/current/supervisor-command-reference.md`

- [x] **Step 1: Update docs**
  Document `screen.control` as a product capability that reuses `screen_control` and existing approval UI.

- [x] **Step 2: Run verification**
  Run the targeted Python and desktop tests, then `scripts/dev-eval changed_surface --base origin/main --json`. If it requires a smoke command, run the recommended command and inspect reviewer prompts before final reporting.

### Implementation Notes

- `screen.control` now returns the existing shared `screen_report` shape, so the generic conversation loop projection worked without changing `capacity_result.py` or `conversation_observations.py`.
- `execute` mode only creates a pending runtime approval; the backend is not called until the existing approval resolution path approves the action.
- Desktop approval cards use a low-sensitive `requestedActionSummary` for screen control: tool, target kind, selector keys, action count/types, and execution mode.
