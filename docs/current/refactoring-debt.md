# Refactoring Debt

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
