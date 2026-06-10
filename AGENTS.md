# Repository Guide

## Project Scope

Isotope is a local-first AI engineering workbench focused on Agent supervision,
Codex session management, controlled worker launch, evidence collection, and
recoverable development workflows.

The main Python package lives under `src/isotope/`; tests live under `tests/unit/`,
`tests/integration/`, `tests/e2e/`, `tests/smoke/`, and `tests/fixtures/`.
Start with `README.md` for the public overview.

## Common Commands

Use Python `3.13` or newer.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/ -q
.venv/bin/isotope-supervisor scan --limit 5
.venv/bin/isotope-supervisor web --host 127.0.0.1 --port 8765
```

For source-tree execution without installing scripts, use `PYTHONPATH=src`.

## Code Style

Python code uses 4-space indentation, `snake_case` modules/functions, and
focused files with clear responsibilities. Test files and test functions use the
`test_*` naming pattern. Keep public interfaces small and prefer explicit data
objects over loosely shaped dictionaries when behavior is shared.

New dependencies are acceptable when they reduce maintenance cost; document why
they are needed and avoid duplicating mature libraries without a clear reason.

## Development Rules

**Ship working features.** Make changes at the scale the task requires — if the
task needs a big change, make a big change. Do not build diagnostic-only stubs,
preflight-only entry points, or "not enabled" paths that mask missing functionality.
A feature either works end-to-end, or it doesn't exist yet.

When adding or changing behavior, update the relevant CLI/API entry point,
tests, and user-facing docs in the same change.

Agent and LLM features should keep the model on the main execution path while
using rules, allowlists, budgets, and workspace boundaries as guardrails. Do not
replace a requested product path with a diagnostic-only or disabled stub.

For parallel Codex work, an existing ahead branch or worktree is treated as an
occupied development lane, not reusable scratch space. Do not continue another
Codex session's branch, rebase it, or add commits on top of it unless the user
explicitly asks you to take over that exact branch/worktree. If takeover is
requested, first perform a read-only audit of the branch owner/session state,
worktree status, and uncommitted changes, then state the risk before editing.
Otherwise, start a fresh topic branch/worktree from the intended base and treat
the other lane's unmerged work only as reference.

## Testing

Use `pytest` for automated tests. Run the targeted test file for your change
plus any relevant regression tests.

If verification is skipped or blocked, state that explicitly.

For desktop, frontend, or Tauri UI issues, first try to reproduce through the
existing observe/smoke entrypoints instead of asking the user to paste logs.
Prefer CDP, screenshot, DOM-state, or artifact evidence before changing UI code.

## Git Workflow

Use Conventional Commits, such as `docs: polish public project guide` or
`fix(supervisor): handle completed worker state`.

Keep history linear. Prefer rebase or fast-forward updates; do not create merge
commits unless a maintainer explicitly asks for one. Stage only files related to
the current task. Before committing, inspect the staged diff and run the minimum
relevant verification.

**Pre-commit hook active.** `.git/hooks/pre-commit` checks staged `.py` files:
rejects files over 2000 lines; warns at 500 lines. Bypass with `git commit
--no-verify`. The hook uses `.venv/bin/python` when available, or `python3`.

For normal scoped changes, finish with verification, commit, and push.
