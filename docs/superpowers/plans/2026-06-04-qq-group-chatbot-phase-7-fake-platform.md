# QQ Group Chatbot Phase 7 Fake Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the complete social core without QQ by running incoming group messages through context building, decision, fake send, and send feedback.

**Architecture:** Add a deterministic in-memory fake platform adapter. It emits `SocialMessage`, records selected `SocialReplyAction`, returns `SocialSendFeedback`, and exposes a small harness that wires `SocialContextBuilder`, `SocialDecisionLoop`, optional `Lorebook`, and optional `StickerLibrary`.

**Tech Stack:** Python 3.13, pytest, dataclasses.

---

## Reuse Audit

- Reuse `SocialMessage` as fake inbound events; do not invent another inbound shape.
- Reuse `SocialReplyAction` as fake outbound sends.
- Reuse `SocialSendFeedback` as fake platform result.
- Reuse `SocialContextBuilder`, `SocialDecisionLoop`, `Lorebook`, and `StickerLibrary` to prove the core pieces compose.
- Do not import NapCat, OneBot, NoneBot, or QQ dependencies in this phase.

## File Structure

- Create `src/isotope/features/social/fake_platform.py`: in-memory fake platform and harness.
- Modify `src/isotope/features/social/__init__.py`: export fake platform names.
- Create `tests/integration/social/test_social_fake_platform_flow.py`: full fake flow tests.

## Task 1: Fake Platform Flow

**Files:**
- Create: `src/isotope/features/social/fake_platform.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/integration/social/test_social_fake_platform_flow.py`

- [ ] **Step 1: Write failing integration tests**

Create tests proving:

- a multi-part group message with a bot mention creates and sends a text reply;
- a role-consistent sticker reply is sent when role and group allow it;
- dry-run mode returns proposed send candidates and records no outgoing action.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/social/test_social_fake_platform_flow.py -q
```

Expected: FAIL because fake platform objects do not exist.

- [ ] **Step 3: Implement fake platform and harness**

Create:

- `SocialFakePlatform`
- `SocialFakePlatformTurn`
- `SocialFakePlatformHarness`

Behavior:

- queue incoming `SocialMessage` objects;
- `receive_next()` returns and removes the next message;
- `send(action)` records the action and returns `SocialSendFeedback`;
- harness builds context with `SocialContextBuilder`;
- harness calls `SocialDecisionLoop`;
- harness sends selected send actions unless dry-run is enabled;
- fake sent message IDs are deterministic: `fake_sent_1`, `fake_sent_2`, ...

- [ ] **Step 4: Run fake platform integration tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/social/test_social_fake_platform_flow.py -q
```

Expected: PASS.

## Task 2: Regression And Product Acceptance

- [ ] **Step 1: Run full social unit regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social -q
```

Expected: all social unit tests pass.

- [ ] **Step 2: Run fake integration regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/social/test_social_fake_platform_flow.py -q
```

Expected: all fake platform integration tests pass.

- [ ] **Step 3: Run shared supervisor regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run diff hygiene**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Product checklist**

Confirm from tests and code:

- a reviewer can read one integration test and see the intended QQ group behavior;
- sticker reply works through the same fake send path as text reply;
- dry-run leaves fake platform outgoing actions empty.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-7-fake-platform.md src/isotope/features/social tests/integration/social/test_social_fake_platform_flow.py
git commit -m "feat(social): add fake platform harness"
```
