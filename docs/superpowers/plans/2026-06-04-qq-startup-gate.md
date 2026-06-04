# QQ Startup Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a QQ startup check that blocks generated live dry-run/send scripts until the beta pack, applied profile, sticker assets, and replay report are all ready.

**Architecture:** Keep existing `beta_check.py` and `replay.py` as the source of truth. Add a focused `startup_gate.py` module that aggregates those results and validates profile/sticker/replay readiness. Wire one new `qq startup-check` CLI command and make generated `dry-run.sh` / `send-run.sh` call `startup-check.sh` before connecting to OneBot.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing QQ social beta pack/runtime modules.

---

### Task 1: Startup Gate CLI Contract

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`
- Create: `src/isotope/features/social/startup_gate.py`
- Modify: `src/isotope/features/social/runner.py`

- [x] **Step 1: Write passing-path failing test**

Add a test that creates a beta pack, applies a profile pack, creates and runs replay, then runs:

```bash
isotope-social qq startup-check --pack-dir <beta_dir> \
  --replay-report <beta_dir>/logs/replay-report.json --json
```

Expected JSON shape:

```json
{
  "status": "ok",
  "command": "startup-check",
  "ready": true,
  "checks": [
    {"name": "beta_pack", "ok": true},
    {"name": "profile_assets", "ok": true},
    {"name": "sticker_assets", "ok": true},
    {"name": "replay_report", "ok": true}
  ]
}
```

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_startup_check_passes_after_profile_and_replay -q
```

Expected: FAIL because `startup-check` is not registered.

- [x] **Step 3: Implement startup gate module**

Create `src/isotope/features/social/startup_gate.py` with:

- `QQStartupGateConfig(pack_dir: Path, replay_report: Path, min_sticker_candidates: int = 1)`
- `QQStartupGateResult(pack_dir, replay_report, checks)` with `ready` and `to_public_dict()`
- `check_qq_startup_gate(config)` returning four checks:
  - `beta_pack`: wraps `check_qq_beta_pack`
  - `profile_assets`: requires `role_card_path` and `sticker_library_path`, paths exist, and both parse
  - `sticker_assets`: requires at least one sticker entry with media data
  - `replay_report`: requires `passed: true`, `dry_run: true`, enough `summary.sticker_candidate_count`, and no sent group messages

- [x] **Step 4: Wire CLI command**

Add `qq startup-check` to `runner.py`. On success return `status: ok`. On failed gate return JSON with `status: blocked`, `ready: false`, and `checks`, and exit code `2`.

- [x] **Step 5: Verify green**

Run the focused passing test again. Expected: PASS.

### Task 2: Failure Visibility and Generated Script Gate

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `src/isotope/features/social/beta_check.py`

- [x] **Step 1: Write failing blocked-path test**

Add a test that creates a default beta pack without profile/replay, runs `qq startup-check`, and asserts:

- exit code is `2`;
- JSON status is `blocked`;
- failed checks include `profile_assets`, `sticker_assets`, and `replay_report`;
- error output includes checks instead of hiding them behind a plain message.

- [x] **Step 2: Write failing script test**

Extend the init-beta test to assert:

- generated scripts include `startup-check.sh`;
- `dry-run.sh` calls `./startup-check.sh`;
- `send-run.sh` still refuses without `ISOTOPE_QQ_ENABLE_SEND=1`;
- after the send guard, `send-run.sh` calls `./startup-check.sh`.

- [x] **Step 3: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_startup_check_blocks_missing_profile_and_replay tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack -q
```

Expected: FAIL because startup check and script gate are missing.

- [x] **Step 4: Update generated beta pack**

Add `startup-check.sh` to `SCRIPT_NAMES`, make `dry-run.sh` call it before `live-run`, and make `send-run.sh` keep the send env guard first then call it before `live-run --send`.

- [x] **Step 5: Update beta pack check**

`beta-check` should include `startup-check.sh` in required files and shell syntax checks through `SCRIPT_NAMES`. Keep `send_guard` focused on the send env refusal so operators cannot accidentally send while startup assets are missing.

- [x] **Step 6: Verify green**

Run the two focused tests again. Expected: PASS.

### Task 3: Docs and Regression

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Add docs assertion**

Require docs to mention `startup-check`, `ready`, `profile_assets`, and `replay_report`.

- [x] **Step 2: Update runbooks**

Document the new order: apply profile, run beta-check, run replay, run startup-check, then run generated `dry-run.sh`; `send-run.sh` remains manually enabled and also checks startup readiness.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Generated beta packs include a startup gate script.
- Generated dry-run/send scripts cannot proceed through the normal operator path until startup readiness is true.
- The CLI prints structured failed checks, not just a vague error string.
- Replay pass/fail and sticker candidate count are part of the startup decision.
