# QQ Group Chatbot Phase 8 QQ Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the platform-neutral social core to OneBot/NapCat-style QQ events and sends without adding a hard QQ runtime dependency.

**Architecture:** Keep QQ details inside `src/isotope/integrations/qq`. `OneBotAdapter` converts incoming OneBot events into `SocialMessage`, converts `SocialReplyAction` into OneBot message segments, calls an injected client, and turns platform errors into `SocialSendFeedback` instead of corrupting social state.

**Tech Stack:** Python 3.13, pytest, dataclasses, stdlib only.

---

## Reuse Audit

- Reuse `SocialMessage` and `SocialMessagePart` for normalized incoming events.
- Reuse `SocialReplyAction` and `SocialSendFeedback` for outgoing sends.
- Reuse no external QQ library in unit tests; use `FakeOneBotClient`.
- Do not modify social core for QQ-specific segment fields; store those in `platform_data`.
- Do not implement Amadeus MCP in this phase; OneBot/NapCat is the selected first adapter path.

## File Structure

- Create `src/isotope/integrations/qq/__init__.py`: public QQ integration exports.
- Create `src/isotope/integrations/qq/onebot_client.py`: in-memory fake client and client protocol shape.
- Create `src/isotope/integrations/qq/onebot_adapter.py`: event normalization, send mapping, duplicate filtering, health state.
- Create `tests/unit/integrations/qq/test_onebot_adapter.py`: segment mapping and error tests.
- Create `tests/integration/qq/test_fake_onebot_flow.py`: fake end-to-end OneBot flow.

## Task 1: OneBot Adapter Unit Tests

**Files:**
- Create: `src/isotope/integrations/qq/__init__.py`
- Create: `src/isotope/integrations/qq/onebot_client.py`
- Create: `src/isotope/integrations/qq/onebot_adapter.py`
- Test: `tests/unit/integrations/qq/test_onebot_adapter.py`

- [ ] **Step 1: Write failing unit tests**

Create tests proving:

- OneBot group event maps text, at, face, image, reply, and file segments;
- duplicate message IDs are ignored on the second normalize call;
- mixed `SocialReplyAction` maps to OneBot reply/at/text/face/image segments;
- platform send failure returns failed `SocialSendFeedback` with concrete error.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py -q
```

Expected: FAIL because QQ integration modules do not exist.

- [ ] **Step 3: Implement adapter and fake client**

Create:

- `FakeOneBotClient`
- `OneBotAdapter`
- `OneBotConnectionState`

Behavior:

- support `message_type=group/private`;
- normalize segment types `text`, `at`, `face`, `image`, `reply`, `file`;
- image segments with `sub_type=sticker` map to `kind="sticker"`;
- unknown segments map to `kind="raw"`;
- duplicate `message_id` returns `None`;
- send group/private actions through injected client;
- platform exceptions become `SocialSendFeedback(status="failed", platform_error=...)`.

- [ ] **Step 4: Run unit tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py -q
```

Expected: PASS.

## Task 2: Fake OneBot Integration

**Files:**
- Test: `tests/integration/qq/test_fake_onebot_flow.py`

- [ ] **Step 1: Write failing integration tests**

Create tests proving:

- fake client queued event normalizes into `SocialMessage`;
- adapter sends sticker-capable reply through fake client;
- history backfill skips duplicate events;
- real smoke is disabled unless explicit env vars are provided.

- [ ] **Step 2: Run integration test to verify failure before implementation**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: FAIL before implementation or PASS after Task 1 implementation if the test only needs existing adapter behavior.

- [ ] **Step 3: Run integration tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: PASS.

## Task 3: Regression And Product Acceptance

- [ ] **Step 1: Run QQ adapter tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: all QQ tests pass.

- [ ] **Step 2: Run social regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/integration/social/test_social_fake_platform_flow.py -q
```

Expected: all social tests pass.

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

- QQ platform failure stays in adapter feedback;
- sticker/image media refs are not dropped;
- duplicate events do not produce duplicate normalized messages;
- real smoke remains opt-in.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-group-chatbot-phase-8-qq-adapter.md src/isotope/integrations/qq tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py
git commit -m "feat(qq): add onebot adapter"
```
