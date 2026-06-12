# Agent Group Channel Workspace Design

Date: 2026-06-12

## Goal

Redesign the desktop `Agent Group Chat` experience from the current single-page
prototype into a Slack-like workspace with channels and direct messages.

The motivating workflow is `/home/lumber/Github/AI_Camp_RNA_2026`: one Codex
session explores research direction, another Codex session pushes engineering
work, and the user wants Isotope to make their progress, transcript history,
coordination, private AI-human discussion, and stop controls visible in one
place.

The first implementation should make the page usable, not merely demonstrable:
the user must be able to create a workspace/channel, add or remove Codex
sessions, choose send permissions, distinguish channel messages from private
messages, inspect Codex transcripts with high fidelity, and stop running AI
work.

## Product Decision

Use a mixed workspace/channel/direct-message model.

- A workspace is bound to a local project path such as
  `/home/lumber/Github/AI_Camp_RNA_2026`.
- Channels belong to one workspace and represent shared topics, for example
  `#rna-research`, `#engineering`, or `#platform-debug`.
- Codex sessions join channels as members. Membership has channel-local role,
  goal, status, and send permission.
- Direct messages are separate conversations in the same workspace, for example
  `Coordinator AI`, `Research Codex`, or `Engineering Codex`.
- The page keeps a three-column workbench shape: left navigation, central chat,
  and right settings/inspector.

This keeps the interface close to mature chat tools while preserving Isotope's
agent-specific controls.

## Non-Goals

- Do not build a broad organization or workflow engine in this slice.
- Do not force a mechanical router that decides all messages by fixed rules.
  The coordinator model should still decide whether to answer, relay, draft,
  wait, or ask privately, within explicit permission gates.
- Do not replace the existing `/desktop/chat` supervisor page.
- Do not hide Codex work behind short summaries or low-sensitivity JSON.
- Do not introduce a separate "global stop" control unless a later design shows
  a clear target. This design uses current-run stop and member stop.
- Do not promise OS-level termination for manually adopted Codex sessions unless
  Isotope owns a reliable process handle.

## Reuse Audit

Reuse:

- `src/isotope/features/supervisor/agent_group/*` for group, member, message,
  turn contracts, public projection, and durable state patterns.
- `src/isotope/features/supervisor/agent_group/codex_chat/*` for connected
  Codex member contracts, private chat, runtime controls, transcript API shape,
  and policy concepts.
- `worker_event_channel` as the low-sensitive public message ledger.
- `FileMemoryStore` for durable records.
- Existing Codex adoption/resume work: `adopt --session-id` remains the known
  registration path, while `resume_managed_codex(...)` is the continuation path
  when Isotope can safely resume a session.
- `src/isotope/integrations/codex/session_reader.py` for recent session index
  discovery and lightweight list previews.
- `src/isotope/integrations/codex/transcript.py` for high-fidelity transcript
  paging in the inspector.
- Existing desktop fetch/SSE and approval patterns from `/desktop/chat` where
  they fit.

Do not reuse as-is:

- The current `AgentGroupWorkspace.svelte` layout. Its member strip plus mixed
  group/private panes is not clear enough for channel navigation or settings.
- Lightweight Codex scan snapshots as user-visible transcript history. They are
  appropriate for recent-session lists, not for the full observation panel.
- A single group-level send permission. Permission must be scoped to the Codex
  session's membership in the current channel.

## Information Architecture

### Workspace

Add a workspace concept above channels.

Fields:

- `workspace_id`: stable id.
- `title`: display name, defaulting to the folder name when possible.
- `root_path`: local path used for cwd-scoped Codex session discovery.
- `status`: `active`, `archived`, or `error`.
- `created_at` and `updated_at`.

Creation behavior:

- The first implementation creates one default workspace from the current
  Supervisor project path when no workspace exists.
- The user can edit `root_path` in workspace settings.
- If no path is available, the UI asks for a path before offering the `cwd`
  recent-session filter.

### Channel

Channels are public group conversations inside a workspace.

Fields:

- `channel_id`: stable id.
- `workspace_id`: parent workspace.
- `name`: short channel name, shown as `#name`.
- `topic`: optional user-facing purpose.
- `status`: `active`, `archived`, or `error`.
- `created_at` and `updated_at`.

Default channels:

