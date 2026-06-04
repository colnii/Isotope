# QQ Social CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the QQ social runtime through `isotope-social qq` commands for run-once, dry-run, pause/resume, inspect, health, and audit-log export.

**Architecture:** Follow existing CLI style: `pyproject.toml` registers `isotope-social = isotope.features.social.runner:main`, and `apps/cli/isotope_social.py` stays a thin forwarding entry. The runner loads a JSON config, persists pause/audit state under `--state-root`, drives the existing `SocialRuntime` with `FakeOneBotClient` + `OneBotAdapter` for one-event local verification, and leaves real OneBot network transport for the next phase.

**Tech Stack:** Python 3.13, pytest, argparse, JSON files, existing social runtime and QQ adapter.

---

## Reuse Audit

- Reuse `SocialRuntime`, `SocialRuntimeConfig`, `SocialOperationsController`, and `SocialAuditLog`.
- Reuse `OneBotAdapter` and `FakeOneBotClient` for one-event local CLI verification.
- Reuse `CharacterCard.from_dict` and `StickerLibrary.from_dict`; add runner-local lorebook loader rather than changing core.
- Reuse existing `[project.scripts]` pattern and thin `apps/cli/*` entries.
- Do not introduce NapCat HTTP/WebSocket networking in this phase.
- Do not add new dependencies.

## File Structure

- Create `src/isotope/features/social/runner.py`: argparse CLI, config loading, state persistence, command handlers.
- Create `apps/cli/isotope_social.py`: thin script entry.
- Modify `pyproject.toml`: add `isotope-social` script.
- Modify `apps/cli/README.md`: list the new entry.
- Modify `docs/current/qq-group-chatbot-operations.md`: remove "intended CLI" wording for implemented commands.
- Create `tests/unit/features/social/test_social_runner.py`: command tests.

## Task 1: CLI Tests

**Files:**
- Create: `tests/unit/features/social/test_social_runner.py`

- [ ] **Step 1: Write failing tests**

Create tests proving:

- `qq dry-run` processes one event JSON, records a decision log, and sends nothing;
- `qq run --send` processes one event JSON, records decision and send logs, and returns sent feedback;
- `qq pause` persists paused group state and `qq run --send` then returns policy `group_paused`;
- `qq resume` unpauses the group;
- `qq inspect role` and `qq inspect stickers` return useful JSON;
- `qq health` returns paused groups and audit counts;
- `qq export-log` writes group audit entries to a JSON file.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: FAIL because `isotope.features.social.runner` does not exist.

## Task 2: Runner Implementation

**Files:**
- Create: `src/isotope/features/social/runner.py`
- Modify: `pyproject.toml`
- Create: `apps/cli/isotope_social.py`
- Modify: `apps/cli/README.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Implement CLI runner**

Commands:

- `qq dry-run --config-json <path> --event-json <path> --state-root <dir> --json`
- `qq run --config-json <path> --event-json <path> --state-root <dir> --send --json`
- `qq pause --config-json <path> --state-root <dir> --group <id> --operator <id> --json`
- `qq resume --config-json <path> --state-root <dir> --group <id> --operator <id> --json`
- `qq inspect role|lorebook|stickers --config-json <path> --json`
- `qq health --config-json <path> --state-root <dir> --json`
- `qq export-log --state-root <dir> --group <id> --output <path> --json`

JSON config supports:

- `bot_user_id`
- `dry_run`
- `group_policy`
- `role_card` or `role_card_path`
- `lorebook` or `lorebook_path`
- `sticker_library` or `sticker_library_path`

- [ ] **Step 2: Run CLI tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

## Task 3: Regression And Product Acceptance

- [ ] **Step 1: Run CLI tests**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py -q
```

Expected: PASS.

- [ ] **Step 2: Run social and QQ regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q
```

Expected: all tests pass, with real QQ smoke skipped unless enabled.

- [ ] **Step 3: Run shared supervisor regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/integration/supervisor/test_supervisor_desktop_chat.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run diff hygiene**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Product checklist**

Confirm from tests and code:

- dry-run is the default and sends nothing;
- sending requires `--send`;
- pause/resume persists under `--state-root`;
- inspect and health are understandable without reading source;
- export-log gives operators a file they can attach to beta failure reports.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-06-04-qq-social-cli.md src/isotope/features/social/runner.py apps/cli/isotope_social.py pyproject.toml apps/cli/README.md docs/current/qq-group-chatbot-operations.md tests/unit/features/social/test_social_runner.py
git commit -m "feat(social): add qq operations cli"
```
