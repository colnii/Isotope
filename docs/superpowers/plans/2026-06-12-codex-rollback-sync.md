# Codex Rollback Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agent Group Chat follow the current effective Codex thread after manual rollback while keeping raw JSONL history inspectable.

**Architecture:** Project `thread_rolled_back` as a transcript event, track rollback cursor state in member transcript policy, mark obsolete imported member observations as superseded, and filter superseded messages plus rollback metadata from default chat listing.

**Tech Stack:** Python 3.13, pytest, existing Codex transcript reader, existing workspace store/importer contracts.

---

### Task 1: Transcript Rollback Projection

**Files:**
- Modify: `src/isotope/integrations/codex/transcript.py`
- Test: `tests/unit/integrations/codex/test_codex_transcript.py`

- [ ] **Step 1: Write failing test**

Add a test that writes a `thread_rolled_back` event and asserts that `read_codex_transcript_page()` returns an event with `kind == "rollback"`, `title == "thread rolled back"`, `num_turns == 2`, and a terminal event for the rollback.

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest -q tests/unit/integrations/codex/test_codex_transcript.py::test_transcript_reader_projects_thread_rollback_event
```

Expected: fail because rollback is still projected as generic status and is absent from terminal events.

- [ ] **Step 3: Implement minimal projection**

Handle `event_msg` payload type `thread_rolled_back` before generic `event_msg`, with a small helper for `num_turns` and terminal summary text.

- [ ] **Step 4: Run transcript test**

Run the same pytest command and expect it to pass.

### Task 2: Superseded Message Filtering

**Files:**
- Modify: `src/isotope/features/supervisor/agent_group/workspace/store.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_store.py`

- [ ] **Step 1: Write failing test**

Add a test that publishes a member observation, then publishes a `status` message with payload `{"status_kind": "codex_thread_rolled_back", "superseded_message_ids": [old_id]}`. Assert `list_messages()` hides both the old observation and rollback status by default, and returns both when called with `include_superseded=True`.

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest -q tests/unit/features/supervisor/agent_group/workspace/test_store.py::test_store_hides_messages_superseded_by_codex_rollback_by_default
```

Expected: fail because `list_messages()` has no `include_superseded` argument and does not filter rollback supersession status payloads.

- [ ] **Step 3: Implement filtering**

Add an optional keyword-only `include_superseded: bool = False` to `list_messages()`. Build a set of superseded message ids from status messages with `status_kind == "codex_thread_rolled_back"` and filter those ids plus the rollback status messages unless `include_superseded` is true.

- [ ] **Step 4: Run store test**

Run the same pytest command and expect it to pass.

### Task 3: Importer Rollback Awareness

**Files:**
- Modify: `src/isotope/features/supervisor/agent_group/workspace/importer.py`
- Test: `tests/unit/features/supervisor/agent_group/workspace/test_reply_importer_rollback.py`

- [ ] **Step 1: Write failing tests**

Add one test for `old candidate -> rollback -> new candidate` that asserts only the new candidate appears in default chat messages. Add another test for rollback-only import that asserts a `thread_rolled_back` import status and cursor advancement.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest -q tests/unit/features/supervisor/agent_group/workspace/test_reply_importer_rollback.py::test_import_channel_member_replies_hides_observations_superseded_by_codex_rollback tests/unit/features/supervisor/agent_group/workspace/test_reply_importer_rollback.py::test_import_channel_member_replies_records_rollback_without_new_candidate
```

Expected: fail because rollback events do not affect imported observations or import status.

- [ ] **Step 3: Implement import logic**

Detect the latest rollback event in the imported page, track `last_rollback_event_index`, publish one rollback status message containing superseded message ids for that member/session, and process assistant candidate terminal events only after that rollback event index.

- [ ] **Step 4: Run importer tests**

Run the same pytest command and expect it to pass.

### Task 4: Regression Verification

**Files:**
- No production changes expected.

- [ ] **Step 1: Run targeted suite**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest -q tests/unit/integrations/codex/test_codex_transcript.py tests/unit/features/supervisor/agent_group/workspace/test_reply_importer.py tests/unit/features/supervisor/agent_group/workspace/test_reply_importer_candidates.py tests/unit/features/supervisor/agent_group/workspace/test_store.py
```

Expected: all tests pass.

- [ ] **Step 2: Run changed-surface gate**

Run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

If `eval_required` is true, run the recommended smoke command and inspect generated reviewer prompts before final reporting.