- A workspace can start with one empty `#general` channel.
- Creating a channel should not require adding Codex sessions immediately.
  The normal flow is quick create first, then add members from channel settings.

### Direct Message

Direct messages are private conversations in the same workspace.

Types:

- `coordinator`: private AI-human chat with the coordinator model.
- `codex_member`: private conversation scoped to one connected Codex member.

DM messages are not public channel broadcasts. The user should always know
whether the composer targets a channel or a DM.

## Layout

Use a Slack-like three-column workbench.

### Left Sidebar

The left sidebar contains:

- Workspace header with current workspace name and settings action.
- `+` action for creating a channel.
- Channel list, grouped under `Channels`.
- DM list, grouped under `Direct messages`.
- Per-item status badges for running, needs user, blocked, or stopped states.

Selecting a channel opens the channel conversation. Selecting a DM opens the
private conversation. This resolves the current ambiguity where the user cannot
tell whether a message goes to a group or an AI.

### Center Conversation

The center pane contains:

- Conversation header with channel or DM name.
- Compact topic/status line.
- Message timeline.
- Visible event types for user messages, coordinator replies, Codex member
  observations, drafts, sent messages, approvals, stop events, and errors.
- Composer whose placeholder and submit button name reflect the current target:
  for example `Message #rna-research` or `Message Coordinator AI`.

When a run is active:

- If the composer has text, the user chooses `Queue` or `Interrupt`.
- If the composer is empty, the primary send button becomes `Stop`.
- `Stop` targets the current visible run in the selected channel or DM.

### Right Inspector

The right pane changes by selected conversation.

For a channel, it shows:

- Channel settings.
- Codex members in that channel.
- Add/remove Codex controls.
- Send permission controls.
- Selected member transcript.
- Member-level stop controls.

For a DM, it shows:

- DM participant details.
- Related Codex session metadata when applicable.
- Transcript panel for a Codex-member DM.
- Stop control for that member when applicable.

The right pane is collapsible on narrow screens and remains accessible from the
conversation header.

## Codex Session Selection

Adding a Codex session happens from channel settings.

The `Add Codex` dialog has three entry paths:

1. `cwd` recent list: recent Codex sessions whose recorded `cwd` is equal to or
   under the workspace `root_path`.
2. `all` recent list: recent Codex sessions from the global Codex history.
3. Manual entry: user-entered session id plus display name, role, goal, and
   send permission.

Recent-list item contents:

- Thread title when available.
- Short session id.
- Full `cwd`.
- Last event time.
- Source path when known.
- Lightweight preview from recent messages.
- A clear unavailable/error state when the session file cannot be read.

Selection behavior:

- The user can select one or more recent sessions and add them to the current
  channel.
- Duplicate membership in the same channel is blocked.
- The same Codex session can be added to different channels with different
  roles, goals, and send permissions.
- Manual entry remains available even if the session cannot be found locally,
  but the resulting member is marked with an attention state until resolved.

Filtering details:

- `cwd` matching uses normalized local paths. A session matches if its `cwd` is
  the workspace `root_path` or a descendant.
- `all` does not apply a workspace path filter.
- Both lists should be ordered by most recent activity.
- The list preview uses lightweight scan/snapshot data. The transcript panel
  uses high-fidelity paged transcript reading.

## Membership And Permissions

Channel membership fields:

- `member_id`: stable id for this channel membership.
- `workspace_id` and `channel_id`.
- `display_name`: for example `Research Codex`.
- `member_kind`: `codex_session`, `internal_agent`, or `supervisor`.
- `role`: short role label.
- `goal`: optional member-specific goal.
- `send_policy`: `auto`, `confirm`, or `draft_only`.
- `status`: `active`, `running`, `idle`, `needs_user`, `terminated`,
  `blocked`, or `archived`.
- `resume_session_id`: Codex session id when applicable.
- `source_path`: local JSONL path when known.
- `managed_record_id`: managed process record when Isotope owns the run.
- `created_at` and `updated_at`.

Permission semantics:

- `auto`: the coordinator may send to this member without user confirmation,
  subject to safety gates and runtime state.
- `confirm`: the coordinator creates an approval draft. The user approves or
  denies before Isotope sends.
- `draft_only`: the coordinator may write a suggested message, but Isotope does
  not send automatically.

