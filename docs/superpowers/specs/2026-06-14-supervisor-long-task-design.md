# Supervisor Long Task Design

Date: 2026-06-14

## Goal

Let Isotope run long-horizon Supervisor work through one durable backend
contract, with CLI commands as the first verification surface and a thin desktop
adapter for product visibility and control.

The first version should let a user start a long task, observe progress, advance
bounded ticks, pause, resume, stop, and recover after a process restart without
repeating completed steps.

## Background

Current Isotope already has most of the right primitives:

- `run_agent_loop_provider_planner_tick(...)` advances one model-selected
  planner step through existing agent-loop contracts.
- `run_agent_loop_until_stop(...)` runs a finite loop with a max-tick budget.
- `build_agent_loop_tick_policy(...)` centralizes stop reasons such as approval,
  completion, user pause, and budget exhaustion.
- `FileEventStore` and `FileCheckpointStore` provide run event history and
  restart boundaries.
- Supervisor capability execution already routes through `CapabilityRunner`
  and agent-loop `call_capability`; long tasks must reuse that path.
- Desktop chat and Supervisor web routes already expose streamed status and
  approval-style user controls.

External practice points in the same direction: durable long-running agents need
discrete steps, a queue/control surface, checkpoint or event-sourced recovery,
human-in-the-loop interruption, tracing, and progress streaming. This design
uses those as constraints but keeps Isotope's local-first runtime as the source
of truth.

References:

- OpenAI reasoning guide:
  <https://developers.openai.com/api/docs/guides/reasoning>
- Codex slash commands:
  <https://developers.openai.com/codex/cli/slash-commands>
- OpenAI Agents SDK running agents:
  <https://openai.github.io/openai-agents-python/running_agents/>
- LangGraph runtime design:
  <https://www.langchain.com/blog/building-langgraph>
- Temporal durable AI agents:
  <https://temporal.io/blog/of-course-you-can-build-dynamic-ai-agents-with-temporal>

## Scope

Build the backend contract first, then expose it through:

1. CLI commands for start, status, run ticks, pause, resume, and stop.
2. A desktop thin adapter that can create a long task from chat and show the
   same status/control state.

The first implementation can be pull-driven: `long-task run --max-ticks N`
advances work. A daemon or scheduler can be added later on top of the same
contract.

## Non-Goals

- Do not build a full workflow engine.
- Do not bypass the existing agent loop or capability runner.
- Do not make desktop chat hold one HTTP request open for the whole task.
- Do not hard-kill a tool in the middle of a filesystem or terminal action in
  the first version. Stop and pause take effect at tick boundaries.
- Do not expose raw prompts, raw provider responses, raw artifact content, API
  keys, or hidden capability inputs in task projections.
- Do not solve multi-worker merge/cleanup policy here; use existing Supervisor
  lifecycle and capability contracts when a tick chooses those actions.

## Reuse Audit

Reuse:

- `src/isotope/agents/loop/runner.py` for finite tick loops.
- `src/isotope/agents/loop/tick.py` for one-step execution boundaries.
- `src/isotope/agents/loop/provider_planner.py` for model-selected planner
  ticks.
- `src/isotope/agents/loop/control.py` for status, pause, approval, completion,
  and budget stop decisions.
- `src/isotope/runtime/in_process/agent_loop.py` as the runtime facade.
- `src/isotope/platform/state/event_store.py` and
  `src/isotope/platform/state/checkpoint_store.py` for event replay and restart.
- Supervisor command and web routing patterns, but keep new logic in a focused
  `supervisor/long_task/` package.
- Existing desktop SSE/read-model projection style for status and controls.

Do not reuse as-is:

- A single long desktop chat request as the execution container. It is a UI
  transport, not a durable execution boundary.
- Prompt-only instructions that ask the model to continue forever. Continuation
  must be controlled by the app-owned tick policy.
- Ad hoc background subprocesses without a task record, heartbeat, checkpoint
  basis, and stop/pause control.

Directory note:

- `src/isotope/features/supervisor/` and several existing Supervisor files are
  already large. New code should live in `src/isotope/features/supervisor/long_task/`
  and focused tests rather than appending to existing large modules.

## Core Contract

### LongTaskRecord

`LongTaskRecord` is the index and control surface. It is not the execution
truth. Execution truth remains the run event log plus checkpoints.

Fields:

- `task_id`: stable long-task id.
- `run_id`: Isotope run id created for the task.
- `session_id`: session id for the run.
- `goal`: user goal.
- `status`: `queued`, `running`, `paused`, `stopping`, `stopped`,
  `completed`, `failed`, or `blocked`.
- `created_at`: creation timestamp.
- `updated_at`: last task-record update.
- `last_event_id`: latest projected run event seen by the task projection.
- `last_checkpoint_event_id`: checkpoint basis event when known.
- `heartbeat`: optional last runner heartbeat.
- `control_state`: current user control request.
- `summary`: low-sensitive progress summary.

### Control State

Control state is explicit and boundary-based:

- `run`: task may advance at the next tick.
- `pause`: runner stops before starting another tick.
- `resume`: clears pause and allows future ticks.
- `stop`: runner stops before another tick and marks the task stopped.

Pause and stop do not interrupt an already executing tool call in the first
version. They take effect before the next planner tick.

### Tick Result

