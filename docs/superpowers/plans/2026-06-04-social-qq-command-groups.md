# Social QQ Command Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the remaining QQ command handlers out of
`src/isotope/features/social/qq_handlers.py` so that file becomes a dispatch
table only, without changing the `isotope-social qq` CLI contract.

**Architecture:** Keep parser registration in `qq_runner.py`, runtime execution
in `qq_runtime_commands.py`, and state/config helpers in `qq_state_config.py`.
Move the remaining handlers into focused modules:

- `qq_beta_commands.py`: beta pack, startup check, dry-run review, beta-day
  report, regression intake.
- `qq_profile_commands.py`: profile pack init/apply.
- `qq_replay_commands.py`: replay template init.
- `qq_operations_commands.py`: pause/resume, inspect, health, export-log.

**Tech Stack:** Python 3.13, argparse, pytest, existing QQ/social tests.

---

### Task 1: Structure Regression

**Files:**
- Modify: `tests/unit/features/social/test_social_runner_structure.py`

- [x] **Step 1: Write failing structure test**

Update the structure test to assert:

- `qq_handlers.py` has fewer than 120 lines;
- beta, profile, replay-template, and operations command modules exist;
- `qq_handlers.py` no longer defines concrete `_handle_*` command functions;
- `qq_handlers.py` no longer imports beta/profile/operations implementation
  config classes.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py -q
```

Expected: FAIL because the command group modules do not exist yet.

### Task 2: Split Command Groups

**Files:**
- Create: `src/isotope/features/social/qq_beta_commands.py`
- Create: `src/isotope/features/social/qq_profile_commands.py`
- Create: `src/isotope/features/social/qq_replay_commands.py`
- Create: `src/isotope/features/social/qq_operations_commands.py`
- Modify: `src/isotope/features/social/qq_handlers.py`

- [x] **Step 1: Move beta/report handlers**

Move beta pack, beta check, startup check, dry-run review, beta-day report, and
regression intake handlers into `qq_beta_commands.py`.

- [x] **Step 2: Move profile and replay-template handlers**

Move profile init/apply into `qq_profile_commands.py`, and replay template init
into `qq_replay_commands.py`.

- [x] **Step 3: Move operational handlers**

Move pause/resume, inspect, health, and export-log handlers into
`qq_operations_commands.py`, reusing `qq_state_config.py`.

- [x] **Step 4: Keep dispatch stable**

Make `qq_handlers()` import the new `handle_*` functions and preserve every
existing command key.

### Task 3: Verification and Debt Update

**Files:**
- Modify: `docs/current/refactoring-debt.md`

- [x] **Step 1: Focused verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

- [x] **Step 2: Record remaining debt**

Record that `qq_handlers.py` is now dispatch-only, while the social package
still has many top-level modules and may later need a `qq/` subpackage.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Existing `isotope-social qq` commands keep the same parser path and returned
  JSON payloads.
- `qq_handlers.py` is dispatch-only and below 120 lines.
- Each command group owns only its related imports and concrete handler logic.
- Runtime, state/config, command dispatch, and command implementation boundaries
  are separate enough for the next QQ chatbot feature work.
