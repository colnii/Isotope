# Codex Rollback Sync Design

## Goal

When a connected Codex session is manually rolled back, Agent Group Chat should follow the current effective conversation instead of leaving reverted branch messages in the main chat stream.

## Product Semantics

Codex session JSONL files are append-only audit logs. Isotope must not rewrite or truncate them. A `thread_rolled_back` event means the user intentionally moved the active Codex thread back to an earlier point while the raw historical branch remains inspectable.

The normal group or private chat view represents the current collaboration state, not the raw audit log. Messages imported from a Codex branch that was later rolled back should be hidden from the default conversation view. Raw transcript and terminal/debug views may still expose the rollback event and surrounding historical events.

## Architecture

Transcript reading projects Codex rollback events from `event_msg.payload.type == "thread_rolled_back"` into a first-class `rollback` event. The projection includes `event_index`, timestamp, `num_turns`, and optional `reason`, while raw payloads remain available only when raw inclusion is requested.

Workspace import tracks rollback state in each Codex member's `transcript_policy`. On import, it detects rollback events after the last import cursor, records the latest rollback index, imports only candidate messages after that rollback within the same scan, and marks already imported member observations from the same session at or before the rollback as superseded.

Workspace message listing keeps append-only event storage but filters superseded message ids and internal rollback status messages by default. This makes the chat UI behave like a current timeline while preserving raw events for audit and debugging.

## Data Flow

1. User manually rolls back a Codex session.
2. Codex appends `event_msg` with payload type `thread_rolled_back` to the JSONL file.
3. Isotope polls/imports the session.
4. Importer sees the rollback event, updates `last_rollback_event_index`, and marks earlier imported member observations from that member/session as superseded.
5. Store `list_messages()` excludes superseded messages and rollback status metadata from default results.
6. Transcript/terminal views can still show the rollback event and raw JSONL data.

## Error Handling

Unknown rollback payload fields are ignored in the public projection unless raw view is requested. Missing or malformed `num_turns` is projected as `None`. If a rollback is detected without any later assistant candidate, import returns a `thread_rolled_back` status and advances the cursor so the frontend can refresh without repeatedly surfacing the same rollback.

## Testing

Unit tests cover transcript rollback projection, terminal rollback visibility, importer behavior for `old candidate -> rollback -> new candidate`, rollback-only cursor advancement, and default store filtering of superseded member observations.
