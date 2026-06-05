# Refactoring Debt

## Social QQ CLI Handler Split

- Addressed first split on 2026-06-04: QQ parser registration and command
  dispatch moved from `src/isotope/features/social/runner.py` into
  `src/isotope/features/social/qq_runner.py`, and a structure regression keeps
  `runner.py` below 700 lines.
- Addressed second split on 2026-06-04: QQ command handlers, state loading,
  config loading, runtime construction, and command-specific helpers moved into
  `src/isotope/features/social/qq_handlers.py`. `runner.py` is now a thin CLI
  entry point kept below 120 lines by a structure regression.
- Addressed third split on 2026-06-04: QQ state/config helpers moved into
  `src/isotope/features/social/qq_state_config.py`; `run`, `live-run`, replay
  execution, and runtime construction moved into
  `src/isotope/features/social/qq_runtime_commands.py`. A structure regression
  keeps `qq_handlers.py` below 350 lines and keeps WebSocket transport out of
  that module.
- Addressed fourth split on 2026-06-04: beta/report commands moved into
  `src/isotope/features/social/qq_beta_commands.py`, profile commands moved
  into `src/isotope/features/social/qq_profile_commands.py`, replay-template
  init moved into `src/isotope/features/social/qq_replay_commands.py`, and
  pause/inspect/health/export-log moved into
  `src/isotope/features/social/qq_operations_commands.py`. `qq_handlers.py` is
  now a dispatch table kept below 120 lines by a structure regression.
- Remaining debt: `src/isotope/features/social/` contains 30+ Python files. If
  more QQ-specific modules are added, consider moving the QQ command, runtime,
  state/config, and adapter-facing glue modules into a focused `social/qq/`
  subpackage instead of continuing to grow the top-level social package.
- Addressed test split on 2026-06-06: the 2953-line
  `tests/unit/features/social/test_social_runner.py` regression suite was split
  into focused runner, profile/startup, and replay test files. The pre-commit
  size guard no longer needs a social runner exception.
- Remaining debt: keep future QQ CLI tests near the workflow they cover instead
  of growing one broad runner test file again.

## Supervisor Web Handler

- Addressed first split on 2026-06-04: dashboard payload helpers, desktop route
  parsing, desktop screen artifact content, goal plan candidate writing, and
  daemon/watcher service actions now live under
  `src/isotope/features/supervisor/web/routes/`. The web package also exports
  public entry points through a normal package `__init__`, so route modules can
  be imported directly.
- Remaining debt: `src/isotope/features/supervisor/web/_impl.py` is still a
  700+ line `BaseHTTPRequestHandler` wrapper. Keep future endpoint work in
  `web/routes/` first; if handler methods continue growing, split desktop chat
  streaming, approval resolution, decision answers, and managed-command POST
  handlers into route objects or mixins with explicit handler I/O boundaries.

## Supervisor CLI Parser And Flow Projection

- New debt recorded on 2026-06-05: Codex session adoption added a minimal
  parser branch in `src/isotope/features/supervisor/commands/parser/__init__.py`
  and a minimal managed-session projection branch in
  `src/isotope/features/supervisor/flow/_flow_impl.py`. Both files were already
  over the comfortable size threshold, and the pre-commit hook now warns for
  both.
- Remaining debt: move lifecycle command parser registration for `launch`,
  `resume`, `adopt`, `send`, and `archive` into a focused parser module; move
  managed-session projection for `process`, `tmux`, and `codex_session`
  backends into a focused flow projection module. Keep future session adoption
  behavior in smaller modules first instead of growing these two files.

## Supervisor Capability Catalog And Dispatcher

- New debt recorded on 2026-06-05: description-driven Codex session resume added
  one operation branch in `src/isotope/capabilities/supervisor.py` and one
  metadata branch in `src/isotope/capabilities/catalog.py`. The matcher itself
  lives in a focused registry module, but these two capability entry files were
  already above the comfortable size threshold.
- Remaining debt: split supervisor Codex operation dispatch into focused
  operation modules, and move capability schema construction for supervisor
  tools out of the monolithic catalog once the next supervisor capability
  change needs more than a small enum/input addition.
