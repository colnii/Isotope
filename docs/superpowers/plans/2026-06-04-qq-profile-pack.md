# QQ Profile Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add editable QQ role/sticker profile packs and make beta packs consume them through path-based config.

**Architecture:** Keep profile generation and application in `src/isotope/features/social/profile_pack.py`. `runner.py` only exposes `qq init-profile` and `qq apply-profile`. Generated profiles are ordinary `role-card.json` and `sticker-library.json` files validated by existing `CharacterCard` and `StickerLibrary`; applying a profile updates a beta pack `config.json` to `role_card_path` and `sticker_library_path` while keeping a backup.

**Tech Stack:** Python 3.13, argparse, pathlib, json, pytest, existing social character/sticker contracts.

---

### Task 1: Generate Editable QQ Profile Pack

**Files:**
- Create: `src/isotope/features/social/profile_pack.py`
- Modify: `src/isotope/features/social/runner.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing init-profile test**

Add `test_social_runner_qq_init_profile_writes_editable_role_and_stickers`. It should run:

```python
main([
    "qq", "init-profile",
    "--output-dir", str(profile_dir),
    "--group", "99999",
    "--name", "群聊工程猫",
    "--json",
])
```

Assert `role-card.json`, `sticker-library.json`, and `README.md` exist; `CharacterCard.from_dict(...)` accepts the role; `StickerLibrary.from_dict(...)` accepts the stickers; the returned JSON includes both file paths.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_init_profile_writes_editable_role_and_stickers -q
```

Expected: FAIL because `init-profile` is not registered.

- [x] **Step 3: Implement profile generation**

Create `QQProfilePackConfig`, `QQProfilePackResult`, and `create_qq_profile_pack(...)`. The generator writes a friendly group role card and a non-empty sticker library, validates both with existing parsers, refuses non-empty output without `--force`, and returns JSON-safe paths.

- [x] **Step 4: Wire CLI**

Add:

```text
qq init-profile --output-dir <dir> --group <group_id> --name <role_name> [--force] [--json]
```

- [x] **Step 5: Verify green**

Run the focused test again. Expected: PASS.

### Task 2: Apply Profile to Beta Pack

**Files:**
- Modify: `src/isotope/features/social/profile_pack.py`
- Modify: `src/isotope/features/social/runner.py`
- Modify: `src/isotope/features/social/beta_check.py`
- Test: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Write failing apply-profile test**

Add `test_social_runner_qq_apply_profile_updates_beta_config_and_beta_check`. It should create a beta pack, create a profile pack, run:

```python
main([
    "qq", "apply-profile",
    "--pack-dir", str(beta_dir),
    "--profile-dir", str(profile_dir),
    "--json",
])
```

Assert `config.json` now contains `role_card_path` and `sticker_library_path`, no inline `role_card` or `sticker_library`, a backup file exists, `inspect role`, `inspect stickers`, and `beta-check` all pass with the updated config.

- [x] **Step 2: Verify red**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py::test_social_runner_qq_apply_profile_updates_beta_config_and_beta_check -q
```

Expected: FAIL because `apply-profile` is not registered and `beta-check` only understands inline assets.

- [x] **Step 3: Implement apply-profile**

Add `QQProfileApplyConfig`, `QQProfileApplyResult`, and `apply_qq_profile_pack(...)`. It validates profile files, writes `config.before-profile.json` if absent, removes inline assets, writes relative paths when possible, and returns config/backup/profile paths.

- [x] **Step 4: Update beta-check**

Let `beta-check` validate either inline `role_card` / `sticker_library` or path-based `role_card_path` / `sticker_library_path`, resolving relative paths from the beta pack directory.

- [x] **Step 5: Wire CLI and verify green**

Add:

```text
qq apply-profile --pack-dir <beta_pack_dir> --profile-dir <profile_dir> [--json]
```

Run the focused test again. Expected: PASS.

### Task 3: Docs and Regression

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`
- Modify: `tests/unit/docs/test_qq_group_chatbot_docs.py`

- [x] **Step 1: Add docs assertion**

Require docs to mention `init-profile`, `apply-profile`, `role-card.json`, and `sticker-library.json`.

- [x] **Step 2: Update runbooks**

Document this executable order:

```bash
isotope-social qq init-profile --output-dir .isotope/qq-profile \
  --group <controlled_group_id> --name 群聊工程猫 --json
isotope-social qq apply-profile --pack-dir .isotope/qq-beta \
  --profile-dir .isotope/qq-profile --json
isotope-social qq beta-check --pack-dir .isotope/qq-beta --json
```

- [x] **Step 3: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Operators can generate editable role/sticker files without hand-writing JSON from scratch.
- Applying the profile changes the real beta pack config that `live-run`, `inspect`, and `beta-check` use.
- The profile has non-empty sticker entries and a recognizable group persona, not an empty placeholder.
- All paths and generated files are visible in JSON output so operators know what to edit.
