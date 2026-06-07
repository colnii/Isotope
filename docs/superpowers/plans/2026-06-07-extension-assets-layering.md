# Extension Assets Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Isotope load skills and MCP servers from project-owned assets, user assets, packaged built-ins, and compatibility paths while preserving progressive skill loading and cold MCP JSON loading.

**Architecture:** Add a shared extension source resolver, then route the existing `skills.*` and `mcp.*` capabilities through that resolver. Source metadata flows into capability results; raw private paths and config files stay out of model-facing observations.

**Tech Stack:** Python 3.13, `importlib.resources`, existing `isotope.extensions.skills`, existing `isotope.extensions.mcp`, existing Supervisor capability loop, pytest.

---

## Current State

The existing implementation already has the right capability IDs and progressive shape:

- `src/isotope/extensions/skills.py` exposes `discover_skills()` and `describe_skill()`.
- `src/isotope/extensions/mcp.py` exposes `load_mcp_server_configs()`, `list_mcp_servers()`, `list_mcp_tools()`, and `call_mcp_tool()`.
- `src/isotope/capabilities/extensions.py` registers `skills.search`, `skills.describe`, `mcp.servers.list`, `mcp.tools.search`, and `mcp.tool.call`.
- `cwd` is already passed as `x-system-input` and hidden from model-visible capacity display in `src/isotope/features/supervisor/conversation_loop.py`.
- Tests already cover progressive skill search/describe and MCP stdio calls under `tests/unit/extensions/`.

This plan keeps those entry points and changes the asset resolution layer behind them.

## Source Contract

Recommended project assets:

```text
isotope.extensions/
  skills/
    <skill-id>/SKILL.md
  mcp/
    servers.json
    servers.d/*.json
```

Packaged built-in assets:

```text
src/isotope/builtin/extensions/
  skills/
    <skill-id>/SKILL.md
  mcp/
    servers.json
    servers.d/*.json
```

Compatibility assets:

```text
.isotope/skills
.isotope/mcp_servers.json
```

Source priority for default discovery:

1. project: `isotope.extensions/`
2. user: `$ISOTOPE_HOME` and `~/.isotope`
3. builtin: `isotope.builtin.extensions`
4. legacy_project: `.isotope/`

Explicit skill roots keep the current override behavior: if `roots` is passed, only those roots are searched and the returned records use `source_kind: explicit`.

Explicit MCP config keeps override behavior: `ISOTOPE_MCP_SERVERS_JSON` and `ISOTOPE_MCP_SERVERS_JSON_FILE` replace the layered default config for that invocation.

## Task 1: Add A Shared Source Resolver

- [ ] Create `src/isotope/extensions/sources.py`.

Define source kinds and lightweight resource helpers:

