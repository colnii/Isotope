# QQ Startup Sticker Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make QQ startup checks verify imported sticker files and replay-required sticker IDs.

**Architecture:** Reuse `StickerLibrary.from_dict` for schema validation, then add startup-only asset checks in `startup_gate.py`. Keep importer output aligned by writing `local_path` relative to the output library location.

**Tech Stack:** Python 3.13, pytest, existing `isotope-social qq startup-check`.

---

### Task 1: Startup Sticker Asset Checks

**Files:**
- Modify: `src/isotope/features/social/sticker_assets/importer.py`
- Modify: `src/isotope/features/social/startup_gate.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing tests**

Add tests that prove:

- `import-stickers` writes `local_path` relative to the output library directory.
- `startup-check` fails `sticker_assets` when a referenced `local_path` file is missing.
- `startup-check` fails `sticker_assets` when `require_sticker_candidate_ids` in the replay report names an ID missing from the applied sticker library.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_import_stickers_writes_valid_profile_library \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_startup_check_blocks_missing_sticker_local_path \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_startup_check_blocks_replay_required_sticker_missing_from_library \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failures because startup-check does not validate `local_path` or replay-required IDs yet.

- [x] **Step 3: Implement importer path basis**

In `sticker_assets/importer.py`, compute `local_path` as a relative path from `output.parent` to the source asset file.

- [x] **Step 4: Implement startup checks**

In `startup_gate.py`, load the replay report once, pass it to `_check_sticker_assets`, collect sticker IDs, validate `local_path`, and compare required replay sticker IDs against the library IDs.

- [x] **Step 5: Update docs**

Document that `local_path` is relative to `sticker-library.json`, and that startup-check blocks missing files or missing replay-required IDs.

- [x] **Step 6: Verify**

Run the focused command from Step 2, then:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```
