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

## Testing

Use `pytest` for automated tests. Run the targeted test file for your change
plus any relevant regression tests.

If verification is skipped or blocked, state that explicitly.

For desktop, frontend, or Tauri UI issues, first try to reproduce through the
existing observe/smoke entrypoints instead of asking the user to paste logs.
Prefer CDP, screenshot, DOM-state, or artifact evidence before changing UI code.

For changes touching Supervisor conversation behavior, LLM prompts, capability
contracts, capacity manifests, capacity observations, agent-loop result
projection, or `src/isotope/dev_evals/`, run
`scripts/dev-eval changed_surface --base origin/main --json`
before final reporting. If it returns `eval_required=true`, run the recommended
command, read any generated `.dev-eval-runs/state/dev-evals/reviewer-prompts/*.md`,
and report hard gates, scores, reviewer findings, and follow-up changes. If this
is blocked, report the exact command and output.

## Git Workflow

Use Conventional Commits, such as `docs: polish public project guide` or
`fix(supervisor): handle completed worker state`.

Keep history linear. Prefer rebase or fast-forward updates in your own
branch/worktree; do not rebase, continue, or commit on another Codex session's
ahead branch/worktree unless the user explicitly hands it off after a read-only
status/session audit. Do not create merge commits unless a maintainer explicitly
asks for one. Stage only files related to the current task. Before committing,
inspect the staged diff and run the minimum relevant verification.

**Pre-commit hook active.** `.git/hooks/pre-commit` checks staged `.py` files:
rejects files over 2000 lines; warns at 500 lines. Bypass with `git commit
--no-verify`. The hook uses `.venv/bin/python` when available, or `python3`.

For normal scoped changes, finish with verification, commit, and push.