```python
"""Shared source resolution for Isotope extension assets."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
import os
from pathlib import Path
from typing import Iterable


SOURCE_EXPLICIT = "explicit"
SOURCE_PROJECT = "project"
SOURCE_USER = "user"
SOURCE_BUILTIN = "builtin"
SOURCE_LEGACY_PROJECT = "legacy_project"


@dataclass(frozen=True)
class ExtensionSource:
    source_kind: str
    root: Path | Traversable
    label: str


def skill_sources(
    *,
    cwd: Path | str | None = None,
    explicit_roots: Iterable[Path | str] | None = None,
) -> list[ExtensionSource]:
    if explicit_roots is not None:
        return _existing_path_sources(
            SOURCE_EXPLICIT,
            [Path(root).expanduser() for root in explicit_roots],
        )
    project_root = Path(cwd).expanduser() if cwd is not None else Path.cwd()
    roots: list[ExtensionSource] = []
    roots.extend(
        _existing_path_sources(
            SOURCE_PROJECT,
            [project_root / "isotope.extensions" / "skills"],
        )
    )
    env_roots = os.environ.get("ISOTOPE_SKILL_ROOTS")
    if env_roots:
        roots.extend(
            _existing_path_sources(
                SOURCE_USER,
                [Path(item).expanduser() for item in env_roots.split(os.pathsep) if item],
            )
        )
    isotope_home = os.environ.get("ISOTOPE_HOME")
    user_candidates: list[Path] = []
    if isotope_home:
        user_candidates.append(Path(isotope_home).expanduser() / "skills")
    user_candidates.append(Path.home() / ".isotope" / "skills")
    roots.extend(_existing_path_sources(SOURCE_USER, user_candidates))
    roots.extend(_builtin_sources("skills"))
    roots.extend(
        _existing_path_sources(
            SOURCE_LEGACY_PROJECT,
            [project_root / ".isotope" / "skills"],
        )
    )
    return _unique_sources(roots)


def mcp_file_sources(*, cwd: Path | str | None = None) -> list[ExtensionSource]:
    project_root = Path(cwd).expanduser() if cwd is not None else Path.cwd()
    sources: list[ExtensionSource] = []
    sources.extend(
        _existing_path_sources(
            SOURCE_PROJECT,
            [project_root / "isotope.extensions" / "mcp"],
        )
    )
    isotope_home = os.environ.get("ISOTOPE_HOME")
    user_candidates: list[Path] = []
    if isotope_home:
        user_candidates.append(Path(isotope_home).expanduser() / "mcp_servers.json")
    user_candidates.append(Path.home() / ".isotope" / "mcp_servers.json")
    sources.extend(_existing_path_sources(SOURCE_USER, user_candidates))
    sources.extend(_builtin_sources("mcp"))
    sources.extend(
        _existing_path_sources(
            SOURCE_LEGACY_PROJECT,
            [project_root / ".isotope" / "mcp_servers.json"],
        )
    )
    return _unique_sources(sources)


def iter_named_files(root: Path | Traversable, name: str) -> list[tuple[Path | Traversable, str]]:
    matches: list[tuple[Path | Traversable, str]] = []

    def visit(node: Path | Traversable, relative_prefix: str) -> None:
        try:
            children = sorted(node.iterdir(), key=lambda item: item.name)
        except (FileNotFoundError, NotADirectoryError):
            return
        for child in children:
            relative = f"{relative_prefix}/{child.name}" if relative_prefix else child.name
            if child.is_dir():
                visit(child, relative)
            elif child.is_file() and child.name == name:
                matches.append((child, relative))

    visit(root, "")
    return matches


def read_text(resource: Path | Traversable) -> str:
    return resource.read_text(encoding="utf-8")


def mcp_json_files(source: ExtensionSource) -> list[tuple[Path | Traversable, str]]:
    root = source.root
    if root.is_file():
        return [(root, Path(root.name).as_posix())]
    files: list[tuple[Path | Traversable, str]] = []
    servers_json = root.joinpath("servers.json")
    if servers_json.is_file():
        files.append((servers_json, "servers.json"))
    fragments = root.joinpath("servers.d")
    if fragments.is_dir():
        files.extend(
            (item, f"servers.d/{item.name}")
            for item in sorted(fragments.iterdir(), key=lambda child: child.name)
            if item.is_file() and item.name.endswith(".json")
        )
    return files
```

Implementation notes:

- `_existing_path_sources()` filters missing paths and accepts both directories and files because MCP user config is a file while skill roots are directories.
- `_builtin_sources(subdir)` uses `resources.files("isotope.builtin.extensions").joinpath(subdir)` and returns the source only when the resource exists.
- `_unique_sources()` deduplicates filesystem paths by resolved path. For built-in traversables, deduplicate by `(source_kind, label)`.
- Do not expose `label` directly in capability output; it is for validation messages.

## Task 2: Refactor Skill Discovery To Use Sources

- [ ] Update `src/isotope/extensions/skills.py`.

Replace `source_root: Path` with source metadata and resource-local relative paths:

