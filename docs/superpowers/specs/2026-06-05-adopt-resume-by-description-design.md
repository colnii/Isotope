# Adopt And Resume By Description Design

## Goal

Let a user describe the Codex work they want to continue, then let Isotope find
the matching local Codex session, adopt it if needed, and launch a managed
resume worker without requiring the user to provide a session id or run a CLI
command.

## Scope

This slice adds a deterministic session matching and execution boundary. It does
not add free-form terminal control, does not inject input into an old TUI window,
and does not write to multiple sessions for one request.

## User Model

The user says something like "continue the ai4s research exploration session".
Isotope scans local Codex sessions, ranks candidates against that description,
and either:

- resumes the single clear match through a managed Codex process; or
- returns a small candidate list when the match is ambiguous.

The model can call this capability from desktop chat, but the final session
choice is constrained to ranked candidates produced by Isotope.

## Behavior

- Add a session matcher that uses local session metadata, cwd, title, recent
  user text, and recent assistant text.
- Match by normalized token overlap and a few stable field weights.
- Treat one top candidate as clear only when it passes a minimum score and is
  meaningfully ahead of the second candidate.
- Add a supervisor operation `adopt_resume_by_description`.
- If the target session is already adopted under a managed lane, reuse that lane.
- If it is not adopted, call `adopt_codex_session` with an inferred lane name.
- Call `resume_managed_codex` using the matched real Codex session id.
- Return structured status:
  - `resumed` for a launched managed resume;
  - `ambiguous` with candidates for close matches;
  - `no_match` when no candidate is good enough.

## Safety

- No automatic resume for ambiguous descriptions.
- No use of `managed:<record-id>` as the resume target; always resume the real
  Codex session id.
- No tmux `send` for this path.
- No simultaneous fanout to multiple sessions.

## Testing

Tests cover clear match, ambiguous match, no match, existing adopted lane reuse,
and the supervisor capability runner operation path.
