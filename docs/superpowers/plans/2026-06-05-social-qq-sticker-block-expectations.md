# QQ Sticker Block Expectations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add replay expectation checks for sticker block reasons.

**Architecture:** Reuse `EXPECTATION_NAMES`, `_expectation_actual`, and
`_expectation_ok` in `replay.py`. Do not create a second replay validator.

**Tech Stack:** Python 3.13, pytest, existing social/QQ tests.

---

### Task 1: Sticker Block Reason Expectations

**Files:**

- Modify: `src/isotope/features/social/replay.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`

- [x] **Step 1: Write failing tests**

Add tests for template defaults, passing require/forbid block reason
expectations, failing require/forbid block reason expectations, and docs.

- [x] **Step 2: Verify red**

Run focused tests and confirm failures are unsupported expectation fields.

- [x] **Step 3: Implement replay expectations**

Add `require_sticker_block_reasons` and `forbid_sticker_block_reasons` to default
expectations, expectation order, actual-value mapping, and pass/fail logic.

- [x] **Step 4: Update docs**

Document both fields in the QQ chatbot runbook.

- [x] **Step 5: Verify**

Run focused tests, relevant social/QQ tests, `git diff --check`, then commit and
merge.
