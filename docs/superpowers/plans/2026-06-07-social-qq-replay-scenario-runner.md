# QQ Replay Scenario Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add a batch command that runs every generated QQ replay scenario and
writes one aggregate report.

**Architecture:** Extract reusable single-scenario replay execution, then call
it from a new `qq replay-scenarios` command.

**Tech Stack:** Python 3.13, pytest, existing social CLI tests.

---

### Task 1: Batch Scenario Replay

**Files:**

- Modify: `src/isotope/features/social/qq_runtime_commands.py`
- Modify: `src/isotope/features/social/qq_replay_commands.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `tests/unit/features/social/test_social_qq_replay_scenarios.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`

- [x] **Step 1: Write failing tests**

Add CLI tests for a passing scenario pack and a failing scenario pack.

- [x] **Step 2: Verify red**

Run the focused test and confirm failure is the missing `replay-scenarios`
command.

- [x] **Step 3: Reuse replay execution**

Extract `run_qq_replay` from the existing `qq replay` handler without changing
single-scenario behavior.

- [x] **Step 4: Implement batch command**

Read `index.json`, resolve each replay file, write per-scenario reports, write
one aggregate report, and return exit code 2 when any scenario fails.

- [x] **Step 5: Update docs**

Document the command, aggregate report, per-scenario report directory, and
failure behavior.

- [x] **Step 6: Verify and prepare integration**

Run focused tests, relevant social/QQ tests, and `git diff --check`, then
commit the branch for fast-forward merge, push, and worktree cleanup.
