# QQ Real Smoke Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder real QQ smoke guard with an opt-in harness that actually exercises the live OneBot/NapCat path.

**Architecture:** Keep the real smoke in `tests/integration/qq/test_fake_onebot_flow.py` so the existing fake flow and real guard stay together. The opt-in test builds a temporary config, calls `isotope.features.social.runner.main(["qq", "live-run", ...])`, and supports health-only plus one-event dry-run modes through environment variables.

**Tech Stack:** Python 3.13, pytest, existing `isotope-social qq live-run`, NapCat/OneBot WebSocket.

---

## Reuse Audit

- Reuse `isotope.features.social.runner.main` instead of duplicating CLI/runtime construction.
- Reuse the current role-card fixture helper shape by embedding a tiny valid role card directly in the integration test.
- Reuse `live-run --max-events 0` for health-only smoke.
- Do not send real group messages from automated tests. Send-enabled beta remains a manual operator command.

## Environment Contract

- `ISOTOPE_QQ_REAL_SMOKE=1`: opt in.
- `ISOTOPE_QQ_ONEBOT_URL=ws://127.0.0.1:3001`: required endpoint.
- `ISOTOPE_QQ_TEST_GROUP=<group_id>`: required allowlisted group.
- `ISOTOPE_QQ_BOT_USER_ID=<bot_qq>`: optional, defaults to `bot_qq`.
- `ISOTOPE_QQ_ACCESS_TOKEN=<token>`: optional.
- `ISOTOPE_QQ_REAL_SMOKE_MODE=health|dry-run`: optional, defaults to `health`.
- `ISOTOPE_QQ_REAL_SMOKE_TIMEOUT=3`: optional receive timeout seconds.

## Task 1: RED Tests

- [ ] **Step 1: Update real smoke test**

Change `test_real_qq_smoke_is_explicitly_opt_in` so:

- default path still skips when `ISOTOPE_QQ_REAL_SMOKE != 1`;
- opt-in without `ISOTOPE_QQ_ONEBOT_URL` fails with a clear assertion;
- `health` mode calls `qq live-run --max-events 0`;
- `dry-run` mode calls `qq live-run --max-events 1` without `--send`;
- returned JSON must include `status: ok`, `command: live-run`, and the configured state file.

- [ ] **Step 2: Verify RED**

Run:

```bash
ISOTOPE_QQ_REAL_SMOKE=1 PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py::test_real_qq_smoke_is_explicitly_opt_in -q
```

Expected: FAIL because the test only checks the environment variable today.

## Task 2: Harness Implementation

- [ ] **Step 1: Implement helpers in the integration test**

Add test-local helpers:

- `_real_smoke_env()` validates required env vars.
- `_real_smoke_config()` writes a minimal valid config under `tmp_path`.
- `_real_smoke_args()` builds `qq live-run` arguments.

- [ ] **Step 2: Verify smoke skip and local fake regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: fake tests pass and real smoke is skipped.

## Task 3: Docs And Regression

- [ ] **Step 1: Update runbooks**

Document health and dry-run smoke modes, required env vars, and that automated smoke never passes `--send`.

- [ ] **Step 2: Run selected regression**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py tests/unit/features/social/test_social_runner.py tests/unit/integrations/qq/test_onebot_ws_client.py -q
```

Expected: all selected tests pass with one skipped real smoke by default.

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected: no output.

## Product Acceptance

- [ ] The default test suite cannot send a QQ message.
- [ ] Setting `ISOTOPE_QQ_REAL_SMOKE=1` exercises the real `live-run` command instead of only checking env vars.
- [ ] Health mode checks WebSocket connectivity without consuming group events.
- [ ] Dry-run mode consumes at most one real event and records a decision without sending.
- [ ] Missing env vars fail with actionable messages.