```python
from isotope.extensions.sources import (
    ExtensionSource,
    iter_named_files,
    read_text,
    skill_sources,
)


@dataclass(frozen=True)
class SkillRecord:
    skill_id: str
    name: str
    description: str
    source_kind: str
    relative_path: str
    skill_resource: Path | Traversable

    def to_metadata(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "relative_path": self.relative_path,
            "readiness": "ready",
            "source_kind": self.source_kind,
        }
```

Use source objects:

```python
def default_skill_roots(*, cwd: Path | str | None = None) -> list[Path]:
    roots: list[Path] = []
    for source in skill_sources(cwd=cwd):
        if isinstance(source.root, Path) and source.root.is_dir():
            roots.append(source.root)
    return roots


def _normalize_sources(
    roots: Iterable[Path | str] | None,
    *,
    cwd: Path | str | None,
) -> list[ExtensionSource]:
    return skill_sources(cwd=cwd, explicit_roots=roots)
```

Load and merge by `skill_id`:

```python
def _load_skill_records(
    sources: list[ExtensionSource],
) -> tuple[list[SkillRecord], list[dict[str, str]]]:
    by_id: dict[str, SkillRecord] = {}
    skipped: list[dict[str, str]] = []
    for source in sources:
        for skill_resource, relative_path in iter_named_files(source.root, "SKILL.md"):
            parsed = _parse_skill_text(read_text(skill_resource))
            if parsed is None:
                skipped.append(
                    {
                        "relative_path": relative_path,
                        "readiness": "invalid_frontmatter",
                        "source_kind": source.source_kind,
                    }
                )
                continue
            skill_id = parsed["name"]
            if skill_id in by_id:
                continue
            by_id[skill_id] = SkillRecord(
                skill_id=skill_id,
                name=parsed["name"],
                description=parsed["description"],
                source_kind=source.source_kind,
                relative_path=relative_path,
                skill_resource=skill_resource,
            )
    return sorted(by_id.values(), key=lambda item: item.skill_id), skipped
```

Change `describe_skill()` to read the selected `skill_resource`:

```python
text = read_text(record.skill_resource)
```

Keep progressive loading intact:

- `discover_skills()` reads only frontmatter and never includes `body`.
- `describe_skill()` returns capped body only for the selected skill.
- `linked_paths` remains filename-only discovery; referenced files are not opened.

Backward compatibility:

- `roots=[...]` still works for Codex compatibility imports.
- `default_skill_roots()` remains available for callers/tests that inspect default path roots, but built-in resources are not represented as `Path` values there.
- Remove `source_root` from public skill metadata and replace it with `source_kind`.

## Task 3: Refactor MCP Config Loading To Merge Layered JSON

- [ ] Update `src/isotope/extensions/mcp.py`.

Extend `McpServerConfig`:

```python
@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    enabled: bool = True
    allowed_tools: tuple[str, ...] = ()
    source_kind: str = "explicit"
```

Add command reference parsing:

```python
def _resolve_command_fields(value: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    command = value.get("command")
    args = value.get("args", [])
    command_ref = value.get("command_ref")
    if command and command_ref:
        raise ValueError("MCP server config must not set both command and command_ref")
    if command_ref is not None:
        if not isinstance(command_ref, str) or not command_ref.startswith("python_module:"):
            raise ValueError("MCP server command_ref must use python_module:<module>")
        module = command_ref.removeprefix("python_module:")
        if not module:
            raise ValueError("MCP server command_ref module must be non-empty")
        return sys.executable, ("-m", module)
    if not isinstance(command, str) or not command:
        raise ValueError("MCP server command must be a non-empty string")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise ValueError("MCP server args must be an array of strings")
    return command, tuple(args)
```

Use source labels for errors and `source_kind` for metadata:

