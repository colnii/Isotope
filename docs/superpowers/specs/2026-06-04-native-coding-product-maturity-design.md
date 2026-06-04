# Native Coding Product Maturity Design

Date: 2026-06-04

## Goal

Make native coding usable as a product feature from Supervisor/Desktop chat:
the user gives a natural-language coding goal, Isotope uses the existing agent
loop to inspect the repository, propose and execute a bounded change in an
isolated workspace, verify it, and return reviewable evidence before anything is
applied to the source workspace.

## Core Correction

Do not build a separate "coding agent loop".

Isotope already has an agent loop and capability execution path. Native coding
maturity means improving that existing loop so it can orchestrate the current
capabilities:

- `code.search`
- `code.read`
- `workspace.materialize`
- `code.apply_patch`
- `test.run`
- `artifact.changed_files`
- `artifact.diff_summary`
- `coding_task.execute`

`coding_task.run` may be added as a product-level capability, but it is not a
new loop. It is an entrypoint that asks the existing agent loop to perform the
right sequence of capability calls.

## Current Context

The current `coding_task.execute` is a low-level executor. It requires a prepared
patch and verification argv, materializes an isolated workspace under the
runtime state root, applies the patch, runs an allowlisted verification command,
and writes changed-file and diff-summary artifacts.

That is useful, but it is not yet a mature product feature because the model
still needs a separate way to understand the repository, decide what to edit,
choose verification, revise after failures, and present a user-facing review.

## Product Contract

The user-facing coding entrypoint should accept only the goal:

```text
coding_task.run(goal)
```

The system supplies routing and provenance context:

- `cwd`: current source workspace.
- `root`: Isotope runtime state root.
- `run_id`: current agent-loop run.
- `execution_id`: generated execution id for action provenance.
- `workspace_id`: isolated workspace id.

The model should not invent or directly supply these fields. It may request
code search, code reads, patch application, and verification through capability
calls. The system performs those calls using the current `cwd` and `root`.

## Environment Understanding

`cwd` and `root` do not make the model understand the repository. They only tell
the system where to execute safe operations and where to store state.

Model understanding must come from agent-loop-mediated observations:

1. The model receives the user goal and capability manifest.
2. The model calls `code.search` or `code.read` to inspect relevant files.
3. The system executes those calls against `cwd` and returns bounded,
   low-sensitive observations.
4. The model asks for more context or proposes a patch and verification.
5. The system applies and verifies the change in an isolated workspace.
6. The model uses the result summary to either revise or report a reviewable
   outcome.

The model never gets raw filesystem authority. It gets observations returned by
capabilities.

## Architecture

Keep the existing layers:

1. Desktop/Supervisor chat receives the user goal.
2. `run_supervisor_conversation_events(...)` runs the model-action loop.
3. The model selects `call_capability`.
4. The existing agent loop executes the capability call.
5. `CapabilityRunner` enforces the selected capability input contract.
6. Capability runners perform bounded filesystem, workspace, test, or artifact
   actions.
7. The conversation loop streams low-sensitive capacity events and observations
   back to the model and UI.

`coding_task.run` should fit into this path. It should not bypass
`CapabilityRunner`, agent-loop control, workspace isolation, artifact storage,
or low-sensitive projection.

## Data Flow

User request:

`Desktop chat -> conversation loop -> existing agent loop -> capability calls`

Context collection:

`code.search/code.read -> bounded observations -> model planning`

Execution:

`workspace.materialize -> code.apply_patch -> test.run -> artifact summaries`

Review:

`artifact.changed_files/artifact.diff_summary -> capacity result -> Desktop UI`

Optional application to source workspace:

`reviewed isolated diff -> explicit user approval -> apply back to source`

## Capability Shape

Add a product-level capability:

```text
coding_task.run
```

Required input:

- `goal`

System defaults:

- `root`
- `cwd`
- `run_id`
- `execution_id`
- `workspace_id`

Optional user/model-safe inputs:

- `include_paths`
- `forbidden_paths`
- `verification_intent`
- `max_steps`
- `timeout_seconds`

Output:

- `status`: `verified`, `needs_revision`, `needs_input`, `blocked`, or `error`.
- `workspace_id`
- `changed_files`
- `verification`
- `artifact_refs`
- `next_action`

## Scope

In scope:

- Reuse the existing agent loop to orchestrate coding capabilities.
- Keep source workspace unchanged until explicit apply/approval.
- Let the model gather context through `code.search` and `code.read`.
- Let the model propose patches and verification through structured capability
  calls.
- Run patch and verification in an isolated workspace.
- Return low-sensitive evidence: changed files, diff summary, verification
  status, and blocker reasons.
- Hide raw patch, raw argv, prompts, transcripts, and raw file content from UI
  summaries.

Out of scope for the first maturity slice:

- A separate coding-specific agent runtime.
- Automatic merge to `main`.
- Automatic commit without user approval.
- Broad dependency installation.
- Full raw source projection into Desktop chat.
- Replacing existing `coding_task.execute`.

## Error Handling

The product entrypoint should distinguish:

- `needs_input`: the goal is too vague or required scope is missing.
- `blocked`: a guardrail prevents progress, such as forbidden path, missing
  verification command, or exhausted budget.
- `needs_revision`: patch applied but verification failed.
- `error`: implementation failure or malformed capability result.

Verification failure should not end the product flow immediately. The existing
agent loop should receive the low-sensitive failure summary and may attempt a
bounded revision until `max_steps` is exhausted.

## Review And Apply

Native coding should finish with a reviewable result, not silent source edits.

The default final state is:

- isolated workspace contains the modified files;
- artifacts contain changed-file and diff summaries;
- Desktop/Supervisor shows what changed and what verification ran;
- source workspace remains unchanged.

A later apply capability may copy the reviewed diff back to the source
workspace only after explicit user approval.

## Testing

Targeted tests should prove:

- `coding_task.run` appears in the default capability catalog as a product
  candidate.
- The user-facing contract does not require `cwd`, `root`, `run_id`,
  `execution_id`, `patch`, or `argv`.
- The existing agent-loop capability path injects system context instead of
  accepting model-invented routing fields.
- A small natural-language coding request causes `code.read` or `code.search`
  before patch execution.
- A verified isolated change returns changed files, verification status, and
  artifact refs without mutating the source workspace.
- A failing verification can trigger a bounded revision.
- Raw patch and argv do not appear in low-sensitive capacity events.

Run targeted unit tests for capabilities, agent-loop step execution, and
Supervisor conversation events before broader Supervisor/Desktop tests.

## Rollout

Implement in thin slices:

1. Add `coding_task.run` as a cataloged product capability with a safe launch
   plan and no source mutation.
2. Route `coding_task.run` through the existing agent loop and prove system
   context injection.
3. Add context collection using existing `code.search` and `code.read`.
4. Add single-pass patch and verification by reusing `coding_task.execute` or
   its component capabilities.
5. Add bounded revision after verification failure.
6. Add review/apply separation for moving isolated changes back to source.

Each slice should keep the existing `coding_task.execute` contract stable unless
there is a focused migration plan and tests for current callers.
