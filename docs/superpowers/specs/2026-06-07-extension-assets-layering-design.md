# Extension Assets Layering Design

Date: 2026-06-07

## Goal

Make Isotope skills and MCP configuration manageable as first-class Isotope
assets.

The design must support three use cases at the same time:

- project-local extension assets that travel with a repository;
- built-in extension assets shipped inside an Isotope release;
- user-local extension assets and overrides for personal setup.

The design replaces the earlier Codex-centric assumption. Codex skill folders
may still be used as explicit compatibility import roots, but they are not the
default home for Isotope-owned skills.

## Non-Goals

This design does not add automatic installation of third-party MCP servers,
download marketplace content, or execute skill scripts. It only defines how
Isotope finds, merges, packages, and exposes extension assets that already exist
locally or inside the release.

This design does not change the progressive loading rule: `skills.search`
returns metadata only, and `skills.describe` returns the selected `SKILL.md`
body on demand.

## Asset Locations

Use separate paths for source-controlled project assets, packaged release
assets, and user-local overrides.

Project-local assets:

```text
isotope.extensions/
  skills/
    <skill-id>/SKILL.md
  mcp/
    servers.json
    servers.d/*.json
```

Built-in release assets:

```text
src/isotope/builtin/extensions/
  skills/
    <skill-id>/SKILL.md
  mcp/
    servers.json
    servers.d/*.json
```

User-local assets:

```text
$ISOTOPE_HOME/skills
$ISOTOPE_HOME/mcp_servers.json
~/.isotope/skills
~/.isotope/mcp_servers.json
```

Compatibility project-local assets:

```text
.isotope/skills
.isotope/mcp_servers.json
```

`isotope.extensions/` is the recommended repository path. `.isotope/` remains
supported for compatibility and quick local experiments, but it should not be
the primary source-controlled extension directory because the project already
uses `.isotope/` for runtime state, beta packs, logs, and temporary artifacts.

## Source Priority

The resolver uses a deterministic source order:

1. explicit inputs passed to the capability, such as `roots` or explicit MCP
   config file;
2. project assets under `isotope.extensions/`;
3. user-local assets under `$ISOTOPE_HOME` and `~/.isotope`;
4. built-in assets packaged under `src/isotope/builtin/extensions/`;
5. compatibility project assets under `.isotope/`.

Higher-priority sources override lower-priority sources by stable ID:

- skills merge by `skill_id`;
- MCP servers merge by `server_id`.

Each returned skill or server metadata record should include a `source_kind`
field with one of:

- `explicit`;
- `project`;
- `user`;
- `builtin`;
- `legacy_project`.

The model-facing observations should include `source_kind` because it helps the
model explain why a skill or server is available. They should not include raw
absolute paths unless the capability already exposes a low-sensitive path field
for the specific use case.

## Skill Discovery

The skill resolver returns roots from the source priority list. The skill
scanner still parses only `SKILL.md` frontmatter during `skills.search`.

Required frontmatter remains:

```md
---
name: llm2docx
description: Fill Word templates and inspect docx reports.
---
```

`skills.search` returns metadata:

- `skill_id`;
- `name`;
- `description`;
- `relative_path`;
- `readiness`;
- `source_kind`.

`skills.describe` returns the selected metadata plus capped `SKILL.md` body and
linked relative paths. It still must not auto-load referenced files such as
`references/`, `scripts/`, or `assets/`.

Codex skill directories are supported only through explicit compatibility roots:

```json
{"roots": ["/home/lumber/.codex/skills"], "query": "docx"}
```

This keeps Isotope's public default independent from the Codex runtime while
still allowing the user to import existing personal skills when desired.

## MCP Configuration

MCP configuration supports a single JSON file and a directory of JSON fragments.
All files are read on each capability invocation so cold changes take effect
without restarting Isotope.

Supported project layout:

```text
isotope.extensions/mcp/servers.json
isotope.extensions/mcp/servers.d/docs.json
isotope.extensions/mcp/servers.d/browser.json
```

Supported JSON shapes:

```json
{
  "servers": {
    "docs": {
      "command": "node",
      "args": ["docs-server.js"],
      "enabled": true,
      "allowed_tools": ["fetch_doc"]
    }
  }
}
```

