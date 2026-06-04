# Social QQ First-Run Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generated `first-run.sh` script to QQ beta packs that runs the safe pre-live checks in order without consuming QQ group messages.

**Architecture:** Reuse existing generated scripts as the source of behavior. `first-run.sh` calls `diagnostics.sh`, `beta-check`, checks that `logs/replay-report.json` exists, then calls `startup-check.sh` and `health.sh`. It does not call `dry-run.sh`, `send-run.sh`, or any command with `--max-events` greater than `0`.

**Tech Stack:** Python 3.13, bash script generation, pytest, existing QQ social beta pack generator.

---

### Task 1: Red Tests

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Add generated script assertions**

Update `test_social_runner_qq_init_beta_writes_operator_pack` to require:

- `first-run.sh` appears in the generated scripts payload;
- `first-run.sh` contains `./diagnostics.sh`;
- `first-run.sh` contains `qq beta-check --pack-dir . --json`;
- `first-run.sh` checks `logs/replay-report.json` before `./startup-check.sh`;
- `first-run.sh` contains `./startup-check.sh` before `./health.sh`;
- `first-run.sh` does not contain `./dry-run.sh`, `./send-run.sh`, or `--send`;
- generated README mentions `./first-run.sh`;
- `bash -n` covers `first-run.sh`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack -q
```

Expected: FAIL because `first-run.sh` is not generated yet.

### Task 2: Script Generation

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`

- [x] **Step 1: Add script name**

Add `first-run.sh` to `SCRIPT_NAMES` after `diagnostics.sh` so beta-check required-file and shell-syntax checks cover it automatically.

- [x] **Step 2: Add script body**

Generate a script body that:

1. runs `./diagnostics.sh`;
2. runs `isotope-social qq beta-check --pack-dir . --json`;
3. checks `[ -f logs/replay-report.json ]`;
4. if missing, prints exact `init-replay` and `replay` commands to stderr and exits `2`;
5. runs `./startup-check.sh`;
6. runs `./health.sh`.

- [x] **Step 3: Update generated README**

Make first-run order use `./first-run.sh` after applying the profile and clarify that it stops before `dry-run.sh`.

- [x] **Step 4: Verify green**

Run the focused init-beta test from Task 1. Expected: PASS.

### Task 3: Docs and Final Verification

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Update runbooks**

Document `./first-run.sh` in generated beta pack flow and state that it does not consume messages or send replies.

- [x] **Step 2: Add docs coverage**

Require `first-run.sh` in the QQ runbook docs test.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/unit/llm/test_system_prompt_assets.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- A fresh QQ beta pack contains executable `first-run.sh`.
- `first-run.sh` runs only no-message or preflight checks.
- Missing replay report stops `first-run.sh` with exact next commands.
- A ready pack reaches `health.sh` but never `dry-run.sh` or `send-run.sh`.
