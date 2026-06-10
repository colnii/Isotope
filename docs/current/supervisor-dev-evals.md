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

If the result has `eval_required=true`, run the returned `recommended_command`
as the default smoke gate. Use the returned `full_command` only when you need
the explicit full suite. Token cost is not a valid skip reason for the default
gate.

If live provider or network configuration is missing, report the blocker and run
the deterministic fallback checks. Do not claim the live eval passed.

After a required suite runs, read the generated reviewer prompt and feed it back
to Codex before claiming the development task is complete. `reviewer_status=
prompt_generated` only means the prompt artifact exists; it is not a completed
reviewer verdict. The reviewer prompt must be grounded in the current diff,
capacity trace, hard gates, and scores.
