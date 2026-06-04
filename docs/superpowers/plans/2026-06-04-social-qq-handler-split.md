# Social QQ Handler Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move QQ command handlers and runtime helpers out of `src/isotope/features/social/runner.py` while keeping the `isotope-social qq` CLI contract unchanged.

**Architecture:** Keep `runner.py` as a thin process entry point. Keep QQ parser registration in `qq_runner.py`. Move command handlers, state/config helpers, and runtime construction into `qq_handlers.py`.

**Tech Stack:** Python 3.13, argparse, pytest, existing QQ/social runner tests.

---

### Task 1: Thin Runner Structure Test

**Files:**
- Modify: `tests/unit/features/social/test_social_runner_structure.py`

- [x] **Step 1: Write failing structure test**

Update the structure test to assert:

- `runner.py` has fewer than 120 lines;
- `qq_handlers.py` exists and defines `qq_handlers`;
- `qq_handlers.py` owns the OneBot WebSocket dependency;
- `runner.py` does not contain `_handle_run`;
- `runner.py` does not import `OneBotWebSocketClient`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py -q
```

Expected: FAIL because `qq_handlers.py` does not exist and `runner.py` still owns handlers.

### Task 2: Move Handler Implementation

**Files:**
- Create: `src/isotope/features/social/qq_handlers.py`
- Modify: `src/isotope/features/social/runner.py`
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Move handlers and helpers**

Move `_handle_*`, state loading, config loading, runtime construction, and JSON file helpers from `runner.py` into `qq_handlers.py`.

- [x] **Step 2: Keep runner as thin entry point**

Make `runner.py` import `qq_handlers`, `handle_qq_command`, and `register_qq_commands`. Keep only parser setup, `main`, JSON/plain output, and error handling in `runner.py`.

- [x] **Step 3: Update monkeypatch targets**

Update live-run tests to monkeypatch `qq_handlers.OneBotWebSocketClient`, because the WebSocket dependency now belongs to `qq_handlers.py`.

- [x] **Step 4: Verify focused tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

### Task 3: Debt Update and Final Verification

**Files:**
- Modify: `docs/current/refactoring-debt.md`

- [x] **Step 1: Update refactoring debt**

Record that `runner.py` is now thin, while `qq_handlers.py` remains a 600+ line module that should be split before more QQ commands are added.

- [x] **Step 2: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Existing `isotope-social qq` behavior is unchanged.
- `runner.py` is below 120 lines and no longer owns QQ handler dependencies.
- `qq_handlers.py` owns command handlers and can be split further later.
- Tests preserve monkeypatchability of the live-run WebSocket client at the new boundary.