```python
def _mcp_server_configs_from_payload(
    payload: Any,
    *,
    source: str,
    source_kind: str,
) -> list[McpServerConfig]:
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must be a JSON object")
    servers = payload.get("servers")
    if isinstance(servers, (dict, list)):
        payload = servers
    if isinstance(payload, list):
        return [
            _mcp_server_config_from_mapping(
                item.get("server_id"),
                item,
                source_kind=source_kind,
            )
            for item in payload
            if isinstance(item, dict)
        ]
    if not isinstance(payload, dict):
        raise ValueError(f"{source} servers must be an object or array")
    configs: list[McpServerConfig] = []
    for server_id, value in payload.items():
        configs.append(
            _mcp_server_config_from_mapping(
                server_id,
                value,
                source_kind=source_kind,
            )
        )
    return configs
```

Layered loading:

```python
def load_mcp_server_configs(*, cwd: Path | str | None = None) -> list[McpServerConfig]:
    raw = os.environ.get("ISOTOPE_MCP_SERVERS_JSON")
    if raw:
        return _mcp_server_configs_from_payload(
            json.loads(raw),
            source="ISOTOPE_MCP_SERVERS_JSON",
            source_kind=SOURCE_EXPLICIT,
        )
    explicit = os.environ.get("ISOTOPE_MCP_SERVERS_JSON_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        return _load_mcp_json_file(path, source_kind=SOURCE_EXPLICIT)
    merged: dict[str, McpServerConfig] = {}
    for source in reversed(mcp_file_sources(cwd=cwd)):
        for resource, relative_path in mcp_json_files(source):
            for config in _load_mcp_json_resource(
                resource,
                source=f"{source.label}/{relative_path}",
                source_kind=source.source_kind,
            ):
                merged[config.server_id] = config
    return sorted(merged.values(), key=lambda item: item.server_id)
```

The `reversed()` call loads low-priority sources first, then lets higher-priority sources overwrite duplicate `server_id` entries. Within a source, `mcp_json_files()` returns `servers.json` before sorted `servers.d/*.json`, so fragments override the base file inside the same source.

Update server list metadata:

```python
"source_kind": config.source_kind,
```

Keep raw `env`, raw file paths, and JSON payloads out of `list_mcp_servers()`, `list_mcp_tools()`, and `call_mcp_tool()` results.

## Task 4: Add Built-In Package Asset Skeleton

- [ ] Create built-in package directories.

Files:

```text
src/isotope/builtin/__init__.py
src/isotope/builtin/extensions/__init__.py
src/isotope/builtin/extensions/skills/isotope-extension-guide/SKILL.md
src/isotope/builtin/extensions/mcp/servers.json
```

`src/isotope/builtin/extensions/skills/isotope-extension-guide/SKILL.md`:

```md
---
name: isotope-extension-guide
description: Explain how Isotope loads project, user, built-in, and compatibility extension assets.
---

# Isotope Extension Guide

Use this skill when explaining Isotope extension asset locations, source priority, progressive skill loading, or MCP JSON cold loading.

Default project assets live under `isotope.extensions/`. User assets live under `$ISOTOPE_HOME` or `~/.isotope`. Built-in assets are packaged with Isotope. Compatibility project assets under `.isotope/` still load with lower priority.
```

`src/isotope/builtin/extensions/mcp/servers.json`:

```json
{
  "servers": {}
}
```

Update `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"isotope.llm.prompts" = ["*.md"]
"isotope.builtin.extensions" = [
    "skills/**/SKILL.md",
    "mcp/*.json",
    "mcp/servers.d/*.json",
]
```

No built-in MCP server process is added in this slice. The empty packaged JSON verifies the resource path and keeps the package contract ready for a separate server implementation.

## Task 5: Update Capability Observation Projection

- [ ] Update `src/isotope/features/supervisor/conversation_observations.py`.

Ensure skill observations preserve:

- `skill_id`
- `name`
- `description`
- `relative_path`
- `readiness`
- `source_kind`

