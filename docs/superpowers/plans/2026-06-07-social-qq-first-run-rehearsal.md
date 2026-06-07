# QQ First-Run Rehearsal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add a generated no-OneBot first-run rehearsal script for QQ beta
packs.

**Architecture:** Extend beta pack script generation with a local rehearsal
script that composes existing social CLI commands.

**Tech Stack:** Python 3.13, pytest, existing social CLI tests.

---

### Task 1: First-Run Rehearsal Script

**Files:**

- Modify: `src/isotope/features/social/beta_pack.py`
- Add: `tests/unit/features/social/test_social_qq_first_run_rehearsal.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing tests**

Add tests requiring `first-run-rehearsal.sh` generation and a full local ready
chain without OneBot.

- [x] **Step 2: Verify red**

Run focused tests and confirm failures are the missing script and script list.

- [x] **Step 3: Implement script generation**

Add `first-run-rehearsal.sh`, compose existing profile/replay/scenario commands,
and keep network-facing commands out of the script.

- [x] **Step 4: Update docs**

Document the script in generated README and current QQ operations docs.

- [x] **Step 5: Verify and prepare integration**

Run focused tests, relevant social/QQ tests, and `git diff --check`, then
commit the branch for fast-forward merge, push, and worktree cleanup.
