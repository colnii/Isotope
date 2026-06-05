# QQ Sticker Explanation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add operator-visible reasons for missing QQ sticker candidates.

**Architecture:** Reuse `StickerLibrary` as the sticker decision source and
`SocialActionCandidate.metadata` as the existing report path.

**Tech Stack:** Python 3.13, pytest, existing social/QQ test suite.

---

### Task 1: Sticker Candidate Explanations

**Files:**

- Modify: `src/isotope/features/social/stickers.py`
- Modify: `src/isotope/features/social/loop.py`
- Modify: `src/isotope/features/social/replay.py`
- Modify: `src/isotope/features/social/__init__.py`
- Modify: `tests/unit/features/social/test_stickers.py`
- Modify: `tests/unit/features/social/test_social_decision_loop.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`

- [x] **Step 1: Write failing tests**

Add tests for:

- sticker selection outcome explains `use_frequency_zero`;
- decision loop text fallback metadata explains recent sticker feedback;
- replay summary aggregates sticker block reason counts;
- docs mention the new report fields and reason codes.

- [x] **Step 2: Verify red**

Run focused tests and confirm failures are due to missing explanation behavior.

- [x] **Step 3: Implement selection outcome**

Add a diagnostic outcome to `StickerLibrary` while preserving the existing
`select()` return contract.

- [x] **Step 4: Wire loop metadata**

Use the diagnostic outcome in `SocialDecisionLoop` and attach explanation
metadata to text fallback candidates.

- [x] **Step 5: Aggregate replay summary**

Collect blocked reasons from proposed candidate metadata into replay summary.

- [x] **Step 6: Update docs**

Document the report fields and reason codes in the QQ chatbot runbook.

- [x] **Step 7: Verify**

Run focused tests, relevant social/QQ tests, `git diff --check`, then commit and
merge.
