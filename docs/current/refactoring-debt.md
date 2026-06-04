# Refactoring Debt

## Social QQ CLI Handler Split

- Addressed first split on 2026-06-04: QQ parser registration and command
  dispatch moved from `src/isotope/features/social/runner.py` into
  `src/isotope/features/social/qq_runner.py`, and a structure regression keeps
  `runner.py` below 700 lines.
- Remaining debt: QQ handler implementations still live in `runner.py` with
  state loading, config loading, runtime construction, and command handlers in
  one file. Move those handlers and shared helpers behind an explicit QQ runtime
  command module before adding more QQ commands.

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
