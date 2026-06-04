# QQ Group Chatbot Phase 10 Beta Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document and guard the controlled real QQ group beta path with exact setup, config, run, pause, inspect, smoke, shutdown, tuning, and failure-regression rules.

**Architecture:** Keep beta guidance in `docs/current` because it is user-facing operational knowledge. Add a docs unit test that fails if critical runbook sections or real-smoke guard variables disappear.

**Tech Stack:** Markdown, pytest.

---

## Reuse Audit

- Reuse Phase 8 `ISOTOPE_QQ_REAL_SMOKE` guard naming.
- Reuse Phase 9 operations concepts: pause, resume, inspect, audit log, health.
- Do not invent CLI commands that do not exist yet; mark future commands as intended CLI surfaces and give current Python-level smoke/import verification where executable today.
- Do not claim a real QQ beta has already run; document the controlled beta process and the rule for turning observed failures into regression tests.

## File Structure

- Create `docs/current/qq-group-chatbot.md`: setup, configuration, run path, real smoke, tuning.
- Create `docs/current/qq-group-chatbot-operations.md`: operator controls, inspect, shutdown, failure log, multi-day checklist.
- Create `tests/unit/docs/test_qq_group_chatbot_docs.py`: runbook coverage checks.

## Task 1: Runbook Coverage Test

**Files:**
- Create: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [ ] **Step 1: Write failing docs test**

Create a test that asserts both docs exist and include:

- setup
- config
- run
- pause
- inspect
- shutdown
- `ISOTOPE_QQ_REAL_SMOKE`
- role-card tuning
- sticker pack setup
- failure log
- multi-day checklist

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: FAIL because the docs do not exist.

## Task 2: Write Beta Docs

**Files:**
- Create: `docs/current/qq-group-chatbot.md`
- Create: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Write docs**

The docs must include:

- exact local verification commands available today;
- intended QQ runtime config shape;
- guarded real smoke command shape;
- role-card tuning loop;
- sticker pack setup rules;
- pause/resume/inspect/shutdown operations;
- failure log rules requiring a regression test for every real beta bug.

- [ ] **Step 2: Run docs test**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: PASS.

## Task 3: Regression And Product Acceptance

- [ ] **Step 1: Run docs test**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: PASS.

- [ ] **Step 2: Run QQ/social regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: all tests pass, with real QQ smoke skipped unless enabled.

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

Confirm from docs and tests:

- controlled real group setup is understandable;
- real smoke cannot run accidentally;
- operators know how to pause, inspect, and shut down;
- real beta failures must produce regression tests.

- [ ] **Step 6: Commit**

```bash
git add docs/current/qq-group-chatbot.md docs/current/qq-group-chatbot-operations.md tests/unit/docs/test_qq_group_chatbot_docs.py docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-10-beta-hardening.md
git commit -m "docs(qq): add beta hardening runbook"
```
