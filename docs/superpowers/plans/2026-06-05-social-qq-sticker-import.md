# QQ Sticker Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a QQ sticker asset importer that generates a validated `sticker-library.json` from a local manifest.

**Architecture:** Put import logic in `src/isotope/features/social/sticker_assets/` so the already-large social root directory does not grow further. Keep CLI registration in `qq_runner.py`, command handling in `qq_profile_commands.py`, and use the existing `StickerLibrary.from_dict` validation as the final contract check.

**Tech Stack:** Python 3.13, pytest, JSON manifests, existing `isotope-social qq` CLI.

---

### Task 1: Import Sticker Manifest

**Files:**
- Create: `src/isotope/features/social/sticker_assets/__init__.py`
- Create: `src/isotope/features/social/sticker_assets/importer.py`
- Modify: `src/isotope/features/social/qq_runner.py`
- Modify: `src/isotope/features/social/qq_profile_commands.py`
- Modify: `src/isotope/features/social/qq_handlers.py`
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [x] **Step 1: Write failing CLI tests**

Add tests that call:

```bash
isotope-social qq import-stickers \
  --source-dir <assets> \
  --output <profile>/sticker-library.json \
  --group 99999 \
  --pack-id engineering \
  --json
```

The passing test must assert the output library validates with
`StickerLibrary.from_dict`, includes `ship-it`, writes `local_path`, and can be
used by `apply-profile` plus `beta-check`. The failing test must assert a
missing file returns exit code 2 and does not write the output file.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_import_stickers_writes_valid_profile_library \
  tests/unit/features/social/test_social_runner.py::test_social_runner_qq_import_stickers_rejects_missing_files \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
```

Expected: failures because `import-stickers` is not registered and docs do not
mention the new command.

- [x] **Step 3: Implement importer**

Create a config/result dataclass pair and a `import_qq_sticker_assets` function
that reads `manifest.json`, validates file paths, rejects duplicates, writes a
normal `StickerLibrary` payload, and returns `entry_count` plus `sticker_ids`.

- [x] **Step 4: Wire CLI**

Register `qq import-stickers`, add a handler, and expose JSON output with
`status`, `command`, `output`, `entry_count`, and `sticker_ids`.

- [x] **Step 5: Update docs**

Document `manifest.json`, `file`, `media_ref`, `local_path`, and the command in
both QQ runbooks. Extend the docs coverage test with these strings.

- [x] **Step 6: Verify**

Run the focused command from Step 2, then:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/unit/features/social \
  tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```
