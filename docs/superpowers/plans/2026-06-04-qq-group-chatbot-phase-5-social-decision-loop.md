# QQ Group Chatbot Phase 5 Social Decision Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide whether the group bot should speak, stay silent, send a sticker, call a capability, write memory, or request operator review based on group context and role state.

**Architecture:** Keep decision-making platform-neutral. `SocialDecisionLoop` creates explainable `SocialActionCandidate` objects from `social_context`, previous send feedback, and deterministic wake inputs; `SocialArbiter` chooses a non-conflicting set of candidates while allowing at most one send action per turn.

**Tech Stack:** Python 3.13, pytest, dataclasses.

---

## Reuse Audit

- Reuse `SocialContextBuilder` payload shape as the decision input.
- Reuse `SocialReplyAction` for outbound respond/interrupt candidates.
- Reuse `SocialSendFeedback` to suppress immediate repeated sends after the bot already spoke.
- Reuse `StickerLibrary` and `StickerSelectionRequest` when the role and request allow a sticker reply.
- Do not call real capabilities in this phase; represent capability intent as a candidate action for Phase 6.
- Do not send to QQ in this phase; fake/real platform adapters come later.

## File Structure

- Create `src/isotope/features/social/candidates.py`: candidate action model.
- Create `src/isotope/features/social/arbiter.py`: candidate selection and conflict rejection.
- Create `src/isotope/features/social/decision.py`: decision request/result objects.
- Create `src/isotope/features/social/loop.py`: deterministic decision loop.
- Modify `src/isotope/features/social/__init__.py`: export Phase 5 names.
- Create `tests/unit/features/social/test_social_decision_loop.py`: wake, dry-run, feedback, sticker tests.
- Create `tests/unit/features/social/test_social_arbiter.py`: duplicate send and state-lock conflict tests.

## Task 1: Candidate Arbiter

**Files:**
- Create: `src/isotope/features/social/candidates.py`
- Create: `src/isotope/features/social/arbiter.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_social_arbiter.py`

- [ ] **Step 1: Write failing arbiter tests**

Create tests proving:

- two send candidates from different agents cannot both be selected;
- the higher confidence send candidate wins;
- two candidates claiming the same state lock cannot both be selected;
- non-conflicting non-send candidates can be selected together.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_arbiter.py -q
```

Expected: FAIL because `SocialActionCandidate` and `SocialArbiter` do not exist.

- [ ] **Step 3: Implement candidate and arbiter models**

Create:

- `SocialActionCandidate`
- `SocialArbiter`
- `SocialArbiterResult`

Supported candidate kinds:

- `silent`
- `internal_note`
- `respond`
- `interrupt`
- `call_capability`
- `write_memory`
- `request_operator_review`

Rules:

- `respond` and `interrupt` require `reply_action`;
- confidence must be between 0 and 1;
- selected candidates sort by confidence high to low;
- at most one send candidate is selected;
- a state lock can be owned by only one selected candidate.

- [ ] **Step 4: Run arbiter tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_arbiter.py -q
```

Expected: PASS.

## Task 2: Decision Loop

**Files:**
- Create: `src/isotope/features/social/decision.py`
- Create: `src/isotope/features/social/loop.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_social_decision_loop.py`

- [ ] **Step 1: Write failing decision loop tests**

Create tests proving:

- mention wake creates a respond candidate with an explanation;
- keyword wake creates a respond candidate;
- autonomous wake can create a respond candidate when `autonomy_score <= talkativeness`;
- no-wake creates only a silent candidate;
- recent successful send feedback suppresses immediate repeated sends;
- dry-run returns proposed send candidates but selects none;
- sticker selection can produce a sticker-only respond candidate when allowed.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_decision_loop.py -q
```

Expected: FAIL because `SocialDecisionLoop` and `SocialDecisionRequest` do not exist.

- [ ] **Step 3: Implement decision loop**

Create:

- `SocialDecisionRequest`
- `SocialDecisionTurn`
- `SocialDecisionLoop`

Behavior:

- read `message`, `character_card`, and `group_id` from the social context payload;
- build wake reasons from bot mention, configured wake keywords, and deterministic autonomous score;
- return a silent candidate with reason when no wake reason exists;
- return a silent candidate with reason when recent successful send feedback exists;
- generate one respond candidate with text by default;
- generate a sticker-only respond candidate if sticker library, role policy, request permission, and selection tags allow it;
- in dry-run mode, expose proposed candidates and do not select send candidates.

- [ ] **Step 4: Run decision tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_decision_loop.py -q
```

Expected: PASS.

## Task 3: Regression And Product Acceptance

- [ ] **Step 1: Run full social regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social -q
```

Expected: all social tests pass.

- [ ] **Step 2: Run shared supervisor regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run diff hygiene**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 4: Product checklist**

Confirm from tests and code:

- the bot can explain why it spoke or stayed silent;
- two agents cannot both send in one group turn;
- recent send feedback changes the next decision;
- dry-run exposes what would happen without treating it as sent.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-5-social-decision-loop.md src/isotope/features/social tests/unit/features/social/test_social_decision_loop.py tests/unit/features/social/test_social_arbiter.py
git commit -m "feat(social): add social decision loop"
```
