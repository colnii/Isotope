# QQ OneBot Live Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the QQ social runtime to a real NapCat/OneBot 11 WebSocket endpoint for sustained event receive and real message send.

**Architecture:** Add a focused OneBot WebSocket client under `src/isotope/integrations/qq/` and keep message normalization/sending in `OneBotAdapter`. Extend `isotope-social qq` with a live command that builds the existing `SocialRuntime`, consumes events from the client, records state after each processed turn, and defaults to dry-run unless `--send` is present.

**Tech Stack:** Python 3.13, pytest, `websockets`, argparse, existing social runtime and QQ adapter.

---

## Reuse Audit

- Reuse `OneBotAdapter` for event normalization and outgoing segment rendering.
- Reuse `SocialRuntime` for group policy, context building, decision selection, send feedback, and audit logging.
- Reuse `SocialOperationsController` state persistence from the current CLI runner.
- Add `websockets` as a runtime dependency because NapCat supports OneBot WebSocket event/request exchange and the Python examples use this package.
- Do not add NoneBot/AstrBot as a runtime dependency in this phase; their adapters are full bot frameworks and would duplicate the platform-neutral social core.

## File Structure

- Create `src/isotope/integrations/qq/onebot_ws_client.py`: sync wrapper around an async OneBot 11 WebSocket connection.
- Modify `src/isotope/integrations/qq/__init__.py`: export `OneBotWebSocketClient`.
- Modify `src/isotope/features/social/runner.py`: add `qq live-run` and reusable runtime construction helpers.
- Modify `pyproject.toml`: add `websockets>=15.0`.
- Modify `docs/current/qq-group-chatbot.md` and `docs/current/qq-group-chatbot-operations.md`: document live run commands and real smoke.
- Add `tests/unit/integrations/qq/test_onebot_ws_client.py`: fake in-memory WebSocket tests.
- Extend `tests/unit/features/social/test_social_runner.py`: CLI live-run tests.

## Task 1: OneBot WebSocket Client Tests

- [ ] **Step 1: Write failing tests**

Create `tests/unit/integrations/qq/test_onebot_ws_client.py` proving:

- event frames are returned by `receive_event()`;
- API response frames are matched by `echo`;
- `send_group_msg` and `send_private_msg` send OneBot action payloads;
- `connection_state()` reports connected, pending events, and API sequence count;
- timeout while waiting for API response raises a clear `TimeoutError`.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_ws_client.py -q
```

Expected: FAIL because `isotope.integrations.qq.onebot_ws_client` does not exist.

## Task 2: OneBot WebSocket Client Implementation

- [ ] **Step 1: Implement `OneBotWebSocketClient`**

The client must expose the same methods consumed by `OneBotAdapter`:

- `receive_event() -> dict[str, Any] | None`
- `send_group_msg(group_id: str, message: list[dict[str, Any]]) -> dict[str, Any]`
- `send_private_msg(user_id: str, message: list[dict[str, Any]]) -> dict[str, Any]`
- `connection_state() -> OneBotConnectionState`
- `close() -> None`

- [ ] **Step 2: Verify GREEN**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_ws_client.py -q
```

Expected: PASS.

## Task 3: CLI Live Run Tests

- [ ] **Step 1: Write failing tests**

Extend `tests/unit/features/social/test_social_runner.py` proving:

- `qq live-run --websocket-url ws://... --max-events 1 --json` builds a real WebSocket client class, processes one turn, saves state, and defaults to dry-run;
- `qq live-run --send --max-events 1 --json` allows send feedback to be recorded;
- `qq live-run --max-events 0 --json` returns health without consuming events, useful as a connection check;
- missing `websockets` dependency returns an actionable error in JSON.

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: FAIL because `qq live-run` is not implemented.

## Task 4: CLI Live Run Implementation

- [ ] **Step 1: Add parser and command handler**

Add:

```bash
isotope-social qq live-run --config-json config.json --state-root .isotope/qq \
  --websocket-url ws://127.0.0.1:3001 --max-events 10 --json
```

Flags:

- `--send`: enable real sends;
- `--max-events`: stop after N accepted OneBot events; `0` means connect/health only;
- `--receive-timeout-seconds`: stop cleanly if no event arrives within this time;
- `--access-token`: optional NapCat/OneBot token.

- [ ] **Step 2: Verify CLI tests**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

## Task 5: Documentation And Regression

- [ ] **Step 1: Update docs**

Document:

- NapCat WebSocket setup expectation;
- dry-run live command;
- explicit send command;
- health-only connection check;
- real smoke environment variables.

- [ ] **Step 2: Run regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_ws_client.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass, with real QQ smoke skipped unless explicitly enabled.

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

## Product Acceptance

- [ ] Operators can connect to a real NapCat OneBot WebSocket endpoint.
- [ ] Live mode defaults to dry-run and cannot send unless `--send` is passed.
- [ ] The same pause/resume and group allowlist policy applies before the decision loop.
- [ ] Every processed turn is persisted to the audit log after processing.
- [ ] Health-only mode can verify configuration without consuming group messages.
- [ ] The documentation gives exact commands for dry-run, send-enabled beta, and real smoke.