Each long-task tick records:

- `task_id`
- `run_id`
- `tick_index`
- `before_status`
- `after_status`
- `before_policy`
- `planner_summary`
- `step_summary`
- `after_policy`
- `stop_reason`
- `basis_event_id`
- `checkpoint_event_id` when available

The public projection must include summaries and artifact refs only. Raw content
continues to use existing artifact inspect and expansion paths.

## Storage

Add a focused file-backed store under the Supervisor state root:

```text
long_tasks/
  tasks.jsonl
  controls.jsonl
```

`tasks.jsonl` is an append-only task-record ledger. `controls.jsonl` records
pause, resume, and stop requests. The read model folds both ledgers with current
run state rebuilt from `FileEventStore` / `FileCheckpointStore`.

This keeps task metadata durable without duplicating run execution state.

## CLI Surface

Add a `long-task` command group:

```bash
isotope-supervisor long-task start --goal "..."
isotope-supervisor long-task status --task-id <task_id>
isotope-supervisor long-task run --task-id <task_id> --max-ticks 5
isotope-supervisor long-task pause --task-id <task_id>
isotope-supervisor long-task resume --task-id <task_id>
isotope-supervisor long-task stop --task-id <task_id>
isotope-supervisor long-task list
```

Behavior:

- `start` creates a session, run, and task record. It does not need to execute
  a tick immediately.
- `run` advances up to `max_ticks`, stops early on approval, pause, stop,
  completion, failure, or budget exhaustion.
- `status` and `list` are read-only and never import, drain, or mutate hidden
  state.
- `pause`, `resume`, and `stop` append control records and update the folded
  projection.

The first version can use deterministic fixture providers in tests. Live LLM
provider wiring should follow existing provider resolution patterns rather than
hardcoding a provider in the long-task store.

## Desktop Thin Adapter

Desktop chat should be able to create a long task when the model or user chooses
the long-task path. The first desktop slice only needs:

- Return `task_id` immediately after creation.
- Show task status, current phase, last tick summary, and stop reason.
- Provide pause, resume, and stop controls that call the same backend contract.
- Stream or poll projection updates using existing desktop/SSE patterns.

The desktop adapter must not define a second task state machine. It reads the
same folded projection used by the CLI.

## Data Flow

Start:

```text
CLI or desktop
  -> long-task start(goal)
  -> create session/run through runtime facade
  -> append LongTaskRecord(status=queued)
  -> return task_id/run_id
```

Run:

```text
long-task run(task_id, max_ticks)
  -> fold task projection
  -> stop if control_state is pause/stop or run is terminal
  -> for each allowed tick:
       read tick policy
       ask provider planner for one symbolic decision
       execute through existing agent loop/capability contracts
       append/update task summary
       save or observe checkpoint basis
       stop on approval/completion/failure/pause/stop/budget
```

Recover:

```text
new process
  -> fold long_tasks/*.jsonl
  -> rebuild run state from events/checkpoints
  -> compare last_event_id with current run last_event_id
  -> continue from current projected phase
```

## Error Handling

- Unknown task id returns a validation/not-found error with the missing id.
- A task whose run is already terminal cannot be resumed into execution.
- Stale task records are repaired by reading current run state; run state wins.
- Malformed task/control ledgers fail with explicit file and line diagnostics.
- Provider or planner errors mark the attempted tick failed and leave the task
  resumable only if the run state is still non-terminal.
- Approval waits produce `blocked` or `paused` style projections with
  `requires_human=true`.

## Testing

Use TDD for implementation. First failing tests should cover:

- `start` creates a task record, session, and run without executing a tick.
- `status` folds task metadata and current run state without side effects.
- `run --max-ticks N` advances bounded ticks and records a low-sensitive tick
  summary.
- `pause` prevents another tick from starting.
- `resume` allows ticks after pause.
- `stop` prevents future ticks and marks the projection stopped.
- Recovery from a new runtime instance continues from event/checkpoint state
  and does not repeat completed planner decisions.
- Public projections reject raw prompt/provider/artifact content.
- Desktop adapter reads the same projection as CLI.

Targeted commands will be chosen during implementation, but likely include:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/long_task \
  tests/integration/supervisor/test_supervisor_long_task_cli.py -q
```

Because this touches Supervisor conversation behavior, capability execution, and
agent-loop projections, run before final reporting:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

If it reports `eval_required=true`, run the recommended smoke command and report
the reviewer prompts, hard gates, scores, findings, and follow-up changes.

## Rollout Slices

1. Backend store and projection with unit tests.
2. CLI start/status/list/pause/resume/stop with integration tests.
3. CLI bounded `run --max-ticks` using deterministic provider tests.
4. Restart/recovery regression.
5. Desktop thin adapter and read/control endpoints.
6. Live-provider smoke only after deterministic contract tests pass.

## Risks

- Duplicate state: avoid by making run events/checkpoints authoritative and task
  records an index/control surface.
- Unsafe cancellation: first version only stops at tick boundaries.
- Scope creep into workflow engine: defer daemon scheduling, automatic retry
  policies, and multi-worker orchestration until the basic contract is stable.
- UI drift: desktop must consume the same projection as CLI, not a separate
  shape.
- Large-file churn: keep long-task code in focused modules and record any
  unavoidable debt in `docs/current/refactoring-debt.md`.
