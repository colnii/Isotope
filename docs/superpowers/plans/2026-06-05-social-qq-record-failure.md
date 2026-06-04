# Social QQ Record Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a QQ beta failure-recording entry point so operators can append structured failures without hand-editing `logs/failures.json`.

**Architecture:** Reuse the existing `failures.json` shape consumed by beta-day-report and regression-intake. Add a small append builder, a `qq record-failure` CLI handler, and a generated `record-failure.sh` wrapper that writes to the beta pack's `logs/failures.json`.

**Tech Stack:** Python 3.13, argparse, JSON file append, bash script generation, pytest.

---

### Task 1: Red Tests

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Add CLI append test**

Add a test that runs:

```bash
isotope-social qq record-failure --failures-json <path> --date 2026-06-05 --group 99999 --symptom 表情包过度热情 --observed-input 这能发吗 --decision-log-entry decision-1 --send-or-capability-log-entry send-1 --root-cause sticker scoring too high --fix tune sticker score --regression-test tests/integration/qq/test_fake_onebot_flow.py --json
```

Expected:

- exit code `0`;
- JSON payload has `command == "record-failure"`;
- JSON payload has `failure_count == 1`;
- `failures.json` contains one failure with `status == "open"` and all provided fields.

- [x] **Step 2: Add generated script test**

Update init-beta tests to require:

- `record-failure.sh` appears in generated scripts;
- `record-failure.sh` contains `qq record-failure`;
- `record-failure.sh` writes `logs/failures.json`;
- `record-failure.sh` accepts symptom from the first argument;
- generated README mentions `./record-failure.sh`.

Add a behavior test that runs:

```bash
./record-failure.sh "表情包过度热情" "这能发吗"
```

and asserts `logs/failures.json` gets one open entry for group `99999`.

- [x] **Step 3: Verify red**

Run the focused tests. Expected: FAIL because `record-failure` is not registered and `record-failure.sh` is not generated.

### Task 2: Implementation

**Files:**
- Create: `src/isotope/features/social/failure_log.py`
- Modify: `src/isotope/features/social/qq_beta_commands.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `src/isotope/features/social/beta_pack.py`

- [x] **Step 1: Implement append builder**

Create `record_qq_beta_failure(config)` that creates or reads `failures.json`,
validates `failures` as a list, appends a structured failure with default
`status: "open"`, and writes pretty sorted JSON.

- [x] **Step 2: Add CLI command**

Register `qq record-failure` with required `--failures-json`, `--date`,
`--group`, and `--symptom`; optional `--observed-input`,
`--decision-log-entry`, `--send-or-capability-log-entry`, `--root-cause`,
`--fix`, `--regression-test`, and `--status`.

- [x] **Step 3: Add generated script**

Generate `record-failure.sh` that accepts symptom from `$1` or
`ISOTOPE_QQ_FAILURE_SYMPTOM`, observed input from `$2` or
`ISOTOPE_QQ_FAILURE_OBSERVED_INPUT`, defaults date to `date +%F`, and appends
optional env-backed fields only when set.

### Task 3: Docs and Verification

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Update runbooks**

Document `qq record-failure` and generated `./record-failure.sh` in the failure log section and beta flow.

- [x] **Step 2: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/unit/llm/test_system_prompt_assets.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can append failures through CLI or generated script.
- The JSON shape remains compatible with beta-day-report and regression-intake.
- Missing symptom is rejected with a clear error before writing.
- Existing failures are preserved.
