# Skills And MCP Client Bridge Design

Date: 2026-06-04

## Goal

Give Isotope Desktop chat access to local Codex skills and configured MCP
servers through the existing capability system.

The first version should let the model discover extension options, inspect the
specific skill or MCP tool it wants, call an allowed MCP tool, and then continue
the existing Supervisor conversation loop from the returned observation. This
must reuse Isotope's `CapabilityCatalog`, `CapabilityRunner`, and
`run_supervisor_conversation_events(...)` path rather than adding a separate chat
router.

## First Slice

Isotope acts as an MCP client and a local skills discovery host.

The first slice includes:

- skill discovery from configured local Codex skill roots;
- importing metadata for all current Codex skills on this machine as a test
  scenario;
- on-demand skill description by reading one selected `SKILL.md`;
- discovery of explicitly configured MCP stdio servers;
- MCP `tools/list` and `tools/call` for allowed configured servers;
- structured capability start/result observations in Desktop chat.

The first slice does not include:

- installing new skills;
- installing or auto-configuring MCP servers;
- changing long-lived Codex or Isotope local configuration;
- exposing Isotope itself as an MCP server;
- injecting every skill body or every MCP tool schema into the normal chat
  prompt.

## Product Behavior

Desktop chat remains the user-facing entrypoint. The model sees only concise
extension entrypoint capabilities in `capacity_manifest`, such as
`skills.search`, `skills.describe`, `mcp.tools.search`, and `mcp.tool.call`. It
does not receive every local skill's metadata in the baseline prompt. The model
chooses whether to discover skills, describe a specific skill, list MCP servers,
search MCP tools, or call an MCP tool.

The user should not need to know a skill path, MCP protocol method, or
capability ID. The model can use discovery when it lacks domain knowledge, then
continue the task with the selected extension.

Success for local skills means Isotope can scan the current Codex skill
directories into a registry, return matching valid skills as metadata through
`skills.search`, and read a selected skill body only after the model asks for
details through `skills.describe`. This verifies that importing all current
Codex skills does not bloat the baseline conversation prompt.

Success for MCP means Isotope can connect to a configured fixture stdio server,
list tools, call a tool, return structured output or a structured error, and
feed that observation back into the conversation loop.

## Architecture

Add a small `isotope.extensions` package with two focused modules:

- `skills.py`: scans configured roots for `SKILL.md`, parses frontmatter
  `name` and `description`, keeps stable file refs, and reads one selected skill
  on demand.
- `mcp.py`: loads MCP server configuration, launches allowed stdio servers,
  initializes a session, lists tools, and calls tools with JSON arguments.

Add `src/isotope/capabilities/extensions.py` as the capability adapter layer.
It exposes these product capabilities:

- `skills.search`: list or filter local skills by text query.
- `skills.describe`: return the selected skill's metadata and capped body.
- `mcp.servers.list`: show configured MCP servers and readiness.
- `mcp.tools.search`: list or filter tools from a configured server.
- `mcp.tool.call`: call one tool on one configured server.

Register those capabilities in `CapabilityCatalog.default()`. Dispatch them
from `CapabilityRunner.run_capability()` using the same validation and
contract-filtering path as existing capacities.

Do not add fixed intent routing to `conversation_loop`. The prompt should still
tell the model to choose from registered capabilities and report a capability gap
only when no available capability can move the goal forward.

## Data Contracts

Skill search returns structured metadata:

- `skill_id`;
- `name`;
- `description`;
- `source_root`;
- `relative_path`;
- `readiness`.

Skill describe returns the selected metadata plus a capped text body. The body
is only returned after explicit selection and should be capped to prevent prompt
overflow. The returned `SKILL.md` should be treated as current-task skill
context, lower priority than system, developer, repository `AGENTS.md`, and
explicit user instructions.

If a `SKILL.md` references `references/`, `scripts/`, `assets/`, or other
linked files, those files must not be read automatically. They require a later
explicit on-demand read or execution path.