```json
{
  "servers": [
    {
      "server_id": "docs",
      "command": "node",
      "args": ["docs-server.js"],
      "allowed_tools": ["fetch_doc"]
    }
  ]
}
```

The existing `ISOTOPE_MCP_SERVERS_JSON` remains as the highest-priority
temporary override. `ISOTOPE_MCP_SERVERS_JSON_FILE` remains an explicit file
override.

When multiple MCP files define the same `server_id`, the higher-priority source
wins. Within the same source layer, later fragment filenames in sorted order win
so local behavior is reproducible.

## Built-In MCP Servers

Built-in MCP entries must not depend on absolute paths that only exist in a
source checkout. They should support a command reference form:

```json
{
  "servers": {
    "builtin-docs": {
      "command_ref": "python_module:isotope.builtin_mcp.docs_server",
      "allowed_tools": ["search_docs", "fetch_doc"]
    }
  }
}
```

At runtime, `command_ref: python_module:<module>` resolves to:

```bash
python -m <module>
```

The public server metadata should still show only a command summary, for
example `python -m isotope.builtin_mcp.docs_server`.

The first implementation only needs this `python_module:` command reference.
Other command reference kinds can be added later if a real packaged asset needs
them.

## Packaging

Package data must include built-in extension assets:

```toml
[tool.setuptools.package-data]
"isotope.llm.prompts" = ["*.md"]
"isotope.builtin.extensions" = [
  "skills/**/SKILL.md",
  "mcp/*.json",
  "mcp/servers.d/*.json",
]
```

The implementation should use `importlib.resources` for built-in assets instead
of filesystem assumptions. This keeps source-tree execution, wheel installs,
and desktop bundle packaging on the same contract.

Desktop bundle packaging can copy or include the same Python package data. The
bundle should not require a separate extension asset path unless the desktop
packager proves Python package data cannot be read at runtime.

## Capability Integration

The public capability IDs remain unchanged:

- `skills.search`;
- `skills.describe`;
- `mcp.servers.list`;
- `mcp.tools.search`;
- `mcp.tool.call`.

The capability input contracts should keep `cwd` as an `x-system-input` so the
Supervisor conversation loop can pass the current project directory without the
model supplying paths. The UI/input summaries should continue hiding `cwd`.

The capability results should expose source metadata but not raw config files,
raw environment variables, absolute private paths, JSON-RPC transcripts, or MCP
tool call arguments.

## Error Handling

Invalid skill files are skipped with a readiness reason, not fatal to the whole
scan.

Invalid MCP JSON should fail the MCP capability with a clear message that
includes the config source label and the validation reason. A malformed MCP file
should not silently disappear because that makes cold-load debugging too hard.

Disabled MCP servers appear in `mcp.servers.list` with `readiness: disabled`.
`mcp.tools.search` and `mcp.tool.call` reject disabled servers before launch.

Tool-level errors remain structured MCP tool results when the MCP protocol call
itself succeeds. Launch, config, or protocol errors remain capability errors.

## Testing

Unit tests should cover:

- project `isotope.extensions/skills` discovery without explicit roots;
- built-in skill discovery through package resources;
- user-local skill override winning over built-in skill with the same
  `skill_id`;
- explicit Codex compatibility roots working without becoming defaults;
- project `isotope.extensions/mcp/servers.json` cold loading;
- `servers.d/*.json` fragment merge order;
- duplicate `server_id` priority across project, user, and built-in layers;
- `command_ref: python_module:<module>` resolution;
- Supervisor conversation calls where the model does not provide roots or MCP
  config paths, but the system `cwd` still makes project assets available.

Smoke or integration coverage should include a fixture MCP stdio server loaded
from project-local JSON and an installed-package/package-data check for built-in
extension assets.

## Migration

Existing `.isotope/skills` and `.isotope/mcp_servers.json` continue to work as
`legacy_project` sources.

Docs and examples should introduce `isotope.extensions/` as the recommended
project-owned path. `.isotope/` should be described as compatibility and local
experiment storage.

No automatic file migration is required in the first implementation. A later
helper can copy `.isotope/skills` into `isotope.extensions/skills` after the
directory contract settles.