Permissions are channel-local. A Codex session can be trusted for automatic
messages in one channel and restricted in another.

## Message Model

A message belongs to a workspace conversation.

Shared fields:

- `message_id`.
- `workspace_id`.
- `conversation_type`: `channel` or `dm`.
- `conversation_id`: `channel_id` or `dm_id`.
- `from_actor`: user, coordinator, supervisor, or member id.
- `to_actor`: optional actor id.
- `message_type`: `user`, `model_reply`, `private_note`, `draft_send`,
  `sent_to_member`, `member_observation`, `runtime_control`, `status`,
  `approval`, or `error`.
- `summary`: visible text.
- `payload`: low-sensitive metadata only.
- `created_at`.

Channel messages are visible in the channel stream. DM messages remain in that
DM and are not mistaken for channel broadcasts.

The UI must not show only middleware JSON. Tool calls, commands, approvals,
status changes, and assistant replies should be projected into readable chat
events while keeping raw inspection available where useful.

## Coordinator Behavior

The coordinator model receives:

- Workspace and selected conversation metadata.
- Channel members, statuses, send policies, roles, and goals.
- Recent channel or DM messages.
- Private coordinator notes relevant to the selected workspace.
- Transcript references and selected excerpts, clearly marked as projections.
- Available actions and their permission gates.

The coordinator may choose:

- `reply_channel`: answer in the selected channel.
- `reply_dm`: answer in the selected DM.
- `send_member`: send to a Codex member when policy allows.
- `draft_member_send`: create an approval or draft.
- `wait`: do nothing now.
- `record_gap`: record missing context or capability.

The coordinator should decide whether to answer directly, relay between agents,
draft a message, or ask the user privately. The product should not reduce this
to a rigid routing table.

## Transcript Observation

Codex history must remain highly visible.

Requirements:

- The transcript panel pages through event-level Codex JSONL history.
- It shows assistant/user messages, tool calls, command output, approvals,
  errors, and status events in readable form.
- It supports raw-event inspection for debugging.
- It shows `session_id`, `source_path`, `source_size_bytes`, last event time,
  current offset, and whether more history is available.
- It uses high default page sizes and load-more controls instead of silently
  clipping to a short final output.
- It distinguishes "what the user can inspect" from "what the model saw".

Model context can still use summaries and recent windows for cost control. The
user-facing transcript viewer must prioritize recreating the terminal
observation experience.

## Stop And Runtime Control

Use two stop surfaces.

### Current-Run Stop

In the selected channel or DM:

- If a run is active and the composer is empty, `Send` becomes `Stop`.
- Pressing it sends a `terminate` control with target `current_run`.
- The result is persisted as a runtime-control event and rendered in the
  timeline.

### Member Stop

In channel settings or member DM:

- Each AI member has a `Stop` action.
- Pressing it sends a `terminate` control with target `member`.
- For managed Codex sessions, Isotope requests cancellation or termination
  through the managed runtime path.
- For adopted manual sessions without a process handle, Isotope stops future
  scheduling/sends, marks the member `terminated`, and tells the user the
  original terminal process may still be alive.
- The coordinator must not auto-send to a terminated member until the user
  resumes or re-adds it.

There is no separate global stop in this design.

## Backend Shape

Add a channel workspace layer without discarding the current group-chat code.

Planned modules:

- `features/supervisor/agent_group/workspace_contracts.py`: workspace,
  channel, DM, channel membership, and conversation-message contracts.
- `features/supervisor/agent_group/workspace_store.py`: durable store for
  workspaces, channels, DMs, memberships, and messages.
- `features/supervisor/agent_group/workspace_runtime.py`: coordination and
  runtime-control application.
- Existing `codex_chat` helpers remain the Codex-specific integration layer
  and should be adapted rather than duplicated.

Endpoint shape:

- `GET /desktop/agent-workspaces`
- `POST /desktop/agent-workspaces`
- `GET /desktop/agent-workspaces/{workspace_id}`
- `POST /desktop/agent-workspaces/{workspace_id}/channels`
- `GET /desktop/agent-workspaces/{workspace_id}/codex-sessions?scope=cwd|all`
- `POST /desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members`
- `DELETE /desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members/{member_id}`
- `PATCH /desktop/agent-workspaces/{workspace_id}/channels/{channel_id}/members/{member_id}`
- `POST /desktop/agent-workspaces/{workspace_id}/conversations/{conversation_id}/chat`
- `POST /desktop/agent-workspaces/{workspace_id}/conversations/{conversation_id}/control`
- Existing transcript endpoint can remain session-oriented if it is easier to
  reuse: `GET /desktop/codex-sessions/{session_id}/transcript`.

