# Adopt Existing Codex Session Design

## Goal

Isotope should be able to adopt an existing user-started Codex session by session
id, record it as a managed lane, and later resume it through Isotope's managed
worker path.

## Scope

This design covers Codex session adoption by session id. It does not attempt to
control the original terminal window. Existing tmux adoption remains unchanged
and continues to be the only adoption mode that supports direct `send`.

## User Model

A Codex session id is the durable conversation identity. A local TUI window is
only one terminal view onto that identity. Isotope adoption records the identity
and lane metadata in `managed_sessions.jsonl`; Isotope continuation starts a new
managed `codex resume <session-id>` process.

When the user later runs `codex resume <session-id>`, they should see both the
old manual history and the new history appended by Isotope's managed resume
process. The user must avoid writing to the same session from two live windows at
the same time.

## Behavior

- Add an adoption path that accepts `--session-id`.
- Validate the session id by finding a matching local Codex rollout file.
- Infer `cwd` from the session when `--cwd` is omitted.
- Store a managed record with `backend="codex_session"` and
  `resume_session_id=<session-id>`.
- Show the adopted lane in `scan`, dashboard, and review surfaces via the
  existing managed record projection.
- Keep `send` restricted to tmux-managed lanes.
- Use existing `resume` for active continuation.

## Non-Goals

- No direct input injection into arbitrary user TUI windows.
- No PID-based terminal control.
- No merging of multiple Codex session histories.
- No automatic resume while the original session is still actively writing.

## Error Handling

If the session id is unknown, adoption fails with a clear message. If `--cwd` is
not provided and the local session has no cwd metadata, adoption fails and asks
for `--cwd`. If a lane name is empty, existing validation applies.

## Testing

Add integration coverage around the registry and scan path:

- adopting by session id writes a managed record with `backend="codex_session"`;
- scan projects that record as a managed lane with `managed_resume_session_id`;
- adoption can infer cwd from a local session file;
- unknown session id is rejected;
- tmux adoption behavior remains unchanged.
