# Social QQ Diagnostics Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generated `diagnostics.sh` script to QQ beta packs so operators can run the beta diagnostics command from inside the pack without remembering CLI arguments.

**Architecture:** Reuse the existing `isotope-social qq beta-diagnostics` command as the single diagnostics implementation. Extend generated beta pack script metadata and documentation; do not duplicate diagnostics rules in shell.

**Tech Stack:** Python 3.13, argparse, pytest, existing social QQ beta pack generator.

---

### Task 1: Red Tests

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Add generated script assertions**

Update `test_social_runner_qq_init_beta_writes_operator_pack` to require:

- `diagnostics.sh` appears in the generated `scripts` payload;
- `diagnostics.sh` contains `qq beta-diagnostics`;
- `diagnostics.sh` passes `--pack-dir .`;
- generated README mentions `./diagnostics.sh`;
- every generated script, including diagnostics, passes `bash -n`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_beta_writes_operator_pack -q
```

Expected: FAIL because `diagnostics.sh` is not generated yet.

### Task 2: Script Generation

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`

- [x] **Step 1: Add script name**

Add `diagnostics.sh` to `SCRIPT_NAMES` near `startup-check.sh` so beta-check required-file and shell-syntax checks cover it automatically.

- [x] **Step 2: Add script body**

In `_script_body`, return:

```bash
isotope-social qq beta-diagnostics --pack-dir . --json
```

using the existing `_common_env()` prefix.

- [x] **Step 3: Update generated README**

Make first-run order use `./diagnostics.sh` after applying the profile, and explain that it wraps `qq beta-diagnostics`.

- [x] **Step 4: Verify green**

Run the focused init-beta test from Task 1. Expected: PASS.

### Task 3: Docs and Verification

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Update runbooks**

Document `./diagnostics.sh` in the generated beta pack flow and explain that it does not connect to QQ.

- [x] **Step 2: Add docs coverage**

Require `diagnostics.sh` in the QQ runbook docs test.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/unit/llm/test_system_prompt_assets.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- A fresh QQ beta pack contains executable `diagnostics.sh`.
- `diagnostics.sh` delegates to `isotope-social qq beta-diagnostics --pack-dir . --json`.
- Existing beta-check covers the new script through required-file and shell-syntax checks.
- Operator docs point to `./diagnostics.sh` before `./startup-check.sh`, `./health.sh`, or send-enabled flow.