Ensure MCP server observations preserve:

- `server_id`
- `transport`
- `command_summary`
- `enabled`
- `readiness`
- `allowed_operations`
- `source_kind`

Do not add:

- `source_root`
- absolute config paths
- raw `env`
- JSON-RPC request/response transcripts
- MCP tool call arguments

If the projection code already passes these dictionaries through unchanged except for known safe fields, add `source_kind` to the allowlist. If it currently passes everything through, add a focused allowlist for skill and MCP server records.

## Task 6: Update Documentation

- [ ] Update `docs/current/supervisor-command-reference.md`.

Add a short section under extension capabilities:

````md
Project-owned extension assets should live under `isotope.extensions/`.

Skills:

```text
isotope.extensions/skills/<skill-id>/SKILL.md
```

MCP servers:

```text
isotope.extensions/mcp/servers.json
isotope.extensions/mcp/servers.d/*.json
```

`skills.search` returns metadata only. Use `skills.describe` to load one selected `SKILL.md` body. MCP JSON is cold-loaded on each capability invocation, so edits to `servers.json` or `servers.d/*.json` do not require restarting the Supervisor.

`.isotope/skills` and `.isotope/mcp_servers.json` remain supported as compatibility paths with lower priority.
````

- [ ] If `docs/current/terminology.md` has an extension/capability section, add these terms:

```md
- Extension asset: a project, user, or packaged asset that adds model-facing skills or MCP server definitions.
- Built-in extension asset: an extension asset shipped inside the Isotope Python package.
- Legacy project extension asset: compatibility asset under `.isotope/`.
```

If that file has no relevant section, skip it and keep the docs change scoped to the command reference.

## Task 7: Unit Tests For Skills

- [ ] Update `tests/unit/extensions/test_skills_registry.py`.

Change existing metadata assertions:

```python
assert "source_root" not in skill
assert skill["source_kind"] == "explicit"
```

Add project discovery test:

```python
def test_discover_skills_loads_project_isotope_extensions(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    _write_skill(
        project / "isotope.extensions" / "skills",
        "project",
        name="project-skill",
        description="Project extension skill.",
    )
    monkeypatch.delenv("ISOTOPE_SKILL_ROOTS", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.chdir(project)

    result = discover_skills(query="project")

    assert [skill["skill_id"] for skill in result["skills"]] == ["project-skill"]
    assert result["skills"][0]["source_kind"] == "project"
```

Add built-in discovery test:

```python
def test_discover_skills_loads_packaged_builtin_skill(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ISOTOPE_SKILL_ROOTS", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)

    result = discover_skills(query="extension guide")

    assert result["skills"][0]["skill_id"] == "isotope-extension-guide"
    assert result["skills"][0]["source_kind"] == "builtin"
```

Add override priority test:

```python
def test_project_skill_overrides_builtin_skill_id(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    _write_skill(
        project / "isotope.extensions" / "skills",
        "override",
        name="isotope-extension-guide",
        description="Project override for extension docs.",
    )
    monkeypatch.delenv("ISOTOPE_SKILL_ROOTS", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)

    result = discover_skills(query="extension")
    match = next(skill for skill in result["skills"] if skill["skill_id"] == "isotope-extension-guide")

    assert match["description"] == "Project override for extension docs."
    assert match["source_kind"] == "project"
```

Update the existing default-root test so it expects the new recommended project path and no Codex default:

```python
_write_skill(
    project / "isotope.extensions" / "skills",
    "project",
    name="project-skill",
    description="Project local skill.",
)
result = discover_skills()
skill_ids = [skill["skill_id"] for skill in result["skills"]]
assert "native-skill" in skill_ids
assert "project-skill" in skill_ids
assert "codex-skill" not in skill_ids
```

Keep an explicit Codex compatibility test:

