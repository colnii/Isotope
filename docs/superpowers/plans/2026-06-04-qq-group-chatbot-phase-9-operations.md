# QQ Group Chatbot Phase 9 Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the QQ group bot operable through understandable group policies, operator permissions, pause/resume controls, dry-run review, audit logs, health checks, and inspect surfaces.

**Architecture:** Add an in-memory operations controller that wraps already-built social objects. It answers whether a group can be processed, enforces operator-only controls, records decision/send/capability reports, and returns plain dictionaries for UI/CLI surfaces.

**Tech Stack:** Python 3.13, pytest, dataclasses.

---

## Reuse Audit

- Reuse `SocialDecisionTurn` for decision logs and dry-run review.
- Reuse `SocialSendFeedback` for send logs.
- Reuse `SocialInformationReport` for capability logs.
- Reuse `CharacterCard`, `Lorebook`, and `StickerLibrary` for inspect output.
- Do not add persistent storage yet; Phase 10 can choose file/DB persistence after real beta needs are known.

## File Structure

- Create `src/isotope/features/social/config.py`: group policy and operations config.
- Create `src/isotope/features/social/audit_log.py`: in-memory audit entries and append/query helpers.
- Create `src/isotope/features/social/operations.py`: operator controls, policy checks, health, inspect.
- Modify `src/isotope/features/social/__init__.py`: export Phase 9 names.
- Create `tests/unit/features/social/test_social_operations.py`: policy, pause, logs, inspect tests.

## Task 1: Operations Controls

**Files:**
- Create: `src/isotope/features/social/config.py`
- Create: `src/isotope/features/social/audit_log.py`
- Create: `src/isotope/features/social/operations.py`
- Modify: `src/isotope/features/social/__init__.py`
- Test: `tests/unit/features/social/test_social_operations.py`

- [ ] **Step 1: Write failing tests**

Create tests proving:

- whitelist, blacklist, and pause state decide whether a group can be processed;
- an operator can pause one group without pausing another;
- a non-operator cannot pause/resume groups;
- decision/send/capability logs are queryable by group;
- role card, lorebook, and sticker library inspection returns useful current data;
- health check reports paused groups, log counts, and adapter state.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_operations.py -q
```

Expected: FAIL because operations objects do not exist.

- [ ] **Step 3: Implement operations objects**

Create:

- `SocialGroupPolicy`
- `SocialOperationsConfig`
- `SocialAuditEntry`
- `SocialAuditLog`
- `SocialOperationsController`
- `SocialPolicyDecision`

Behavior:

- `can_process_group(group_id)` returns allowed bool and concrete reason;
- `pause_group(group_id, operator_user_id)` and `resume_group(...)` require configured operators;
- `record_decision`, `record_send`, and `record_capability` append queryable audit entries;
- `review_dry_run` returns proposed/selected/rejected decision dictionaries;
- `health_check(adapter_states=())` returns status and counts;
- inspect methods return role/lorebook/sticker dictionaries.

- [ ] **Step 4: Run operation tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_operations.py -q
```

Expected: PASS.

## Task 2: Regression And Product Acceptance

- [ ] **Step 1: Run full social regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/integration/social/test_social_fake_platform_flow.py -q
```

Expected: all social tests pass.

- [ ] **Step 2: Run QQ adapter regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: all QQ adapter tests pass, with real smoke skipped unless enabled.

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

- an operator can debug why the bot spoke or did not speak;
- one paused group does not affect another group;
- send and capability failures are visible in logs;
- inspect output is understandable without reading code.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-9-operations.md src/isotope/features/social tests/unit/features/social/test_social_operations.py
git commit -m "feat(social): add operations controls"
```
