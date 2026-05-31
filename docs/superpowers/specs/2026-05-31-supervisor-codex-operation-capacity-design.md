# Supervisor Codex Operation Capacity Design

## Goal

Make Supervisor's Codex-facing operations enter the same capacity and agent-loop path, so the loop has one main action shape instead of mixing direct `launch_session` / `resume_session` / `request_context` execution with `call_capacity`.

## Key Decision

Register one unified capability:

`supervisor.codex_operation`

The capability accepts an `operation` enum and dispatches to existing Supervisor operations internally. This reduces LLM context noise without turning Codex into an unrestricted command runner.

Initial operations:

- `request_context`
- `worker_review`
- `integration_review`
- `launch_worker`
- `resume_worker`

## Architecture

Supervisor remains responsible for state scanning, budgets, cooldowns, approval records, managed worker registry, and dashboard read models. Agent loop becomes the execution lane for selected work: one tick selects `call_capability`, and the selected capability is `supervisor.codex_operation` for Codex/Supervisor operations.

Existing direct Supervisor actions stay as compatibility wrappers during the migration. They should be normalized into the new capacity path where practical, rather than deleted in the first pass.

## Data Flow

```text
Supervisor loop payload
  -> LLM decision / existing direct action
  -> codex operation adapter
  -> agent loop tick
  -> call_capability(supervisor.codex_operation)
  -> existing Supervisor implementation
  -> low-sensitive result summary
  -> capacity memory / dashboard summary
```

## Safety Boundaries

- No arbitrary Codex shell command execution.
- `launch_worker` and `resume_worker` reuse existing managed-worker helpers and their budgets/cooldowns.
- Read-only operations keep existing low-sensitive output contracts.
- Agent-loop payloads expose summaries and artifact refs, not raw prompts or transcripts.
- Old action names remain accepted until tests prove the new path covers them.

## Success Criteria

- `CapabilityRunner` lists and plans `supervisor.codex_operation`.
- `request_context`, `worker_review`, and `integration_review` can run through the unified capability.
- Supervisor action execution can route a legacy direct Codex operation through an agent-loop `call_capability` step.
- Tests prove the routed result contains `agent_loop_summary` and a `capacity_id` of `supervisor.codex_operation`.