MCP server list returns:

- `server_id`;
- `transport`;
- `command_summary`;
- `enabled`;
- `readiness`;
- `allowed_operations`.

MCP tool search returns:

- `server_id`;
- `tool_name`;
- `title`;
- `description`;
- `input_schema`;
- `readiness`.

MCP tool call returns:

- `status`;
- `server_id`;
- `tool_name`;
- `structured_content` when available;
- capped text content summaries;
- resource links or embedded resources as metadata only;
- `is_error` and a readable error summary for tool-level failures.

## Configuration

Keep configuration explicit and local.

For skills, default roots may include the user's current Codex skill directory
when present, such as `$CODEX_HOME/skills` or `~/.codex/skills`. The import path
is metadata discovery. Invalid or unreadable skills are skipped with a readiness reason
instead of failing the whole scan.

For MCP, use an Isotope-owned local configuration file or environment-provided
mapping. The first implementation should support stdio servers only. Each server
entry must include a stable `server_id`, command, args, optional env, enabled
flag, and allowed tool policy.

## Safety Boundaries

Local skills are discovery and instruction assets, not executable code in this
slice. Isotope reads metadata and selected markdown only.

MCP server commands are executable local processes. Isotope must only run
explicitly configured servers, surface a command summary in metadata, and avoid
one-click installation or implicit command generation.

`mcp.tool.call` must validate that the server and tool are configured and
enabled. Tool errors should be returned inside the capability result when they
come from the tool call, so the model can self-correct. Protocol or launch
failures should still become terminal capacity errors in the Desktop stream.

The baseline `capacity_manifest` must contain only concise extension entrypoint
metadata, not the full local skill registry. Skill metadata appears through
`skills.search`; skill bodies appear through `skills.describe`; referenced skill
files require later on-demand loading. Full MCP result text, secrets, raw
transcripts, raw JSON-RPC logs, and complete embedded resources must not be
injected into ordinary chat context.

## Reuse Audit

Reuse:

- `CapabilityCatalog.default()` as the single discovery source for Desktop chat;
- `CapabilityRunner.list_capabilities()` and `run_capability()` for execution;
- existing input-contract validation and contract-filtered system defaults;
- `run_supervisor_conversation_events(...)` for model agency and observations;
- existing `capacity_start` and `capacity_result` SSE event shape;
- existing capability-gap behavior when no extension can satisfy the task.

Do not reuse:

- Codex's internal skill loader as a runtime dependency, because Isotope only
  needs stable markdown discovery and should not couple to another client
  implementation;
- ad hoc MCP JSON string parsing when the official Python SDK can provide typed
  client/session behavior;
- the older `capacity_provider` pre-pass as the primary route for this feature,
  because the product path is the conversation loop.

## Testing

Targeted tests should cover:

- a fixture skill root with multiple `SKILL.md` files is discovered and filtered;
- all current local Codex skills can be imported into the skill registry in a
  live/local smoke command without injecting every skill metadata entry or body
  into the baseline prompt;
- `skills.describe` returns one selected capped body;
- a fixture MCP stdio server can be listed and called;
- MCP tool-level failure returns a structured capability result with `is_error`;
- unknown server/tool and disabled server/tool are rejected before launch;
- default catalog includes the extension discovery capabilities;
- Desktop conversation manifest exposes extension discovery capabilities without
  dumping all skill bodies or raw MCP schemas;
- a model-selected `mcp.tool.call` produces a `capacity_result` observation and
  the next model turn can answer from that observation.

## Rollout

Implement in an isolated worktree and keep the first commit focused on the
extension bridge.

Suggested order:

1. Add local skill registry and tests.
2. Add MCP stdio client wrapper and fixture server tests.
3. Add extension capabilities and runner dispatch.
4. Add Desktop conversation regression tests.
5. Run targeted unit/integration tests.

Do not merge or clean up the implementation worktree until tests pass and the
user has reviewed the result.
