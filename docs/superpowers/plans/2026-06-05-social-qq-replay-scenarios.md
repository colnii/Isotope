# QQ Replay Scenarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add a CLI-generated replay scenario pack for QQ sticker tuning.

**Architecture:** Reuse `replay.py` replay payload construction and existing QQ
command registration/handler dispatch.

**Tech Stack:** Python 3.13, pytest, existing social CLI tests.

---

### Task 1: Replay Scenario Pack

**Files:**

- Modify: `src/isotope/features/social/replay.py`
- Modify: `src/isotope/features/social/qq_replay_commands.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`

- [x] **Step 1: Write failing tests**

Add tests for the new CLI command, generated files, expectations, index, and
docs.

- [x] **Step 2: Verify red**

Run focused tests and confirm failures are missing command/docs.

- [x] **Step 3: Implement scenario generation**

Add scenario config/result data classes and payload generation in `replay.py`.

- [x] **Step 4: Wire CLI**

Register `init-replay-scenarios`, add handler dispatch, and return JSON summary.

- [x] **Step 5: Update docs**

Document the command and generated files.

- [x] **Step 6: Verify**

Run focused tests, relevant social/QQ tests, `git diff --check`, then commit and
merge.
