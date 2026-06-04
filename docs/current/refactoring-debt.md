# Refactoring Debt

## Supervisor Web Handler

- `src/isotope/features/supervisor/web/_impl.py` is above 1000 lines after adding
  the desktop screen artifact content endpoint. Split the HTTP handler into route
  modules for dashboard, desktop chat, desktop artifacts, approvals, goals, and
  service actions before adding more web endpoints.