The exact route names can be adjusted during implementation if they conflict
with existing route style, but the model boundary remains: workspace,
channel/DM conversation, membership, transcript, and runtime control.

## Frontend Shape

Replace the current `AgentGroupWorkspace.svelte` prototype with a composed
workspace UI.

Planned components:

- `AgentWorkspaceShell.svelte`: three-column layout and selected conversation
  state.
- `AgentWorkspaceSidebar.svelte`: workspace header, channels, DMs, create
  channel action.
- `AgentConversationPane.svelte`: header, timeline, and target-aware composer.
- `AgentConversationComposer.svelte`: send, queue, interrupt, and stop behavior.
- `AgentChannelInspector.svelte`: channel settings, member list, add/remove,
  permissions, and selected transcript.
- `CodexSessionPicker.svelte`: `cwd`, `all`, and manual entry modes.
- Existing `CodexTranscriptPanel.svelte` can be reused or refined.

UX rules:

- The composer must visibly name the current target.
- Channel and DM selection must change both the timeline and the composer
  target.
- Member settings must expose send permission in the same place as session
  identity.
- A running state is visible at the sidebar item and conversation header,
  not only in the message stream.
- The page should feel like a dense workbench, not a landing page.

## Error Handling

Handle these cases explicitly:

- Workspace path is missing, invalid, or inaccessible.
- Codex recent-session index is unavailable.
- A selected session id has no readable local JSONL file.
- A member is already present in the channel.
- A send is blocked by `confirm`, `draft_only`, stopped status, missing resume
  path, or missing managed process handle.
- Transcript page loading fails.
- Stop succeeds only partially for an adopted manual session.

Errors should appear in the relevant pane and also persist an event when they
affect conversation state.

## Migration And Compatibility

The first implementation creates new workspace/channel records and keeps the
existing `agent_group` prototype readable through its current endpoints. A later
migration can map prototype records into the new model:

- Existing groups become channels in a default workspace.
- Existing connected members become channel memberships.
- Existing private chat becomes the coordinator DM where possible.
- Existing transcript endpoints can remain session-oriented.

The UI must prefer the new workspace model. Legacy groups should not block the
new channel UI.

## Testing

Backend unit tests:

- Workspace/channel/DM/member contracts validate required fields and choices.
- Store creates, lists, updates, deletes, and rejects duplicate channel
  memberships.
- `cwd` Codex session filtering includes sessions at or under `root_path` and
  excludes unrelated paths.
- `all` session filtering returns recent sessions without path filtering.
- Permission gates produce send, approval, or draft outcomes correctly.
- Runtime controls persist current-run and member stop events.

Frontend tests:

- Sidebar switches between channels and DMs.
- Composer target text changes with selected conversation.
- Running with empty composer shows `Stop`.
- Running with text shows `Queue` and `Interrupt`.
- Channel settings can open the Codex session picker.
- Session picker exposes `cwd`, `all`, and manual modes.
- Member permission edits are reflected in the inspector.

Integration/smoke tests:

- Desktop smoke creates a workspace, creates a channel, adds two Codex sessions
  from fixtures, sends a channel message, opens a DM, opens transcript, and
  stops a member.
- Run `scripts/dev-eval changed_surface --base origin/main --json` after the
  implementation because this touches Supervisor/desktop conversation behavior.

## Implementation Slices

1. Backend workspace/channel contracts and store.
2. Codex recent-session discovery endpoint with `cwd` and `all` scopes.
3. Channel membership add/remove/update permissions.
4. Workspace frontend shell with sidebar and conversation target switching.
5. Channel inspector and Codex session picker.
6. Target-aware composer with send, queue, interrupt, and stop controls.
7. Transcript integration and member stop polish.
8. Migration or compatibility handling for existing prototype groups.

Each slice should be independently testable. The first implementation
prioritizes a complete local workflow over broad customization.
