# Agent Group Codex Chat Design

Date: 2026-06-12

## Goal

Build a desktop Agent Group Chat surface where the user can connect multiple
existing or Isotope-managed Codex sessions, watch their work with high-fidelity
transcripts, let an upper-level coordination model decide when to answer,
private-chat with the user, or send messages to a member, and stop running AI
sessions when needed.

The motivating scenario is `/home/lumber/Github/AI_Camp_RNA_2026`: one Codex
session explores research direction, another pushes engineering work, and the
user currently has to manually shuttle progress and reminders between them.

## Product Shape

The first useful product version should support this flow:

1. The user opens a new `Agent Group Chat` page from the desktop app.
2. The user selects or manually enters Codex session ids and display names,
   for example `Research Codex` and `Engineering Codex`.
3. Each member has a role, optional goal, and send policy:
   `auto`, `confirm`, or `draft_only`.
4. The page shows a public group stream, an AI-human private chat, a member
   list, and a high-fidelity Codex transcript panel per member.
5. The coordination model receives member metadata, visible group state, user
   instructions, and transcript references. It decides whether to answer in the
   group, private-chat the user, draft or send a message to a Codex member, or
   wait.
6. During a running turn, a user text message can be queued or interrupt the
   current coordination run.
7. When the composer is empty and an Isotope run is active, the send button
   becomes `Stop current run`.
8. Each connected AI member has its own `Stop` action. Stopped members are
   marked `terminated` and are excluded from auto-send until resumed.

## Non-Goals

- Do not build a broad autonomous organization system in this slice.
- Do not make fixed intent routes such as "research always talks to engineering"
  or "engineering always waits for research". The model owns the coordination
  decision.
- Do not replace the existing `/desktop/chat` conversation loop.
- Do not silently truncate user-visible Codex history into a short summary.
- Do not guarantee termination of arbitrary hand-started terminal processes
  unless Isotope has a reliable managed process handle. For adopted manual
  sessions, stopping can always stop Isotope scheduling and future sends.
- Do not expose raw secrets, API keys, or private tool payloads in public group
  messages.

## Reuse Audit

Reuse:

- `src/isotope/features/supervisor/agent_group/*` for group, member, message,
  turn contracts, storage, public worker-event messages, and state projection.
- `worker_event_channel` as the public group-message ledger.
- `FileMemoryStore` for durable group/member/turn and control records.
- Existing Codex session adoption by session id from
  `docs/superpowers/specs/2026-06-05-adopt-codex-session-design.md`.
- Existing desktop SSE patterns from `/desktop/chat`, especially streaming
  events, capacity cards, and approval-style visible actions.
- Existing approval and runtime-control plumbing where possible instead of
  inventing a separate approval subsystem.

Do not reuse as-is:

- `read_codex_session(...)` as the transcript viewer backend. It is built for
  lightweight scan projection and may read only head and tail for large files.
  This feature needs a dedicated transcript reader that can expose full
  history by range or page.
- Current `AgentGroupRuntime._member_prompt(...)` context clipping. It takes a
  small recent public-message window and is not enough for Codex transcript
  observation.

## Core Contracts

### Connected Member

Extend the group member concept with connected-session metadata:

- `member_id`: stable id inside the group.
- `display_name`: user-facing name such as `Research Codex`.
- `member_kind`: `codex_session`, `internal_agent`, or `supervisor`.
- `role`: short member role.
- `goal`: optional member-specific goal.
- `send_policy`: `auto`, `confirm`, or `draft_only`.
- `status`: `active`, `running`, `idle`, `needs_user`, `terminated`,
  `blocked`, or `archived`.
- `resume_session_id`: Codex session id for adopted or managed Codex members.
- `source_path`: local Codex JSONL path when known.
- `managed_record_id`: managed registry id when Isotope owns the process.
- `transcript_policy`: default transcript view policy, including page size and
  safety filter settings.

### Group Message

Public group messages remain low-sensitive and structured:

- `message_type`: `user`, `model_reply`, `private_note`, `draft_send`,
  `sent_to_member`, `member_observation`, `runtime_control`, `status`,
  or `error`.
- `from_member`: user, coordinator model, supervisor, or member id.
- `to_member`: optional member id.
- `summary`: public text.
- `payload`: low-sensitive metadata only, such as transcript refs, message
  ids, send policy, and control result.

### Private AI-Human Chat

Private chat is separate from public group messages:

- It is visible to the user and the coordination model.
- It can ask the user for clarification or report a concern without sending it
  to Codex members.
- Private-chat messages are persisted with a `private_human_chat` channel or
  equivalent scope so they are not mistaken for group broadcasts.

### Send Decision

The coordination model may emit one of these actions:

- `reply_group`: write to the public group stream.
- `reply_private`: write to AI-human private chat.
- `send_member`: send text to a connected member if policy allows.
- `draft_member_send`: create a draft that the user can approve.
- `wait`: do not send, optionally explain why.
- `record_gap`: record missing context or missing capability.

Policy handling:

- `auto`: send immediately unless runtime safety gates block.
- `confirm`: create a visible approval draft before sending.
- `draft_only`: never send automatically; only present text for user copy or
  manual approval.

### Runtime Control

Use three separate control intents:

- `queue`: user text waits until the current run reaches a safe boundary.
- `interrupt`: current coordination run pauses and replans with the new user
  message.
- `terminate`: stop a target run or member.

Stop UI is two-layered:

- Current-run stop: if the composer is empty and an Isotope run is active,
  `Send` becomes `Stop current run`.
- Member stop: every connected AI member card has `Stop`. It targets that
  member only.

Termination effects:

- Managed Isotope process: request cancellation or termination through the
  existing managed process/runtime path.
- Adopted manual Codex session without a process handle: stop Isotope
  scheduling and future sends, mark the member `terminated`, and explain that
  the original terminal process may still be alive.
- After termination, the coordinator model must not auto-send to that member
  until the user resumes it.

## Transcript Contract

User-visible Codex observation must not be reduced to a short summary.

The transcript layer should provide:

- `source_path`, `session_id`, `source_size_bytes`, and last event timestamp.
- Event-level pages read from the Codex JSONL file.
- A readable projection for messages, tool calls, command output, approvals,
  errors, and status events.
- A raw-event inspection mode for debugging.
- High default limits and scrollable panels.
- Range or page loading for large files, so the UI can eventually inspect the
  full local history without loading the entire file into memory at once.
- A visible notice when the model saw only a projection or excerpt.

Model context can use summaries, recent windows, and transcript references for
cost control, but these are projections. They must not replace the user-facing
full transcript surface.

## Data Flow

Create or open a group:

1. Load existing `agent_group` groups from Supervisor state.
2. Let the user create a group or open a recent group.
3. Discover recent Codex sessions from session indexes and local JSONL files.
4. Let the user select sessions or manually enter session ids.
5. Store connected-member metadata and send policies.

Run coordination:

1. Load group state, member statuses, private chat, public group messages, and
   transcript refs.
2. Build a coordination-model prompt that describes available members, send
   policies, recent public/private context, and transcript refs.
3. Let the model choose a `SendDecision`.
4. Apply policy gates.
5. Emit SSE events for private replies, group messages, drafts, sends,
   transcript updates, and runtime-control results.
6. Persist low-sensitive public messages and private chat messages separately.

Send to Codex:

1. If the member is Isotope-managed, send through the existing managed Codex
   path.
2. If the member is adopted by session id, continue through an Isotope-managed
   `codex resume <session-id>` path when available.
3. If no reliable send path exists, create a draft with explicit reason rather
   than pretending the send succeeded.

Stop:

1. `Stop current run` targets the current active coordination/private-chat run.
2. Member `Stop` targets a selected connected member.
3. Persist a `runtime_control` event with target, status, and result.
4. Project the stopped state in the member list and group stream.

## Frontend

Add a page-level entry named `Agent Group Chat`.

Recommended layout:

- Left or top member strip: connected Codex sessions, status, role, send
  policy, and member `Stop`.
- Center group stream: public conversation and coordination events.
- Right or lower transcript inspector: selected member transcript with
  readable and raw views.
- Private AI-human chat: a clearly separate pane or tab, not mixed into public
  group messages.
- Composer: text input with queue/interrupt choices when running; empty input
  morphs `Send` into `Stop current run` when a run is active.

The UI should keep dense operational ergonomics. This is a workbench page, not
a marketing hero or decorative chat mockup.

## Backend Surface

Likely new endpoints or route families:

- `GET /desktop/agent-groups`
- `POST /desktop/agent-groups`
- `GET /desktop/agent-groups/{group_id}`
- `POST /desktop/agent-groups/{group_id}/members`
- `POST /desktop/agent-groups/{group_id}/chat`
- `POST /desktop/agent-groups/{group_id}/control`
- `GET /desktop/codex-sessions`
- `GET /desktop/codex-sessions/{session_id}/transcript`

The exact route split can be adjusted during implementation, but the backend
must keep group messages, private chat, transcript paging, send decisions, and
runtime controls as distinct concepts.

## Safety And Failure Modes

- Raw transcript and public group payloads must pass secret and raw-payload
  guards before public projection.
- If a member send fails, the group stream shows a failed send event with a
  clear retry path.
- If transcript reading fails, the member card remains visible with an error
  state instead of disappearing.
- If a member is terminated while a send is queued, queued sends are cancelled
  or moved back to draft state.
- If the model requests an action blocked by policy, emit a visible blocked
  draft instead of silently dropping the action.
- If the browser reconnects, state must be reconstructable from persisted group
  messages, private chat, member metadata, and control events.

## Testing

Backend tests:

- Connected-member contracts validate send policy and terminated status.
- Session lookup accepts manual session ids and selected recent sessions.
- Transcript reader can page through a synthetic large JSONL without head-tail
  truncation.
- Coordination action policy converts `auto`, `confirm`, and `draft_only` into
  the correct send or draft result.
- `terminate` marks members terminated and prevents later auto-send.
- `Stop current run` records a runtime-control event.

Frontend tests:

- Agent Group Chat page entry is reachable.
- Empty composer while running shows `Stop current run`.
- Non-empty composer while running exposes queue and interrupt choices.
- Member cards render send policy, transcript status, and member `Stop`.
- Private chat messages are visually distinct from public group messages.
- Transcript panel scrolls and can switch readable/raw views.

Integration or smoke tests:

- Create a group with two fake Codex sessions.
- Load transcript pages from local JSONL fixtures.
- Run a fake coordination decision that private-chats the user.
- Run a fake coordination decision that drafts a send for a `confirm` member.
- Stop one member and verify no later auto-send targets it.

For changes touching Supervisor conversation behavior, capacity contracts,
agent-loop result projection, or dev evals, run:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

If `eval_required=true`, run the recommended smoke command and report the hard
gates and findings.

## Implementation Slices

1. Backend contracts and transcript reader:
   connected-member contract, transcript paging, unit tests.
2. Group runtime extension:
   private chat channel, send decision contract, policy handling, terminate
   state.
3. Desktop API and SSE:
   route handlers, stream events, snapshot projection.
4. Frontend page:
   navigation entry, member list, group stream, private chat, transcript panel,
   queue/interrupt/stop controls.
5. Product smoke:
   fake two-session scenario, then a local real Codex session read-only smoke.

## References

- OpenAI Agents SDK:
  https://developers.openai.com/api/docs/guides/agents
  runtime/state, handoffs, human review, and observability.
- LangGraph interrupts:
  https://docs.langchain.com/oss/python/langgraph/interrupts
  pause and resume pattern for human-in-the-loop control.
- AutoGen SelectorGroupChat:
  https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html
  model-driven speaker selection in group chat.
- Anthropic effective agents:
  https://www.anthropic.com/research/building-effective-agents
  prefer simple composable agent patterns before complex autonomous systems.
