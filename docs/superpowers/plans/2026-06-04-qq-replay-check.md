# QQ Replay Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add QQ group replay files and a replay command that evaluates persona/sticker/speaking decisions without touching real QQ.

**Architecture:** Keep replay file/report helpers in `src/isotope/features/social/replay.py`. `runner.py` exposes `qq init-replay` and `qq replay`; replay uses existing `FakeOneBotClient`, `OneBotAdapter`, `SocialRuntime`, operations state, and audit log, so it exercises the same decision path as `run` and `live-run`.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing QQ social runtime.

---

### Task 1: Replay Template

**Files:**
- Create: `src/isotope/features/social/replay.py`
- Modify: `src/isotope/features/social/runner.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing init-replay test**

Add a test that runs:

```python
main([
    "qq", "init-replay",
    "--output", str(replay_path),
    "--group", "99999",
    "--bot-user-id", "bot_qq",
    "--json",
])
```

Assert the file contains a JSON object with `events`, `runtime`, and two OneBot group events. Runtime must include `wake_keywords`, `sticker_emotion`, `sticker_scene_tags`, and `allow_sticker_only`.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_replay_writes_editable_event_file -q
```

Expected: FAIL because `init-replay` is not registered.

- [x] **Step 3: Implement template generation**

Create `QQReplayTemplateConfig`, `QQReplayTemplateResult`, and `create_qq_replay_template(...)`. The template should be realistic enough to test wake behavior and sticker selection: one mention event and one normal group event.

- [x] **Step 4: Wire CLI and verify green**

Add:

```text
qq init-replay --output <file> --group <group_id> --bot-user-id <bot_qq> [--json]
```

Run the focused test again. Expected: PASS.

### Task 2: Replay Execution Report

**Files:**
- Modify: `src/isotope/features/social/replay.py`
- Modify: `src/isotope/features/social/runner.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing replay test**

Create a beta pack, profile pack, apply profile, create replay file, then run:

```python
main([
    "qq", "replay",
    "--config-json", str(beta_dir / "config.json"),
    "--state-root", str(beta_dir / "state"),
    "--replay-json", str(replay_path),
    "--output", str(report_path),
    "--json",
])
```

Assert the report exists, dry-run is true, processed count equals event count, turns include decisions, summary includes proposed/selected/sticker counts, and no send feedback was recorded.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_replay_writes_decision_report -q
```

Expected: FAIL because `replay` is not registered.

- [x] **Step 3: Implement replay helpers**

Add helpers to load replay JSON, validate events, extract runtime overrides, build a report summary from public turns, and write the report JSON.

- [x] **Step 4: Wire replay handler**

Runner should queue all replay events into `FakeOneBotClient`, build the existing runtime, call `process_next` once per event with replay runtime overrides and `dry_run=True`, save state, write the report, and return paths/counts.

- [x] **Step 5: Verify green**

Run the focused replay test again. Expected: PASS.

### Task 3: Docs and Regression

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Add docs assertion**

Require docs to mention `init-replay`, `replay`, `replay.json`, and `replay-report.json`.

- [x] **Step 2: Update runbooks**

Document:

```bash
isotope-social qq init-replay --output .isotope/qq-beta/replay.json \
  --group <controlled_group_id> --bot-user-id <bot_qq> --json
isotope-social qq replay --config-json .isotope/qq-beta/config.json \
  --state-root .isotope/qq-beta/state \
  --replay-json .isotope/qq-beta/replay.json \
  --output .isotope/qq-beta/logs/replay-report.json --json
```

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can create a replay file without hand-writing OneBot JSON from scratch.
- Replay runs through the same role card, sticker library, decision loop, and audit log as normal QQ runs.
- The report shows enough detail to judge whether the bot sounded appropriate and whether sticker behavior made sense.
- Replay never sends messages by default.