```python
def test_explicit_roots_can_import_codex_skills(tmp_path) -> None:
    codex_root = tmp_path / "codex" / "skills"
    _write_skill(
        codex_root,
        "docx",
        name="codex-docx",
        description="Codex compatibility skill.",
    )

    result = discover_skills(roots=[codex_root])

    assert [skill["skill_id"] for skill in result["skills"]] == ["codex-docx"]
    assert result["skills"][0]["source_kind"] == "explicit"
```

## Task 8: Unit Tests For MCP

- [ ] Update `tests/unit/extensions/test_mcp_client.py`.

Update dataclass equality expectations to include `source_kind` only where necessary. Because the dataclass default is `explicit`, existing helper-created configs can stay unchanged.

Add project cold-load test:

```python
def test_load_mcp_server_configs_from_project_isotope_extensions(monkeypatch, tmp_path) -> None:
    project = tmp_path / "project"
    config_dir = project / "isotope.extensions" / "mcp"
    config_dir.mkdir(parents=True)
    (config_dir / "servers.json").write_text(
        json.dumps(
            {
                "servers": {
                    "echo": {
                        "command": sys.executable,
                        "args": [str(FIXTURE_SERVER)],
                        "allowed_tools": ["echo"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="echo",
            command=sys.executable,
            args=(str(FIXTURE_SERVER),),
            allowed_tools=("echo",),
            source_kind="project",
        )
    ]
```

Add fragment override test:

```python
def test_mcp_servers_d_fragments_override_base_in_sorted_order(monkeypatch, tmp_path) -> None:
    project = tmp_path / "project"
    config_dir = project / "isotope.extensions" / "mcp"
    fragments = config_dir / "servers.d"
    fragments.mkdir(parents=True)
    (config_dir / "servers.json").write_text(
        json.dumps({"servers": {"echo": {"command": "base", "allowed_tools": ["echo"]}}}),
        encoding="utf-8",
    )
    (fragments / "10-first.json").write_text(
        json.dumps({"servers": {"echo": {"command": "first", "allowed_tools": ["echo"]}}}),
        encoding="utf-8",
    )
    (fragments / "20-second.json").write_text(
        json.dumps({"servers": {"echo": {"command": "second", "allowed_tools": ["echo"]}}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.delenv("ISOTOPE_HOME", raising=False)
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    assert configs[0].command == "second"
    assert configs[0].source_kind == "project"
```

Add layered priority test:

```python
def test_project_mcp_config_overrides_user_and_builtin(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    isotope_home = tmp_path / "isotope-home"
    project = tmp_path / "project"
    (isotope_home).mkdir()
    (isotope_home / "mcp_servers.json").write_text(
        json.dumps({"servers": {"echo": {"command": "user", "allowed_tools": ["echo"]}}}),
        encoding="utf-8",
    )
    project_config = project / "isotope.extensions" / "mcp"
    project_config.mkdir(parents=True)
    (project_config / "servers.json").write_text(
        json.dumps({"servers": {"echo": {"command": "project", "allowed_tools": ["echo"]}}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON_FILE", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ISOTOPE_HOME", str(isotope_home))
    monkeypatch.chdir(project)

    configs = load_mcp_server_configs()

    echo = next(config for config in configs if config.server_id == "echo")
    assert echo.command == "project"
    assert echo.source_kind == "project"
```

Add `command_ref` test:

```python
def test_mcp_command_ref_python_module_resolves_to_current_python(monkeypatch) -> None:
    monkeypatch.setenv(
        "ISOTOPE_MCP_SERVERS_JSON",
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "command_ref": "python_module:isotope.builtin_mcp.docs_server",
                        "allowed_tools": ["search_docs"],
                    }
                }
            }
        ),
    )

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="docs",
            command=sys.executable,
            args=("-m", "isotope.builtin_mcp.docs_server"),
            allowed_tools=("search_docs",),
            source_kind="explicit",
        )
    ]
```

Add list metadata assertion:

