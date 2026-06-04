# Social Runner Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split QQ command registration and dispatch out of `src/isotope/features/social/runner.py` without changing the `isotope-social qq` CLI contract.

**Architecture:** Keep `runner.py` as the generic CLI entry point and JSON/plain output owner. Move QQ parser registration and command-to-handler dispatch into `qq_runner.py`; keep existing handler implementations in `runner.py` for this first low-risk split.

**Tech Stack:** Python 3.13, argparse, pytest, existing social QQ runner tests.

---

### Task 1: Structural Regression Test

**Files:**
- Create: `tests/unit/features/social/test_social_runner_structure.py`

- [x] **Step 1: Write failing structure test**

Add a test that reads `src/isotope/features/social/runner.py` and
`src/isotope/features/social/qq_runner.py`, then asserts:

- `runner.py` has fewer than 700 lines;
- `qq_runner.py` contains `register_qq_commands`;
- `qq_runner.py` contains `handle_qq_command`;
- `runner.py` no longer contains `qq_subparsers.add_parser`;
- `runner.py` no longer contains `def _handle_qq(`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py -q
```

Expected: FAIL because `qq_runner.py` does not exist yet.

### Task 2: Split QQ Parser and Dispatch

**Files:**
- Create: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/runner.py`

- [x] **Step 1: Create `qq_runner.py`**

Move QQ parser registration into `register_qq_commands(subparsers)`. Move command dispatch into `handle_qq_command(args, handlers)`, with grouped keys for `dry-run`/`run` and `pause`/`resume`.

- [x] **Step 2: Shrink `runner.py`**

Replace inline QQ parser registration with `register_qq_commands(subparsers)`.
Replace `_handle_qq(args)` with `handle_qq_command(args, _qq_handlers())`.
Add `_qq_handlers()` as the explicit handler map.

- [x] **Step 3: Verify focused tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

### Task 3: Debt Update and Final Verification

**Files:**
- Modify: `docs/current/refactoring-debt.md`

- [x] **Step 1: Update refactoring debt**

Record that QQ command registration and dispatch have moved to `qq_runner.py`, while handler implementations remain in `runner.py` as the next split.

- [x] **Step 2: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner_structure.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- `isotope-social qq` commands keep their existing behavior.
- `runner.py` is below 700 lines.
- QQ parser registration and command dispatch live in `qq_runner.py`.
- Remaining debt clearly points to moving handler implementations next.
