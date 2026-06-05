# Adopt Existing Codex Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `isotope-supervisor adopt --session-id <id>` so existing user-started Codex sessions can become managed lanes and later be continued through managed resume.

**Architecture:** Reuse the existing managed registry. Add a small lifecycle helper that resolves a local Codex session id to its rollout metadata, writes a `ManagedCodexRecord` with `backend="codex_session"`, and leaves active continuation to the existing `resume` command.

**Tech Stack:** Python 3.13, pytest, existing Isotope Supervisor registry and Codex session scan helpers.

---

### Task 1: Add Registry Adoption Helper

**Files:**
- Modify: `src/isotope/features/supervisor/registry/lifecycle.py`
- Modify: `src/isotope/features/supervisor/registry/__init__.py`
- Test: `tests/integration/codex/scan/test_adopt_codex_session.py`

- [ ] **Step 1: Write the failing test**

Add a test that creates a local rollout JSONL with a matching session id, calls
`adopt_codex_session(...)`, and asserts the stored record has:

```python
assert record.backend == "codex_session"
assert record.resume_session_id == "019e9830-8a72-7ff1-8b2e-310b9d66372b"
assert record.pid == 0
```

- [ ] **Step 2: Verify RED**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/codex/scan/test_adopt_codex_session.py::test_adopt_codex_session_records_resume_identity -q
```

Expected: fail because `adopt_codex_session` is not implemented.

- [ ] **Step 3: Write minimal implementation**

Add `adopt_codex_session(...)` to `registry/lifecycle.py`. It should:

- validate `name`, `session_id`, and prompt;
- resolve session metadata from local Codex session files;
- infer cwd if omitted;
- append a `ManagedCodexRecord`;
- set `backend="codex_session"` and `resume_session_id=session_id`.

- [ ] **Step 4: Run test to verify it passes**

Run the same targeted test and expect pass.

### Task 2: Wire CLI Adopt Mode

**Files:**
- Modify: `src/isotope/features/supervisor/commands/parser/__init__.py`
- Modify: `src/isotope/features/supervisor/commands/dispatch.py`
- Test: `tests/integration/codex/scan/test_adopt_codex_session.py`

- [ ] **Step 1: Write failing CLI test**

Add a test that invokes the parser/dispatch path for:

```bash
adopt --name research --session-id 019e9830-8a72-7ff1-8b2e-310b9d66372b --json
```

Expected output includes `"backend": "codex_session"`.

- [ ] **Step 2: Verify RED**

Run the new test and expect parser failure because `--session-id` is not
accepted by `adopt`.

- [ ] **Step 3: Write minimal implementation**

Update adopt parser so exactly one of `--tmux-session` or `--session-id` is
required. In dispatch, route `--session-id` to `adopt_codex_session(...)` and
keep tmux behavior unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run the new CLI test and expect pass.

### Task 3: Project Adopted Sessions in Scan

**Files:**
- Modify: `src/isotope/features/supervisor/flow/_flow_impl.py`
- Create: `src/isotope/features/supervisor/flow/adopted_sessions.py`
- Test: `tests/integration/codex/scan/test_adopt_codex_session.py`

- [ ] **Step 1: Write failing scan test**

Add a managed registry record with `backend="codex_session"` and an existing
`resume_session_id`. Scan should return a managed session with:

```python
assert session.managed is True
assert session.managed_backend == "codex_session"
assert session.managed_resume_session_id == session_id
assert session.status in {"working", "stale", "needs_user", "exited"}
```

- [ ] **Step 2: Verify RED**

Run the targeted test. Expected failure should show current scan treats the
record as a generic process with pid `0`.

- [ ] **Step 3: Write minimal implementation**

Teach `_managed_summary(...)` that `backend="codex_session"` is a registry
adoption marker. It should not check pid `0`; it should derive status from the
matching local Codex session summary when possible, otherwise mark the lane
`stale` with evidence that it is an adopted session record.

- [ ] **Step 4: Run test to verify it passes**

Run the targeted scan test and expect pass.

### Task 4: Full Verification and Commit

**Files:**
- All modified files above

- [ ] **Step 1: Run focused regression**

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/integration/codex/scan/test_adopt_codex_session.py tests/integration/codex/scan/test_scan.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Inspect diff**

```bash
git diff -- src/isotope/features/supervisor/registry/lifecycle.py src/isotope/features/supervisor/registry/__init__.py src/isotope/features/supervisor/commands/parser/__init__.py src/isotope/features/supervisor/commands/dispatch.py src/isotope/features/supervisor/flow/_flow_impl.py src/isotope/features/supervisor/flow/adopted_sessions.py tests/integration/codex/scan/test_adopt_codex_session.py
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-05-adopt-codex-session-design.md docs/superpowers/plans/2026-06-05-adopt-codex-session.md src/isotope/features/supervisor/registry/lifecycle.py src/isotope/features/supervisor/registry/__init__.py src/isotope/features/supervisor/commands/parser/__init__.py src/isotope/features/supervisor/commands/dispatch.py src/isotope/features/supervisor/flow/_flow_impl.py src/isotope/features/supervisor/flow/adopted_sessions.py tests/integration/codex/scan/test_adopt_codex_session.py
git commit -m "feat(supervisor): adopt existing codex sessions"
```
