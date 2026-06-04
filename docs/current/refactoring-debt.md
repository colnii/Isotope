# Refactoring Debt

## Social QQ CLI Runner

- Added on 2026-06-04: `src/isotope/features/social/runner.py` is now a
  800+ line CLI dispatcher covering runtime commands, beta pack generation,
  profile application, replay, startup checks, dry-run review reports,
  beta day reports, regression intake, inspection, health, and log export. Keep
  domain behavior in focused modules such as `beta_pack.py`, `beta_check.py`,
  `profile_pack.py`, `replay.py`, `startup_gate.py`, `dry_run_review.py`,
  `beta_day_report.py`, and `regression_intake.py`. If more QQ commands are
  added, split parser/handler registration into a QQ command package instead of
  continuing to grow `runner.py`.

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
