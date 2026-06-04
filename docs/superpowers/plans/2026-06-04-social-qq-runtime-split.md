# Social QQ Runtime Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split QQ runtime execution and persisted state/config parsing out of
`src/isotope/features/social/qq_handlers.py` while keeping the `isotope-social qq`
CLI JSON contract unchanged.

**Architecture:** Keep `qq_handlers.py` as the command map plus beta/profile/
operations handlers. Move `run`, `live-run`, replay execution, and runtime
construction into `qq_runtime_commands.py`. Move state file loading/saving and
config object construction into `qq_state_config.py`.

**Tech Stack:** Python 3.13, argparse, pytest, existing QQ/social tests.

---

### Task 1: Structure Regression

**Files:**
- Modify: `tests/unit/features/social/test_social_runner_structure.py`

- [x] **Step 1: Write failing structure test**

Update the structure test to assert:

- `qq_handlers.py` has fewer than 350 lines;
- `qq_runtime_commands.py` exists and owns `OneBotWebSocketClient`;
- `qq_runtime_commands.py` defines `handle_live_run`;
- `qq_state_config.py` exists and defines `StoredQQState` and `load_config`;
- `qq_handlers.py` no longer imports `OneBotWebSocketClient`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py -q
```

Expected: FAIL because `qq_runtime_commands.py` and `qq_state_config.py` do not
exist yet.

### Task 2: Runtime and State Split

**Files:**
- Create: `src/isotope/features/social/qq_runtime_commands.py`
- Create: `src/isotope/features/social/qq_state_config.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/integration/qq/test_fake_onebot_flow.py`

- [x] **Step 1: Move state/config helpers**

Move state file parsing, config parsing, role/lorebook/sticker construction, and
operations-controller construction into `qq_state_config.py`.

- [x] **Step 2: Move runtime commands**

Move `run`, `live-run`, replay execution, and runtime construction into
`qq_runtime_commands.py`.

- [x] **Step 3: Keep handler dispatch stable**

Make `qq_handlers()` map runtime commands to the new functions while keeping
existing command keys and returned JSON payloads unchanged.

- [x] **Step 4: Update monkeypatch targets**

Update live-run tests to monkeypatch `qq_runtime_commands.OneBotWebSocketClient`,
because the WebSocket dependency now belongs to the runtime module.

### Task 3: Verification and Debt Update

**Files:**
- Modify: `docs/current/refactoring-debt.md`

- [x] **Step 1: Focused verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: PASS.

- [x] **Step 2: Record remaining debt**

Record that runtime and state/config are split, while remaining QQ handler
groups can later be split into beta, profile, and operations modules.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Existing `isotope-social qq run`, `live-run`, `replay`, pause/resume, inspect,
  health, and export-log behavior stays unchanged.
- `qq_handlers.py` is below 350 lines and no longer owns WebSocket transport or
  runtime construction.
- Runtime execution is patchable through `qq_runtime_commands.OneBotWebSocketClient`.
- State/config helpers are reusable by future QQ command modules.
