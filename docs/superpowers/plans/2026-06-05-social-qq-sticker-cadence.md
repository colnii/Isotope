# QQ Sticker Cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Make role-card sticker frequency and recent sticker sends affect QQ
sticker candidate generation.

**Architecture:** Reuse `StickerLibrary.select()` as the single sticker
candidate gate. Pass existing `SocialDecisionRequest.recent_send_feedback` from
`SocialDecisionLoop` into `StickerSelectionRequest`.

**Tech Stack:** Python 3.13, pytest, existing social/QQ test suite.

---

### Task 1: Sticker Cadence Rules

**Files:**

- Modify: `src/isotope/features/social/stickers.py`
- Modify: `src/isotope/features/social/loop.py`
- Modify: `tests/unit/features/social/test_stickers.py`
- Modify: `tests/unit/features/social/test_social_decision_loop.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`

- [x] **Step 1: Write failing tests**

Add tests for:

- `use_frequency=0.0` blocks sticker selection.
- recent successful sticker feedback prevents the decision loop from repeating
  the same sticker and falls back to text.
- docs mention sticker frequency and repeated-sticker behavior.

- [x] **Step 2: Verify red**

Run focused tests and confirm failures are caused by missing cadence behavior.

- [x] **Step 3: Implement request shape and filtering**

Add recent send feedback to `StickerSelectionRequest`, validate it, and filter
candidate entries using recent successful sticker IDs.

- [x] **Step 4: Wire decision loop**

Pass `SocialDecisionRequest.recent_send_feedback` into sticker selection. Keep
normal text replies as fallback when no sticker candidate survives filtering.

- [x] **Step 5: Update docs**

Explain in product language how `use_frequency` and recent sticker sends affect
candidate generation.

- [x] **Step 6: Verify**

Run focused tests, relevant social/QQ tests, `git diff --check`, then commit and
merge.
