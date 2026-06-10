# Supervisor Dev Evals

Status: developer-only eval gate
Updated: 2026-06-11

Supervisor dev evals are for Codex and maintainers, not end users.

Before finishing work that touches capability contracts, Supervisor conversation
behavior, LLM prompts, capacity observations, or agent-loop result projection,
run:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.dev_evals.changed_surface --base origin/main --json
```

If the result has `eval_required=true`, run the returned
`recommended_command`. Token cost is not a valid skip reason.

If live provider or network configuration is missing, report the blocker and run
the deterministic fallback checks. Do not claim the live eval passed.

After a required suite runs, read the generated reviewer prompt and feed it back
to Codex before claiming the development task is complete. The reviewer prompt
must be grounded in the current diff, capacity trace, hard gates, and scores.
