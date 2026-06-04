# Agent Group Chat Design

Date: 2026-06-04

## Goal

Build Agent group chat as an Isotope-native Supervisor runtime.

Supervisor should be able to create a group, start multiple internal LLM agents,
send messages to them, let agents talk back to Supervisor or to each other,
arbitrate competing replies, persist the conversation, and summarize progress
for the user.

These agents are not external Codex workers. Codex worker fanout remains the
path for isolated coding worktrees. Agent group chat is the product conversation
and coordination layer inside Isotope.

## Non-Goals

- Do not launch external Codex processes for group-chat members.
- Do not replace existing managed Codex worker lifecycle, fanout, merge
  dispatch, or integration review.
- Do not store raw model prompts, raw model responses, stdout, stderr, full
  artifact content, or private capability outputs in public group messages.
- Do not build a broad autonomous organization system in the first slice.
- Do not create a second private message ledger when the existing worker event
  channel can carry the public group-message contract.

## Product Shape

The first useful version should support this flow:

1. A user asks Supervisor to open a group for a goal.
2. Supervisor creates a group and registers two or three internal agents, such
   as planner, implementer, and reviewer.
3. Supervisor posts the initial task message into the group.
4. Each agent receives the low-sensitive group context and produces a candidate
   reply or chooses silence.
5. The arbiter selects the visible replies for this turn and queues or drops
   the rest with reasons.
6. Selected messages are saved to the public message ledger.
7. Supervisor summarizes the turn and can continue, ask a specific agent, or
   stop.

The MVP is successful when a local CLI demo can create a group with three
internal agents, run one tick, show the group messages, and return a Supervisor
summary.

## Core Contracts

`AgentGroup` is the durable group container:

- `group_id`: stable id.
- `title`: short user-facing name.
- `goal`: user goal for the group.
- `status`: `active`, `paused`, `done`, or `archived`.
- `created_at`, `updated_at`.

`AgentMember` is one internal agent registered in a group:

- `member_id`: stable id inside the group.
- `group_id`.
- `name`: display name such as `planner`.
- `role`: short role description.
- `goal`: member-specific instruction.
- `model_profile`: model pool/profile hint, not a raw API config.
- `allowed_capabilities`: optional list of capability ids.
- `status`: `active`, `silent`, `blocked`, `done`, or `archived`.

`AgentGroupMessage` is the public message contract:

- `message_id`.
- `group_id`.
- `turn_id`.
- `from_member`: member id or `supervisor`.
- `to_member`: member id, `supervisor`, or `null` for broadcast.
- `message_type`: `task`, `reply`, `question`, `observation`, `summary`,
  `interrupt`, or `status`.
- `summary`: required low-sensitive message text.
- `payload`: optional low-sensitive structured metadata.
- `created_at`.

`AgentTurn` is one coordinated group-chat tick:

- `turn_id`.
- `group_id`.
- `input_message_ids`.
- `candidate_messages`.
- `selected_message_ids`.
- `queued_messages`.
- `dropped_messages`.
- `status`: `selected`, `silent`, `blocked`, or `error`.
- `supervisor_summary`.

## Reuse

- Reuse `worker_event_channel` as the storage/event channel for public group
  messages. Add group metadata to payloads instead of inventing a new raw log.
- Reuse `AgentConversationMessage` and
  `arbitrate_agent_conversation_turn(...)` for turn selection.
- Reuse `run_supervisor_conversation_events(...)` as the product-level
  Supervisor loop boundary, but extend it through a separate group-chat runtime
  rather than mixing group state into every desktop chat path.
- Reuse `CapabilityRunner` when an agent is allowed to call capabilities.
- Reuse `SupervisorStateSnapshot`-first projections for user-facing state.
- Keep managed Codex registry and fanout code unchanged unless group chat later
  asks Supervisor to launch real coding work.

## Architecture

Create a focused group-chat runtime under `src/isotope/features/supervisor/`.
The runtime should be small enough to test without real network access:

- `agent_group/contracts.py`: dataclasses and validation helpers for groups,
  members, messages, and turns.
- `agent_group/store.py`: public persistence over memory records and worker
  events.
- `agent_group/runtime.py`: create group, add members, send message, run one
  turn, summarize.
- `agent_group/provider.py`: convert member role/context into one provider call
  and return an `AgentConversationMessage`.
- `agent_group/commands.py`: CLI handlers for create, send, tick, list, and
  inspect.

The provider layer accepts an injected LLM provider in tests. Production should
resolve providers through existing Supervisor LLM pool mechanisms.

## Data Flow

Create group:

1. Validate title and goal.
2. Save `AgentGroup`.
3. Save requested `AgentMember` records.
4. Publish a `task` or `status` group message from `supervisor`.

Run one turn:

1. Load group, active members, and recent public messages.
2. For each active member, build a low-sensitive context with group goal,
   member role, recent selected messages, and allowed capabilities metadata.
3. Ask each member provider for one candidate message.
4. Pass candidates into the conversation arbiter.
5. Persist selected visible messages.
6. Persist turn metadata and queued/drop reasons.
7. Return a public summary for CLI, API, and desktop SSE.

Desktop chat integration:

1. User asks for multi-agent discussion.
2. Supervisor loop can call a group-chat capability or runtime action.
3. SSE emits group, member, message, turn, and summary events.
4. UI renders messages in the existing chat stream with collapsible details.

## Safety

- Public payloads must reject raw model/provider fields using the existing raw
  conversation payload guard pattern.
- Group messages carry summaries and low-sensitive metadata only.
- Capability execution remains allowlisted and contract-filtered.
- Each turn has a visible-message limit.
- Agent members can be paused or archived without deleting history.
- State lock conflicts are queued by the arbiter, not silently ignored.
- Errors from one member should produce a blocked/error candidate for that
  member, not fail the entire group unless Supervisor cannot persist the turn.

## Testing

Targeted tests should prove:

- Contracts reject empty ids, invalid statuses, and raw/private payload keys.
- A group can be created with three members and an initial Supervisor message.
- `tick` with deterministic providers persists selected messages and queued
  reasons.
- Broadcast and directed messages are both visible through the public event
  listing.
- A silent member does not force a fake reply.
- State lock conflicts are queued by the existing arbiter.
- `SupervisorStateSnapshot` or derived dashboard payload can expose active group
  summaries without reading private logs.
- Existing desktop chat and managed Codex fanout tests keep passing.

## First Implementation Slice

The first slice should stop after CLI-level product acceptance:

```text
isotope-supervisor agent-group create --goal "Plan this feature" --member planner --member reviewer
isotope-supervisor agent-group send --group <group_id> --message "Start with risks."
isotope-supervisor agent-group tick --group <group_id> --json
isotope-supervisor agent-group list --json
```

Desktop chat and SSE should come in the second slice after the runtime contract
is stable.
