# Desktop Chat Golden Path Design

Date: 2026-06-04

## Goal

Make Desktop chat the primary product entrypoint for Isotope.

The user should state a goal in natural language. The model should keep agency:
it decides whether to answer directly, inspect project state, modify code, call
Codex, search the web, use or install supporting skills/MCPs, or repair Isotope
itself when Isotope is the limiting factor.

This design must not turn Desktop chat into an intent classifier, fixed router,
pipeline, workflow, or staged checklist.

## Non-Goals

- Do not make users understand capacity IDs, native coding internals, or
  Supervisor implementation terms.
- Do not encode prompt rules that map user intent to a fixed route.
- Do not stop just because a decision could be useful. The model should keep
  moving until completion, a hard boundary, or a real blocker.
- Do not auto-merge self-modifying changes into main.

## Product Shape

Desktop chat exposes one conversational surface. Behind it, Isotope gives the
model:

- registered capabilities and their contracts;
- project state, memory, artifacts, approvals, and worker summaries;
- bounded code-editing and validation capability;
- Codex-backed worker launch when the task is larger than native execution;
- web/search and installable extension options where available;
- low-sensitive execution observations after each action.

The UI should show what the model is doing in user language:

- reading project state;
- changing code in an isolated workspace;
- running verification;
- researching a missing capability;
- repairing an Isotope limitation;
- waiting only when a hard boundary needs approval.

It should not show raw internal labels as the main explanation.

## Model Agency

The conversation loop should present available capabilities and boundaries, then
let the model choose actions based on the current situation. It should avoid
hard-coded branches such as "if project question, call X" or "if code request,
call Y".

The implementation can validate capability inputs, enforce budgets, isolate
workspaces, and filter sensitive details. Those are guardrails, not route
selection.

## Project-State Use Case

When the user asks about project status, blockers, workers, approvals, or next
steps, the model can inspect Supervisor state and answer with a concise status
summary and suggested continuation.

Success means the answer is useful without requiring the user to open the
dashboard first.

## Code-Change Use Case

When the user asks for a concrete code change, the model can use bounded native
coding or launch a Codex worker. The result shown in Desktop chat should include:

- what changed;
- which files were touched;
- what verification ran;
- whether verification passed;
- what remains if it failed.

Success means a small code request can complete from Desktop chat without
switching to CLI.

## Isotope Self-Repair

Capability gap means the model recognizes an Isotope limitation, not merely that
the user was unclear. The model may try to repair that limitation by using
available actions:

- inspect Isotope code and docs;
- search for a solution;
- use or install a skill/MCP when allowed;
- modify Isotope in an isolated worktree;
- run targeted verification;
- present the diff and result back to the user;
- retry the original goal after repair when practical.

This is an action space, not a prescribed pipeline. The model chooses the next
move from context and observations.

## Boundaries

The model may continue autonomously for low-risk actions:

- read-only inspection;
- web/search research;
- creating an isolated worktree;
- editing Isotope inside that worktree;
- running allowlisted verification commands;
- summarizing diff and verification results.

The model must stop for approval before high-risk actions:

- merging into main;
- installing new dependencies, skills, or MCP servers;
- changing long-lived local or shared configuration;
- using external credentials or newly enabled network integrations;
- deleting or overwriting user data;
- making broad irreversible changes.

## Existing Reuse

- `stream_desktop_chat_events(...)` remains the Desktop chat backend stream.
- `run_supervisor_conversation_events(...)` remains the model-action loop.
- `CapabilityRunner.list_capabilities()` remains the capability metadata source.
- `coding_task.execute` remains the first bounded native code-change capability.
- Supervisor state projections remain the source for project-state answers.
- Existing capacity start/result stream events should be rendered in product
  language instead of raw implementation wording.

## Testing

Targeted verification should cover:

- Desktop chat can answer project-state questions from Supervisor projections.
- Desktop chat can execute a small code-change request and surface changed files
  plus verification status.
- A modeled Isotope limitation can trigger self-repair behavior in an isolated
  workspace without merging automatically.
- The prompt and decision layer do not encode fixed intent-to-route rules.
- High-risk self-repair actions require approval.

