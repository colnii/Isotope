# Repository Guide

## Project Scope

Isotope is a local-first AI engineering workbench focused on Agent supervision,
Codex session management, controlled worker launch, evidence collection, and
recoverable development workflows.

The main Python package lives under `src/isotope/`; tests live under
`tests/isotope/`. Current product status and longer notes live under `docs/`.
Start with `README.md` for the public overview and `docs/current/status.md` for
the detailed current state.

## Common Commands

Use Python `3.13` or newer.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[test]"
.venv/bin/python -m pytest tests/isotope -q
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

Prefer small, reviewable changes. When adding or changing behavior, update the
relevant CLI/API entry point, tests, and user-facing docs in the same change.

Agent and LLM features should keep the model on the main execution path while
using rules, allowlists, budgets, and workspace boundaries as guardrails. Do not
replace a requested product path with a diagnostic-only or disabled stub unless
the limitation is intentional and documented.

## Testing

Use `pytest` for automated tests. Choose the smallest meaningful verification
scope for the change:

- Documentation-only changes: run `git diff --check` and inspect the diff.
- CLI/API behavior changes: run the targeted test file plus relevant smoke
  command.
- Shared state, recovery, or Supervisor changes: run the relevant regression
  tests under `tests/isotope/`.

If verification is skipped or blocked, state that explicitly.

## Git Workflow

Use Conventional Commits, such as `docs: polish public project guide` or
`fix(supervisor): handle completed worker state`.

Keep history linear. Prefer rebase or fast-forward updates; do not create merge
commits unless a maintainer explicitly asks for one. Stage only files related to
the current task. Before committing, inspect the staged diff and run the minimum
relevant verification.

For normal scoped changes, finish with verification, commit, and push unless the
maintainer asks to pause or leave work uncommitted.