```python
assert result["servers"][0]["source_kind"] == "explicit"
```

Keep the existing fixture MCP call tests unchanged except for expected list metadata.

## Task 9: Supervisor Capability Regression Tests

- [ ] Update `tests/unit/features/supervisor/test_supervisor_extension_conversation_loop.py`.

Add a test that verifies project-local skills are available through the conversation capability path without the model supplying `roots`:

```python
def test_conversation_loop_loads_project_extension_skills_without_model_roots(
    tmp_path,
) -> None:
    skill_dir = tmp_path / "isotope.extensions" / "skills" / "project-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: project-skill\n"
        "description: Project skill from cwd.\n"
        "---\n\n"
        "# Project Skill\n",
        encoding="utf-8",
    )
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "skills.search",
                    "arguments": {"query": "Project", "limit": 5},
                    "rationale": "Find a project extension skill.",
                }
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已找到项目 extension skill。",
                }
            ),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path,
            user_message="找项目 skill。",
            provider=provider,
            max_turns=3,
        )
    )

    assert events[1].payload["capacity_id"] == "skills.search"
    second_prompt = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    assert "skill_search_result" in second_prompt
    assert "project-skill" in second_prompt
    assert "source_kind" in second_prompt
    assert "project" in second_prompt
```

Do not add this test to `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`; that file is already near the line limit and should not receive new tests.

- [ ] Add the parallel MCP cwd test only if the existing helper can exercise `mcp.servers.list` without launching a stdio server. Otherwise keep MCP cwd coverage in `tests/unit/extensions/test_mcp_client.py`.

## Task 10: Verification

- [ ] Run targeted tests:

```bash
.venv/bin/python -m pytest \
  tests/unit/extensions/test_skills_registry.py \
  tests/unit/extensions/test_mcp_client.py \
  tests/unit/features/supervisor/test_supervisor_extension_conversation_loop.py \
  -q
```

- [ ] Run package-data sanity check:

```bash
.venv/bin/python - <<'PY'
from importlib import resources

root = resources.files("isotope.builtin.extensions")
assert root.joinpath("skills").is_dir()
assert root.joinpath("skills/isotope-extension-guide/SKILL.md").is_file()
assert root.joinpath("mcp/servers.json").is_file()
print("builtin extension resources OK")
PY
```

- [ ] Run all tracked tests if targeted tests pass and the environment is stable:

```bash
git ls-files tests | rg '\.py$' | xargs .venv/bin/python -m pytest -q
```

- [ ] Inspect final status and diff:

```bash
git status --short --branch
git diff --stat
```

## Commit

- [ ] Stage only files related to this implementation.

Expected touched files:

```text
pyproject.toml
docs/current/supervisor-command-reference.md
src/isotope/builtin/__init__.py
src/isotope/builtin/extensions/__init__.py
src/isotope/builtin/extensions/skills/isotope-extension-guide/SKILL.md
src/isotope/builtin/extensions/mcp/servers.json
src/isotope/extensions/sources.py
src/isotope/extensions/skills.py
src/isotope/extensions/mcp.py
src/isotope/features/supervisor/conversation_observations.py
tests/unit/extensions/test_skills_registry.py
tests/unit/extensions/test_mcp_client.py
tests/unit/features/supervisor/test_supervisor_extension_conversation_loop.py
```

If `docs/current/terminology.md` has a relevant section, include it. If not, leave it untouched.

- [ ] Commit:

```bash
git add pyproject.toml docs/current/supervisor-command-reference.md src/isotope/builtin src/isotope/extensions src/isotope/features/supervisor/conversation_observations.py tests/unit/extensions/test_skills_registry.py tests/unit/extensions/test_mcp_client.py tests/unit/features/supervisor/test_supervisor_extension_conversation_loop.py
git commit -m "feat(extensions): load layered skill and mcp assets"
```

Do not merge this branch into `main` until the implementation commit passes verification.
