# QQ Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local QQ runtime harness that processes OneBot/NapCat events through the social core, defaults to dry-run, records operations logs, and can optionally send through the injected OneBot adapter.

**Architecture:** Keep runtime wiring in `src/isotope/features/social/runtime.py` so QQ adapter details stay in `src/isotope/integrations/qq`. The runtime receives normalized messages from an adapter with `receive_next()` / `send_action(...)`, applies group operations policy, builds social context, runs `SocialDecisionLoop`, records decision/send audit entries, and returns an inspectable turn result.

**Tech Stack:** Python 3.13, pytest, dataclasses, existing social core and QQ OneBot adapter.

---

## Reuse Audit

- Reuse `OneBotAdapter.receive_next()` and `OneBotAdapter.send_action(...)`; no new QQ event protocol.
- Reuse `SocialContextBuilder` for role card, lorebook, recent messages, and memory previews.
- Reuse `SocialDecisionLoop` and `SocialDecisionRequest` for decision-making.
- Reuse `SocialOperationsController.can_process_group`, `record_decision`, and `record_send`.
- Reuse `SocialSendFeedback` as the runtime output for both sent and failed sends.
- Do not create a real network client in this phase; tests use `FakeOneBotClient`.
- Do not build CLI yet; this phase creates the runtime object that CLI will call next.

## File Structure

- Create `src/isotope/features/social/runtime.py`: runtime config, turn result, runtime loop.
- Modify `src/isotope/features/social/__init__.py`: export runtime names.
- Create `tests/integration/social/test_qq_runtime_wiring.py`: dry-run, send, policy, failure tests.

## Task 1: Runtime Integration Tests

**Files:**
- Create: `tests/integration/social/test_qq_runtime_wiring.py`

- [ ] **Step 1: Write failing runtime tests**

Create tests proving:

- dry-run processes a OneBot event, proposes a reply, records a decision log, and sends nothing;
- send mode sends through `OneBotAdapter`, records decision and send logs, and returns sent feedback;
- blocked or paused group does not run the decision loop and returns a policy reason;
- OneBot send failure is recorded as failed send feedback and processing continues to return a turn result.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/social/test_qq_runtime_wiring.py -q
```

Expected: FAIL because `SocialRuntime` and related objects do not exist.

## Task 2: Runtime Implementation

**Files:**
- Create: `src/isotope/features/social/runtime.py`
- Modify: `src/isotope/features/social/__init__.py`

- [ ] **Step 1: Implement runtime objects**

Create:

- `SocialRuntimeConfig`
- `SocialRuntimeTurn`
- `SocialRuntime`

Behavior:

- `process_next(...)` returns `None` when adapter has no event;
- blocked/paused groups return a turn with `policy.allowed == False`, no decision, and no send feedback;
- dry-run defaults from config and can be overridden per call;
- decision logs are recorded for every processed allowed message;
- send feedback is recorded when selected send actions are sent;
- recent send feedback is carried into the next decision to suppress repeated replies;
- adapter connection state is available through `health()`.

- [ ] **Step 2: Run runtime tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/social/test_qq_runtime_wiring.py -q
```

Expected: PASS.

## Task 3: Regression And Product Acceptance

- [ ] **Step 1: Run runtime tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/social/test_qq_runtime_wiring.py -q
```

Expected: PASS.

- [ ] **Step 2: Run social and QQ regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: all tests pass, with real QQ smoke skipped unless explicitly enabled.

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

- runtime defaults to dry-run and does not accidentally send;
- allowlist/pause policy prevents processing before decision-making;
- sent and failed sends are visible in operations logs;
- runtime output can explain the event, policy decision, decision result, and send feedback.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-runtime-wiring.md src/isotope/features/social/runtime.py src/isotope/features/social/__init__.py tests/integration/social/test_qq_runtime_wiring.py
git commit -m "feat(social): add qq runtime wiring"
```
