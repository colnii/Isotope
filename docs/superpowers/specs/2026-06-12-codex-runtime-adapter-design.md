# Codex Runtime Adapter Design

## Goal

Build the first shared Codex runtime adapter layer for Isotope.

Plain meaning: Codex CLI does the work and emits JSONL logs. The new layer turns
those logs into one standard Isotope runtime result that other features can
reuse.

This first slice is deliberately not a new user-facing capability and not a UI
feature. It creates the reusable interpretation layer that later Supervisor,
agent-group, desktop chat, and Codex-backed capability work can share.

## Current Context

Existing code already provides several Codex-related pieces:

- `src/isotope/integrations/codex/cli.py` runs `codex exec --json` through
  `CodexCliBackend`.
- `src/isotope/integrations/codex/task.py` defines `CodexTaskAdapter`, which
  validates Codex task requests and writes output artifacts.
- `src/isotope/integrations/codex/jsonl.py` has small helpers for extracting a
  final agent message and diagnostics from JSONL stdout.
- `src/isotope/integrations/codex/transcript.py` reads saved local Codex session
  transcript files for paged UI display.
- `src/isotope/llm/provider/codex.py` uses Codex CLI as an LLM provider but
  intentionally tells Codex not to inspect files or run tools.
- `src/isotope/features/supervisor/agent_group/codex_chat/` connects existing
  Codex sessions to agent-group chat state, but it is not a general runtime
  adapter.

The missing piece is a focused runtime projection layer that can interpret one
Codex CLI JSONL run into low-sensitive, structured Isotope data without each
caller inventing its own parser.

## Reuse Audit

Reuse:

- Keep `CodexCliBackend` as the process execution boundary.
- Keep `CodexTaskAdapter` as the request validation and artifact acceptance
  boundary.
- Reuse the event-shape knowledge from `codex/transcript.py` for message,
  reasoning, tool call, tool output, and error projection.
- Reuse `codex/jsonl.py` behavior for extracting the last agent message, but
  move toward one richer projection surface.

Do not reuse as the primary adapter:

- Do not make `CodexCliLLMProvider` the runtime adapter. It is a provider
  wrapper and deliberately suppresses Codex's autonomous behavior.
- Do not put this into `conversation_loop.py` or `catalog.py`. This first slice
  should not expand the Supervisor conversation contract.
- Do not make agent-group Codex chat own this layer. Agent-group chat is a
  product consumer of Codex state, not the shared runtime contract.

## Architecture

Create a focused package:

```text
src/isotope/integrations/codex/runtime/
  __init__.py
  events.py
  projection.py
  summary.py
  artifacts.py
```

The package exposes one main function:

```python
project_codex_jsonl_stdout(
    *,
    stdout: str,
    stderr: str,
    status: str,
    reason_code: str,
) -> CodexRuntimeProjection
```

The projection contains:

- `events`: normalized `CodexRuntimeEvent` objects.
- `summary`: low-sensitive `CodexRuntimeSummary`.
- `artifact_summary`: payload suitable for a `codex_task_summary` artifact.

This keeps execution, parsing, and presentation separate:

```text
CodexCliBackend
  runs codex exec --json
        |
        v
codex.runtime projection
  interprets stdout/stderr into structured low-sensitive data
        |
        v
CodexTaskAdapter / artifact store / future product surfaces
  consume stable Isotope-shaped results
```

## Runtime Event Contract

`CodexRuntimeEvent` is a small structured event with these public fields:

- `kind`: one of `message`, `reasoning`, `tool_call`, `tool_output`, `error`,
  `status`, or `unknown`.
- `title`: short display title such as `assistant`, `exec_command`, or `error`.
- `text`: low-sensitive text preview.
- `role`: optional role for message events.
- `event_type`: original top-level Codex event type when available.
- `item_type`: original response item type when available.
- `event_index`: zero-based position in the JSONL stream.

It must not expose raw stdout, raw stderr, full argv, full prompt, API keys, or
unbounded tool payloads.

For this first slice, `text` can be a bounded preview. Full raw content remains
inside the existing transcript artifact, controlled by artifact policy.

## Summary Contract

`CodexRuntimeSummary` is the stable low-sensitive report. It contains:

