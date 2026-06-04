# Social QQ Beta Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a QQ beta diagnostics command that gives operators one readable pre-start checklist from an existing generated beta pack.

**Architecture:** Reuse the generated beta pack config, `check_qq_beta_pack`, startup gate checks, role-card and sticker parsers, and the shared LLM provider resolver. Add a focused diagnostics builder so the CLI handler stays thin and the output can be tested without connecting to QQ.

**Tech Stack:** Python 3.13, argparse, pytest, existing social QQ command modules.

---

### Task 1: CLI Contract Tests

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write the failing complete diagnostics test**

Add a test that creates a generated beta pack, applies a profile, writes a replay report, runs:

```bash
isotope-social qq beta-diagnostics --pack-dir <beta_dir> --json
```

Expected JSON fields:

- `command == "beta-diagnostics"`
- `status == "ready"`
- `summary.allowed_groups == ["99999"]`
- `summary.operator_user_ids == ["op"]`
- `summary.bot_user_id == "bot_qq"`
- `summary.websocket_url == "ws://127.0.0.1:3001"`
- `summary.reply_provider == "deterministic"`
- `summary.llm.required is False`
- `summary.profile.role_name == "群聊工程猫"`
- `summary.stickers.entry_count > 0`
- `summary.replay_report.exists is True`
- `next_steps[0]["command"] == "./health.sh"`

- [x] **Step 2: Write the failing missing-profile test**

Add a test that runs diagnostics immediately after `init-beta`. Expected:

- `status == "needs_action"`
- `summary.profile.applied is False`
- `next_steps[0]["command"]` contains `isotope-social qq init-profile`
- `next_steps` also contains `isotope-social qq apply-profile`

- [x] **Step 3: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_diagnostics_reports_ready_pack tests/unit/features/social/test_social_runner.py::test_social_runner_qq_beta_diagnostics_guides_missing_profile -q
```

Expected: FAIL because `beta-diagnostics` is not registered yet.

### Task 2: Diagnostics Builder

**Files:**
- Create: `src/isotope/features/social/beta_diagnostics.py`
- Modify: `src/isotope/features/social/qq_beta_commands.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_handlers.py`

- [x] **Step 1: Implement `build_qq_beta_diagnostics`**

Create a builder that reads `<pack-dir>/config.json`, reports config summary,
parses role/sticker assets when paths exist, detects `logs/replay-report.json`,
runs startup checks when the replay report exists, and returns `status:
"ready"` only when beta pack, profile, sticker, LLM reply provider, and replay
checks all pass.

- [x] **Step 2: Add next-step generation**

Generate operator commands in this priority:

1. missing profile: `isotope-social qq init-profile ...` and `isotope-social qq apply-profile ...`
2. missing replay report: `isotope-social qq init-replay ...` and `isotope-social qq replay ...`
3. LLM provider missing: configure the shared Isotope LLM provider or set `runtime.reply_provider = "deterministic"`
4. ready: `./health.sh`, `./dry-run.sh`, `./review-dry-run.sh`

- [x] **Step 3: Register CLI command**

Add `qq beta-diagnostics --pack-dir <dir> --json`, map it to
`handle_beta_diagnostics`, and return `_exit_code = 2` when status is
`needs_action`.

- [x] **Step 4: Verify green**

Run the two focused tests from Task 1. Expected: PASS.

### Task 3: Docs and Final Verification

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Document operator flow**

Add `beta-diagnostics` after `apply-profile` and before `beta-check` in the
runbooks. Explain that it is a no-network configuration checklist.

- [x] **Step 2: Add docs coverage**

Require `beta-diagnostics`, `next_steps`, and `reply_provider` in
`tests/unit/docs/test_qq_group_chatbot_docs.py`.

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/unit/llm/test_system_prompt_assets.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can run one command after `init-beta` to see exactly which QQ beta setup step is missing.
- The diagnostics output names real configured IDs and paths instead of generic advice.
- The command does not connect to OneBot and does not send messages.
- LLM reply mode is explained with provider status and a concrete next action.
- A ready pack points to `./health.sh` first, not straight to sending.
