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
- Remaining debt: `qq_handlers.py` is a 600+ line module and
  `src/isotope/features/social/` contains 30+ Python files. Before adding more
  QQ commands, split handler groups into a QQ command package, with separate
  runtime, profile/replay, beta-operations, and state/config helper modules.

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