- `status`
- `reason_code`
- `last_agent_message`
- `event_counts`
- `tool_call_count`
- `tool_output_count`
- `error_messages`
- `malformed_event_count`
- `has_agent_message`
- `stderr_preview`

`stderr_preview` is bounded and optional. It exists for quick diagnosis but must
not include the full raw stderr stream.

## Data Flow

`CodexCliBackend.run()` continues to:

1. Execute `codex exec --json`.
2. Capture stdout/stderr with the existing output cap.
3. Build the existing transcript dictionary.
4. Return a `CodexTaskResult`.

The new behavior is:

1. After stdout/stderr capture, call `project_codex_jsonl_stdout(...)`.
2. Use the projection summary to make `CodexTaskResult.summary` more useful
   than a fixed string like `codex cli completed`.
3. Keep the existing `codex_task_transcript` artifact unchanged.
4. When the request artifact policy allows `summary`, also emit a
   `codex_task_summary` artifact with the low-sensitive projection payload.

The first slice does not change the CLI command line, sandbox, approval policy,
or session launch behavior.

## Error Handling

Malformed JSONL lines are not fatal. They increment `malformed_event_count` and
produce either no event or an `unknown` event with bounded metadata.

Codex process status remains authoritative:

- exit code `0` means `completed`;
- timeout means `timeout`;
- non-zero exit means `failed`.

The runtime projection enriches the result; it does not override the process
status.

If projection itself fails unexpectedly, `CodexCliBackend` should still return
the transcript artifact and a controlled failed projection summary. The adapter
layer should not hide the original Codex process outcome.

## Security And Sensitivity

The public runtime summary is low-sensitive by default.

The adapter must not place these fields into summary or public event payloads:

- raw `stdout`
- raw `stderr`
- raw `argv`
- stdin prompt text
- full tool payloads
- API keys or token-like fields
- full file contents

Raw transcript content remains in `codex_task_transcript`, which is already
behind artifact policy.

## Testing

Add focused unit tests under `tests/unit/integrations/codex/runtime/`.

Required coverage:

- projects assistant/user messages from fake JSONL;
- projects reasoning, tool call, tool output, status, and error events;
- extracts `last_agent_message` from the latest assistant message;
- counts malformed JSONL lines without raising;
- bounds text previews and keeps raw stdout/stderr out of public summary;
- builds a `codex_task_summary` artifact payload when requested by the backend
  path;
- keeps existing `CodexCliBackend`, `CodexTaskAdapter`, `CodexCliLLMProvider`,
  and transcript reader tests passing.

Targeted commands after implementation:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/integrations/codex/runtime \
  tests/unit/integrations/codex/test_codex_task_adapter_contract.py \
  tests/integration/codex/test_codex_cli_backend.py \
  tests/unit/llm/test_llm_provider.py \
  tests/unit/integrations/codex/test_codex_transcript.py \
  -q
```

If the changed-surface gate flags this area, also run the command it recommends:

```bash
scripts/dev-eval changed_surface --base origin/main --json
```

## Non-Goals

This first slice does not:

- add `codex.runtime.execute` or any new capability catalog entry;
- change desktop UI;
- change agent-group chat UX;
- change Codex sandbox or approval behavior;
- replace native coding capabilities;
- parse or apply diffs as source-tree changes;
- make Codex the default executor for Supervisor conversation tasks.

## Acceptance Criteria

The first implementation is complete when:

1. There is one shared Codex runtime projection API under
   `src/isotope/integrations/codex/runtime/`.
2. `CodexCliBackend` uses it to produce a richer low-sensitive summary.
3. Existing transcript artifact behavior remains compatible.
4. A summary artifact is emitted only when artifact policy allows `summary`.
5. Tests prove malformed JSONL, tool events, error events, and final assistant
   messages are projected correctly.
6. No user-facing capability or UI contract is added in this slice.

## Implementation Notes

Keep the files small and responsibility-based:

- `events.py` owns dataclasses and event coercion helpers.
- `projection.py` owns JSONL parsing and event projection.
- `summary.py` owns aggregation from events to summary.
- `artifacts.py` owns artifact payload shaping.

Prefer structured dataclasses with `to_dict()` methods over loosely shaped
dictionaries at internal boundaries. Public dicts should be explicit and
low-sensitive.
