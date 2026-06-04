# Skills MCP Client Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Isotope Desktop chat discover local Codex skills and call explicitly configured MCP stdio tools through the existing capability system.

**Architecture:** Add a small `isotope.extensions` package for skill registry and MCP client behavior, then adapt it through `isotope.capabilities.extensions`. Register only extension entrypoint capabilities in `CapabilityCatalog`; keep actual skill metadata behind `skills.search` and skill bodies behind `skills.describe`.

**Tech Stack:** Python 3.13, pytest, official `mcp` PyPI package, stdlib `json`/`tomllib`, existing `CapabilityCatalog`, `CapabilityRunner`, and Supervisor conversation loop.

---

## File Structure

- Create `src/isotope/extensions/__init__.py`: package marker and public exports.
- Create `src/isotope/extensions/skills.py`: Codex skill registry, search, describe, and capped body loading.
- Create `src/isotope/extensions/mcp.py`: explicit MCP stdio server config, server/tool discovery, tool call wrapper.
- Create `src/isotope/capabilities/extensions.py`: capability constants, catalog entries, validation, and run adapters.
- Modify `src/isotope/capabilities/catalog.py`: register extension capability definitions from the new module.
- Modify `src/isotope/capabilities/runner.py`: import extension capability handlers, include them in launch planning and execution dispatch.
- Modify `pyproject.toml`: add official `mcp` runtime dependency.
- Create `tests/unit/extensions/test_skills_registry.py`: unit coverage for skill discovery and progressive loading.
- Create `tests/smoke/test_local_codex_skills_import_smoke.py`: local smoke for importing current Codex skills as registry metadata.
- Create `tests/fixtures/mcp_echo_server.py`: fixture stdio MCP server.
- Create `tests/unit/extensions/test_mcp_client.py`: unit coverage for configured MCP server/tool list and call behavior.
- Modify `tests/unit/capabilities/test_capability_runner_thin_shell.py`: catalog and runner dispatch coverage for extension capacities.
- Modify `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`: manifest and observation regression tests.
- Modify `tests/integration/capability/test_capability_runner_cli.py`: CLI manifest includes extension entrypoint capacities.

## Task 1: Local Skill Registry

**Files:**
- Create: `src/isotope/extensions/__init__.py`
- Create: `src/isotope/extensions/skills.py`
- Create: `tests/unit/extensions/test_skills_registry.py`

- [ ] **Step 1: Write the failing skill registry tests**

Create `tests/unit/extensions/test_skills_registry.py`:

```python
from __future__ import annotations

from pathlib import Path

from isotope.extensions.skills import (
    DEFAULT_SKILL_BODY_LIMIT,
    describe_skill,
    discover_skills,
)


def _write_skill(root: Path, relative: str, *, name: str, description: str, body: str = "") -> None:
    skill_dir = root / relative
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "---\n\n"
        f"# {name}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_discover_skills_returns_metadata_without_body(tmp_path) -> None:
    root = tmp_path / "skills"
    _write_skill(
        root,
        "docx",
        name="llm2docx",
        description="Fill Word templates and inspect docx files.",
        body="PRIVATE BODY SHOULD NOT APPEAR",
    )
    _write_skill(
        root,
        "frontend",
        name="frontend-design",
        description="Build production-grade frontend interfaces.",
        body="FRONTEND BODY SHOULD NOT APPEAR",
    )

    result = discover_skills(roots=[root], query="word")

    assert result["kind"] == "skill_search_result"
    assert result["query"] == "word"
    assert result["skill_count"] == 1
    skill = result["skills"][0]
    assert skill["skill_id"] == "llm2docx"
    assert skill["name"] == "llm2docx"
    assert skill["description"] == "Fill Word templates and inspect docx files."
    assert skill["source_root"] == str(root)
    assert skill["relative_path"] == "docx/SKILL.md"
    assert skill["readiness"] == "ready"
    assert "body" not in skill
    assert "PRIVATE BODY SHOULD NOT APPEAR" not in repr(result)


def test_describe_skill_returns_bounded_body_without_linked_files(tmp_path) -> None:
    root = tmp_path / "skills"
    _write_skill(
        root,
        "agent-browser",
        name="agent-browser",
        description="Browser automation for agents.",
        body=(
            "Use this skill for browser automation.\n"
            "Read references/deep-guide.md only when needed.\n"
            + "x" * (DEFAULT_SKILL_BODY_LIMIT + 200)
        ),
    )
    references = root / "agent-browser" / "references"
    references.mkdir()
    (references / "deep-guide.md").write_text("MUST NOT AUTO LOAD", encoding="utf-8")

    result = describe_skill(
        "agent-browser",
        roots=[root],
        max_body_chars=120,
    )

    assert result["kind"] == "skill_description"
    assert result["skill"]["skill_id"] == "agent-browser"
    assert "Use this skill for browser automation." in result["body"]
    assert result["body_truncated"] is True
    assert "MUST NOT AUTO LOAD" not in result["body"]
    assert result["linked_paths"] == ["references/deep-guide.md"]


def test_discover_skills_skips_invalid_skill_without_failing_scan(tmp_path) -> None:
    root = tmp_path / "skills"
    _write_skill(
        root,
        "valid",
        name="valid-skill",
        description="Valid skill.",
    )
    invalid = root / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "SKILL.md").write_text("# Missing frontmatter\n", encoding="utf-8")

    result = discover_skills(roots=[root])

    assert [skill["skill_id"] for skill in result["skills"]] == ["valid-skill"]
    assert result["skipped"] == [
        {
            "relative_path": "invalid/SKILL.md",
            "readiness": "invalid_frontmatter",
        }
    ]
```

- [ ] **Step 2: Run the skill registry tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/extensions/test_skills_registry.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'isotope.extensions'`.

- [ ] **Step 3: Implement the skill registry**

Create `src/isotope/extensions/__init__.py`:

```python
"""Optional extension discovery surfaces for Isotope."""
```

Create `src/isotope/extensions/skills.py`:

```python
"""Read-only progressive discovery for local Codex skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Any, Iterable


DEFAULT_SKILL_BODY_LIMIT = 12000
_FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n?", re.DOTALL)
_LINKED_PATH_RE = re.compile(r"\b(?:references|scripts|assets)/[A-Za-z0-9._/\-]+")


@dataclass(frozen=True)
class SkillRecord:
    skill_id: str
    name: str
    description: str
    source_root: Path
    skill_path: Path

    @property
    def relative_path(self) -> str:
        return self.skill_path.relative_to(self.source_root).as_posix()

    def to_metadata(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "source_root": str(self.source_root),
            "relative_path": self.relative_path,
            "readiness": "ready",
        }


def default_skill_roots() -> list[Path]:
    roots: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home).expanduser() / "skills")
    roots.append(Path.home() / ".codex" / "skills")
    return _unique_existing_roots(roots)


def discover_skills(
    *,
    roots: Iterable[Path | str] | None = None,
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    records, skipped = _load_skill_records(_normalize_roots(roots))
    normalized_query = query.strip().lower()
    matches: list[SkillRecord] = []
    for record in records:
        haystack = " ".join([record.skill_id, record.name, record.description]).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        matches.append(record)
    return {
        "kind": "skill_search_result",
        "query": query,
        "skill_count": len(matches[:limit]),
        "skills": [record.to_metadata() for record in matches[:limit]],
        "skipped": skipped,
    }


def describe_skill(
    skill_id: str,
    *,
    roots: Iterable[Path | str] | None = None,
    max_body_chars: int = DEFAULT_SKILL_BODY_LIMIT,
) -> dict[str, Any]:
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise ValueError("skill_id must be a non-empty string")
    if isinstance(max_body_chars, bool) or not isinstance(max_body_chars, int) or max_body_chars <= 0:
        raise ValueError("max_body_chars must be a positive integer")
    records, _skipped = _load_skill_records(_normalize_roots(roots))
    for record in records:
        if record.skill_id == skill_id:
            text = record.skill_path.read_text(encoding="utf-8")
            body = text[:max_body_chars]
            return {
                "kind": "skill_description",
                "skill": record.to_metadata(),
                "body": body,
                "body_truncated": len(text) > max_body_chars,
                "linked_paths": _linked_paths(text),
            }
    raise ValueError(f"unknown skill_id: {skill_id}")


def _normalize_roots(roots: Iterable[Path | str] | None) -> list[Path]:
    if roots is None:
        return default_skill_roots()
    normalized = [Path(root).expanduser() for root in roots]
    return _unique_existing_roots(normalized)


def _unique_existing_roots(roots: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for root in roots:
        resolved = root.resolve() if root.exists() else root
        if resolved in seen or not root.exists() or not root.is_dir():
            continue
        seen.add(resolved)
        result.append(root)
    return result


def _load_skill_records(roots: list[Path]) -> tuple[list[SkillRecord], list[dict[str, str]]]:
    records: list[SkillRecord] = []
    skipped: list[dict[str, str]] = []
    for root in roots:
        for skill_path in sorted(root.rglob("SKILL.md")):
            parsed = _parse_skill_file(skill_path)
            if parsed is None:
                skipped.append(
                    {
                        "relative_path": skill_path.relative_to(root).as_posix(),
                        "readiness": "invalid_frontmatter",
                    }
                )
                continue
            records.append(
                SkillRecord(
                    skill_id=parsed["name"],
                    name=parsed["name"],
                    description=parsed["description"],
                    source_root=root,
                    skill_path=skill_path,
                )
            )
    records.sort(key=lambda item: item.skill_id)
    return records, skipped


def _parse_skill_file(path: Path) -> dict[str, str] | None:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"')
    name = fields.get("name", "").strip()
    description = fields.get("description", "").strip()
    if not name or not description:
        return None
    return {"name": name, "description": description}


def _linked_paths(text: str) -> list[str]:
    return sorted(set(_LINKED_PATH_RE.findall(text)))
```

- [ ] **Step 4: Run the skill registry tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/extensions/test_skills_registry.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/isotope/extensions/__init__.py src/isotope/extensions/skills.py tests/unit/extensions/test_skills_registry.py
git commit -m "feat(extensions): add progressive skill registry"
```

## Task 2: Local Codex Skills Import Smoke

**Files:**
- Create: `tests/smoke/test_local_codex_skills_import_smoke.py`

- [ ] **Step 1: Write the local smoke test**

Create `tests/smoke/test_local_codex_skills_import_smoke.py`:

```python
from __future__ import annotations

import pytest

from isotope.extensions.skills import default_skill_roots, discover_skills


def test_local_codex_skills_import_as_metadata_without_bodies() -> None:
    roots = default_skill_roots()
    if not roots:
        pytest.skip("no local Codex skill roots on this machine")

    result = discover_skills(roots=roots, limit=200)

    assert result["kind"] == "skill_search_result"
    assert result["skill_count"] >= 1
    assert all("body" not in skill for skill in result["skills"])
    rendered = repr(result)
    assert "## Checklist" not in rendered
    assert "references/" not in rendered or "linked_paths" not in rendered
```

- [ ] **Step 2: Run the local smoke test**

Run:

```bash
.venv/bin/python -m pytest tests/smoke/test_local_codex_skills_import_smoke.py -q
```

Expected: PASS on this machine with current Codex skills, or SKIP only if the local Codex skill root is absent.

- [ ] **Step 3: Commit Task 2**

```bash
git add tests/smoke/test_local_codex_skills_import_smoke.py
git commit -m "test(extensions): smoke import local codex skills"
```

## Task 3: MCP Stdio Client Wrapper

**Files:**
- Modify: `pyproject.toml`
- Create: `src/isotope/extensions/mcp.py`
- Create: `tests/fixtures/mcp_echo_server.py`
- Create: `tests/unit/extensions/test_mcp_client.py`

- [ ] **Step 1: Add the official MCP SDK dependency**

Modify `pyproject.toml`:

```toml
dependencies = ["mcp>=1.0"]
```

- [ ] **Step 2: Write the fixture MCP server**

Create `tests/fixtures/mcp_echo_server.py`:

```python
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("isotope-test-echo")


@mcp.tool()
def echo(text: str) -> dict[str, str]:
    """Echo text for Isotope MCP client tests."""
    return {"echo": text}


@mcp.tool()
def fail(message: str) -> dict[str, str]:
    """Raise a predictable tool-level error."""
    raise ValueError(message)


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 3: Write failing MCP client tests**

Create `tests/unit/extensions/test_mcp_client.py`:

```python
from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest

from isotope.extensions.mcp import (
    McpServerConfig,
    call_mcp_tool,
    load_mcp_server_configs,
    list_mcp_servers,
    list_mcp_tools,
)


FIXTURE_SERVER = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"


def _server(*, enabled: bool = True, allowed_tools: tuple[str, ...] = ("echo", "fail")) -> McpServerConfig:
    return McpServerConfig(
        server_id="echo",
        command=sys.executable,
        args=(str(FIXTURE_SERVER),),
        enabled=enabled,
        allowed_tools=allowed_tools,
    )


def test_list_mcp_servers_returns_command_summary_without_raw_env() -> None:
    result = list_mcp_servers(configs=[_server()])

    assert result == {
        "kind": "mcp_server_list",
        "servers": [
            {
                "server_id": "echo",
                "transport": "stdio",
                "command_summary": f"{sys.executable} {FIXTURE_SERVER}",
                "enabled": True,
                "readiness": "ready",
                "allowed_operations": ["tools/list", "tools/call"],
            }
        ],
    }


def test_list_mcp_tools_uses_configured_stdio_server() -> None:
    result = list_mcp_tools("echo", configs=[_server()])

    assert result["kind"] == "mcp_tool_search_result"
    assert result["server_id"] == "echo"
    tool_names = [tool["tool_name"] for tool in result["tools"]]
    assert "echo" in tool_names
    echo_tool = next(tool for tool in result["tools"] if tool["tool_name"] == "echo")
    assert echo_tool["readiness"] == "ready"
    assert "input_schema" in echo_tool


def test_call_mcp_tool_returns_structured_content() -> None:
    result = call_mcp_tool(
        "echo",
        "echo",
        arguments={"text": "hello"},
        configs=[_server()],
    )

    assert result["kind"] == "mcp_tool_call_result"
    assert result["status"] == "completed"
    assert result["server_id"] == "echo"
    assert result["tool_name"] == "echo"
    assert result["is_error"] is False
    assert result["structured_content"] == {"echo": "hello"}


def test_call_mcp_tool_returns_tool_error_as_result() -> None:
    result = call_mcp_tool(
        "echo",
        "fail",
        arguments={"message": "boom"},
        configs=[_server()],
    )

    assert result["status"] == "completed"
    assert result["is_error"] is True
    assert result["error_summary"]
    assert "boom" in result["error_summary"]


def test_mcp_client_rejects_disabled_server_before_launch() -> None:
    with pytest.raises(PermissionError, match="disabled MCP server"):
        list_mcp_tools("echo", configs=[_server(enabled=False)])


def test_mcp_client_rejects_unallowed_tool_before_call() -> None:
    with pytest.raises(PermissionError, match="not allowlisted"):
        call_mcp_tool(
            "echo",
            "echo",
            arguments={"text": "hello"},
            configs=[_server(allowed_tools=())],
        )


def test_load_mcp_server_configs_from_explicit_json_mapping(monkeypatch) -> None:
    monkeypatch.setenv(
        "ISOTOPE_MCP_SERVERS_JSON",
        json.dumps(
            {
                "echo": {
                    "command": sys.executable,
                    "args": [str(FIXTURE_SERVER)],
                    "enabled": True,
                    "allowed_tools": ["echo"],
                }
            }
        ),
    )

    configs = load_mcp_server_configs()

    assert configs == [
        McpServerConfig(
            server_id="echo",
            command=sys.executable,
            args=(str(FIXTURE_SERVER),),
            enabled=True,
            allowed_tools=("echo",),
        )
    ]
```

- [ ] **Step 4: Run the MCP client tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/extensions/test_mcp_client.py -q
```

Expected: FAIL with missing `isotope.extensions.mcp` or missing implementation.

- [ ] **Step 5: Implement the MCP wrapper**

Create `src/isotope/extensions/mcp.py`:

```python
"""Explicit MCP stdio client wrapper for Isotope extension capabilities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from typing import Any, Iterable, Mapping

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    enabled: bool = True
    allowed_tools: tuple[str, ...] = ()

    def command_summary(self) -> str:
        return " ".join([self.command, *self.args]).strip()


def list_mcp_servers(*, configs: Iterable[McpServerConfig]) -> dict[str, Any]:
    servers = []
    for config in configs:
        _validate_config(config)
        servers.append(
            {
                "server_id": config.server_id,
                "transport": "stdio",
                "command_summary": config.command_summary(),
                "enabled": config.enabled,
                "readiness": "ready" if config.enabled else "disabled",
                "allowed_operations": ["tools/list", "tools/call"] if config.enabled else [],
            }
        )
    return {"kind": "mcp_server_list", "servers": servers}


def load_mcp_server_configs() -> list[McpServerConfig]:
    raw = os.environ.get("ISOTOPE_MCP_SERVERS_JSON")
    if not raw:
        return []
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("ISOTOPE_MCP_SERVERS_JSON must be a JSON object")
    configs: list[McpServerConfig] = []
    for server_id, value in payload.items():
        if not isinstance(server_id, str) or not server_id:
            raise ValueError("MCP server id must be a non-empty string")
        if not isinstance(value, dict):
            raise ValueError("MCP server config must be an object")
        command = value.get("command")
        args = value.get("args", [])
        env = value.get("env")
        enabled = value.get("enabled", True)
        allowed_tools = value.get("allowed_tools", [])
        if not isinstance(command, str) or not command:
            raise ValueError("MCP server command must be a non-empty string")
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise ValueError("MCP server args must be an array of strings")
        if env is not None and not isinstance(env, dict):
            raise ValueError("MCP server env must be an object")
        if not isinstance(enabled, bool):
            raise ValueError("MCP server enabled must be a bool")
        if not isinstance(allowed_tools, list) or not all(
            isinstance(item, str) for item in allowed_tools
        ):
            raise ValueError("MCP server allowed_tools must be an array of strings")
        configs.append(
            McpServerConfig(
                server_id=server_id,
                command=command,
                args=tuple(args),
                env=env,
                enabled=enabled,
                allowed_tools=tuple(allowed_tools),
            )
        )
    return configs


def list_mcp_tools(
    server_id: str,
    *,
    configs: Iterable[McpServerConfig],
    query: str = "",
) -> dict[str, Any]:
    config = _find_enabled_server(server_id, configs)
    tools = asyncio.run(_list_tools(config))
    normalized_query = query.strip().lower()
    visible = []
    for tool in tools:
        tool_name = str(tool.get("tool_name", ""))
        haystack = " ".join(
            [
                tool_name,
                str(tool.get("title", "")),
                str(tool.get("description", "")),
            ]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        if config.allowed_tools and tool_name not in config.allowed_tools:
            tool["readiness"] = "not_allowlisted"
        visible.append(tool)
    return {
        "kind": "mcp_tool_search_result",
        "server_id": server_id,
        "query": query,
        "tools": visible,
    }


def call_mcp_tool(
    server_id: str,
    tool_name: str,
    *,
    arguments: Mapping[str, Any] | None = None,
    configs: Iterable[McpServerConfig],
) -> dict[str, Any]:
    config = _find_enabled_server(server_id, configs)
    if config.allowed_tools and tool_name not in config.allowed_tools:
        raise PermissionError(f"MCP tool is not allowlisted: {tool_name}")
    return asyncio.run(_call_tool(config, tool_name, dict(arguments or {})))


async def _list_tools(config: McpServerConfig) -> list[dict[str, Any]]:
    async with stdio_client(_stdio_params(config)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()
            result = []
            for tool in response.tools:
                result.append(
                    {
                        "server_id": config.server_id,
                        "tool_name": tool.name,
                        "title": getattr(tool, "title", None) or tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema or {},
                        "readiness": "ready",
                    }
                )
            return result


async def _call_tool(
    config: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    async with stdio_client(_stdio_params(config)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.call_tool(tool_name, arguments)
            return _tool_call_result(config.server_id, tool_name, response)


def _tool_call_result(server_id: str, tool_name: str, response: Any) -> dict[str, Any]:
    structured = getattr(response, "structuredContent", None)
    is_error = bool(getattr(response, "isError", False))
    text_parts = []
    for item in getattr(response, "content", []) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text:
            text_parts.append(text[:2000])
    return {
        "kind": "mcp_tool_call_result",
        "status": "completed",
        "server_id": server_id,
        "tool_name": tool_name,
        "structured_content": structured,
        "content_summary": text_parts[:5],
        "is_error": is_error,
        "error_summary": "\n".join(text_parts[:2]) if is_error else "",
    }


def _stdio_params(config: McpServerConfig) -> StdioServerParameters:
    return StdioServerParameters(
        command=config.command,
        args=list(config.args),
        env=dict(config.env or {}),
    )


def _find_enabled_server(
    server_id: str,
    configs: Iterable[McpServerConfig],
) -> McpServerConfig:
    for config in configs:
        _validate_config(config)
        if config.server_id != server_id:
            continue
        if not config.enabled:
            raise PermissionError(f"disabled MCP server: {server_id}")
        return config
    raise ValueError(f"unknown MCP server: {server_id}")


def _validate_config(config: McpServerConfig) -> None:
    if not isinstance(config.server_id, str) or not config.server_id:
        raise ValueError("server_id must be a non-empty string")
    if not isinstance(config.command, str) or not config.command:
        raise ValueError("command must be a non-empty string")
    if not isinstance(config.args, tuple):
        raise ValueError("args must be a tuple")
```

- [ ] **Step 6: Run the MCP client tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/extensions/test_mcp_client.py -q
```

Expected: PASS. If the official SDK shape differs, adjust only `src/isotope/extensions/mcp.py` to the installed SDK API and keep the tests' Isotope-facing contract unchanged.

- [ ] **Step 7: Commit Task 3**

```bash
git add pyproject.toml src/isotope/extensions/mcp.py tests/fixtures/mcp_echo_server.py tests/unit/extensions/test_mcp_client.py
git commit -m "feat(extensions): add mcp stdio client wrapper"
```

## Task 4: Extension Capabilities And Runner Dispatch

**Files:**
- Create: `src/isotope/capabilities/extensions.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/runner.py`
- Modify: `tests/unit/capabilities/test_capability_runner_thin_shell.py`
- Modify: `tests/integration/capability/test_capability_runner_cli.py`

- [ ] **Step 1: Write failing runner tests**

Append to `tests/unit/capabilities/test_capability_runner_thin_shell.py`:

```python
def test_runner_discovers_extension_entrypoint_capabilities():
    runner = _runner()

    ids = _ids(runner.list_capabilities())

    assert "skills.search" in ids
    assert "skills.describe" in ids
    assert "mcp.servers.list" in ids
    assert "mcp.tools.search" in ids
    assert "mcp.tool.call" in ids


def test_runner_executes_skills_search_with_explicit_roots(tmp_path):
    root = tmp_path / "skills"
    skill_dir = root / "frontend"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: frontend-design\n"
        "description: Build production-grade frontend interfaces.\n"
        "---\n\n"
        "# frontend-design\n",
        encoding="utf-8",
    )
    runner = _runner()

    result = runner.run_capability(
        "skills.search",
        inputs={"roots": [str(root)], "query": "frontend"},
    )

    assert result["status"] == "completed"
    assert result["runner_kind"] == "extension_skill_registry"
    assert result["skills"][0]["skill_id"] == "frontend-design"
    assert "body" not in result["skills"][0]


def test_runner_executes_skills_describe_with_bounded_body(tmp_path):
    root = tmp_path / "skills"
    skill_dir = root / "docx"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: llm2docx\n"
        "description: Fill Word templates.\n"
        "---\n\n"
        "# llm2docx\n\n"
        "Use this skill for docx work.\n",
        encoding="utf-8",
    )
    runner = _runner()

    result = runner.run_capability(
        "skills.describe",
        inputs={"roots": [str(root)], "skill_id": "llm2docx", "max_body_chars": 40},
    )

    assert result["status"] == "completed"
    assert result["runner_kind"] == "extension_skill_registry"
    assert result["skill"]["skill_id"] == "llm2docx"
    assert "Use this skill" in result["body"]
```

- [ ] **Step 2: Update the CLI manifest test expectation**

Modify `tests/integration/capability/test_capability_runner_cli.py` inside `test_capability_runner_cli_lists_capabilities_as_json`:

```python
    assert set(capability_ids).issuperset({
        "approval.tool.runner",
        "artifact.changed_files",
        "artifact.diff_summary",
        "artifact.review",
        "code.read",
        "code.search",
        "coding_task.execute",
        "external.snapshot.review",
        "mcp.servers.list",
        "mcp.tool.call",
        "mcp.tools.search",
        "memory.promotion.preview",
        "memory.query",
        "research.promote",
        "research.search",
        "screen.report",
        "skills.describe",
        "skills.search",
        "supervisor.codex_operation",
        "supervisor.goal_plan",
        "supervisor.integration_review",
        "supervisor.request_context",
        "supervisor.worker_review",
    })
```

- [ ] **Step 3: Run runner tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_extension_entrypoint_capabilities \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_skills_search_with_explicit_roots \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_skills_describe_with_bounded_body \
  tests/integration/capability/test_capability_runner_cli.py::test_capability_runner_cli_lists_capabilities_as_json \
  -q
```

Expected: FAIL because extension capabilities are not registered.

- [ ] **Step 4: Implement extension capability adapters**

Create `src/isotope/capabilities/extensions.py`:

```python
"""Capability adapters for local skills and configured MCP servers."""

from __future__ import annotations

from typing import Any, Mapping

from .catalog import Capability
from isotope.extensions.skills import describe_skill, discover_skills


SKILLS_SEARCH_CAPABILITY = "skills.search"
SKILLS_DESCRIBE_CAPABILITY = "skills.describe"
MCP_SERVERS_LIST_CAPABILITY = "mcp.servers.list"
MCP_TOOLS_SEARCH_CAPABILITY = "mcp.tools.search"
MCP_TOOL_CALL_CAPABILITY = "mcp.tool.call"
EXTENSION_CAPABILITIES = {
    SKILLS_SEARCH_CAPABILITY,
    SKILLS_DESCRIBE_CAPABILITY,
    MCP_SERVERS_LIST_CAPABILITY,
    MCP_TOOLS_SEARCH_CAPABILITY,
    MCP_TOOL_CALL_CAPABILITY,
}


def extension_capability_definitions() -> list[Capability]:
    return [
        Capability(
            capability_id=SKILLS_SEARCH_CAPABILITY,
            title="Skills Search",
            description="Search local Codex skills by metadata without loading skill bodies.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("skills", "extensions", "discovery"),
            input_contract={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query.", "default": ""},
                    "roots": {"type": "array", "items": {"type": "string"}, "description": "Optional explicit skill roots."},
                    "limit": {"type": "integer", "description": "Maximum returned skills.", "default": 20},
                },
            },
            output_contract={"type": "object", "fields": ["status", "runner_kind", "skills", "skill_count", "skipped"]},
            safety_boundaries=("read_only_skill_metadata", "no_skill_body_in_manifest", "no_code_execution"),
            default_enabled=True,
            network_required=False,
        ),
        Capability(
            capability_id=SKILLS_DESCRIBE_CAPABILITY,
            title="Skills Describe",
            description="Load one selected Codex SKILL.md body with bounded content.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("skills", "extensions", "progressive-disclosure"),
            input_contract={
                "type": "object",
                "required": ["skill_id"],
                "properties": {
                    "skill_id": {"type": "string", "description": "Skill id returned by skills.search."},
                    "roots": {"type": "array", "items": {"type": "string"}, "description": "Optional explicit skill roots."},
                    "max_body_chars": {"type": "integer", "description": "Maximum returned SKILL.md characters.", "default": 12000},
                },
            },
            output_contract={"type": "object", "fields": ["status", "runner_kind", "skill", "body", "body_truncated", "linked_paths"]},
            safety_boundaries=("read_only_selected_skill_body", "bounded_body", "no_linked_file_autoload", "no_code_execution"),
            default_enabled=True,
            network_required=False,
        ),
    ]


def is_extension_capability(capability_id: str) -> bool:
    return capability_id in EXTENSION_CAPABILITIES


def validate_extension_inputs(*, capability_id: str, inputs: Mapping[str, Any], missing_inputs: list[str]) -> None:
    if capability_id not in EXTENSION_CAPABILITIES:
        return
    if missing_inputs:
        return
    if "roots" in inputs and not isinstance(inputs["roots"], list):
        raise ValueError("roots must be an array")


def run_extension_capability(capability_id: str, *, inputs: Mapping[str, Any]) -> dict[str, Any]:
    if capability_id == SKILLS_SEARCH_CAPABILITY:
        result = discover_skills(
            roots=inputs.get("roots"),
            query=str(inputs.get("query", "")),
            limit=int(inputs.get("limit", 20)),
        )
        return {"status": "completed", "runner_kind": "extension_skill_registry", **result}
    if capability_id == SKILLS_DESCRIBE_CAPABILITY:
        result = describe_skill(
            str(inputs["skill_id"]),
            roots=inputs.get("roots"),
            max_body_chars=int(inputs.get("max_body_chars", 12000)),
        )
        return {"status": "completed", "runner_kind": "extension_skill_registry", **result}
    raise PermissionError(f"extension capability is not implemented yet: {capability_id}")
```

Only include skill capabilities in this step. MCP capabilities are registered in Task 5 after the MCP config contract is wired through runner tests.

- [ ] **Step 5: Register extension capabilities in the catalog**

Modify `src/isotope/capabilities/catalog.py`:

```python
from .extensions import extension_capability_definitions
```

Inside `CapabilityCatalog.default()`, append definitions near other product candidate capabilities:

```python
                *extension_capability_definitions(),
```

- [ ] **Step 6: Dispatch extension capabilities in the runner**

Modify `src/isotope/capabilities/runner.py` imports:

```python
from .extensions import (
    is_extension_capability,
    run_extension_capability,
    validate_extension_inputs,
)
```

In `plan_capability_run(...)`, add validation and allowlisting checks beside other capability groups:

```python
        validate_extension_inputs(
            capability_id=capability_id,
            inputs=input_mapping,
            missing_inputs=missing_inputs,
        )
```

And include `and not is_extension_capability(capability_id)` in the not-allowlisted branch.

In `run_capability(...)`, add the same validator, include `or is_extension_capability(capability_id)` in the first capability group condition, and dispatch before demo scenarios:

```python
        if is_extension_capability(capability_id):
            return run_extension_capability(capability_id, inputs=input_mapping)
```

- [ ] **Step 7: Run extension runner tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_extension_entrypoint_capabilities \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_skills_search_with_explicit_roots \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_skills_describe_with_bounded_body \
  tests/integration/capability/test_capability_runner_cli.py::test_capability_runner_cli_lists_capabilities_as_json \
  -q
```

Expected: `test_runner_discovers_extension_entrypoint_capabilities` still FAILS for MCP ids until Task 5. The two skill runner tests should PASS. Commit only after Task 5 makes the full set pass.

## Task 5: MCP Capabilities And Conversation Regression

**Files:**
- Modify: `src/isotope/capabilities/extensions.py`
- Modify: `tests/unit/capabilities/test_capability_runner_thin_shell.py`
- Modify: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Add runner tests for MCP capability dispatch**

Append to `tests/unit/capabilities/test_capability_runner_thin_shell.py`:

```python
def test_runner_plans_mcp_capabilities_as_missing_inputs():
    runner = _runner()

    plan = runner.plan_capability_run("mcp.tool.call", inputs={})

    assert plan["status"] == "missing_inputs"
    assert plan["missing_inputs"] == ["server_id", "tool_name"]
    assert plan["can_launch"] is False


def test_runner_rejects_mcp_tool_call_without_config(monkeypatch):
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    runner = _runner()

    with pytest.raises(ValueError, match="unknown MCP server"):
        runner.run_capability(
            "mcp.tool.call",
            inputs={"server_id": "missing", "tool_name": "echo", "arguments": {}},
        )


def test_runner_executes_mcp_tool_call_from_explicit_env_config(tmp_path, monkeypatch):
    import json
    import sys

    fixture_server = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"
    monkeypatch.setenv(
        "ISOTOPE_MCP_SERVERS_JSON",
        json.dumps(
            {
                "echo": {
                    "command": sys.executable,
                    "args": [str(fixture_server)],
                    "enabled": True,
                    "allowed_tools": ["echo"],
                }
            }
        ),
    )
    runner = _runner()

    result = runner.run_capability(
        "mcp.tool.call",
        inputs={
            "server_id": "echo",
            "tool_name": "echo",
            "arguments": {"text": "hello from runner"},
        },
    )

    assert result["status"] == "completed"
    assert result["runner_kind"] == "extension_mcp_client"
    assert result["server_id"] == "echo"
    assert result["tool_name"] == "echo"
    assert result["structured_content"] == {"echo": "hello from runner"}
    assert result["is_error"] is False
```

- [ ] **Step 2: Add Desktop conversation manifest regression**

Append to `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`:

```python
def test_conversation_loop_manifest_exposes_extension_entrypoints_without_skill_registry(
    tmp_path,
) -> None:
    provider = RecordingConversationProvider(["你好，我在。"])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path,
            cwd=tmp_path / "repo",
            user_message="我需要处理 Word 文档",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert '"capability_id": "skills.search"' in system_prompt
    assert '"capability_id": "skills.describe"' in system_prompt
    assert '"capability_id": "mcp.tool.call"' in system_prompt
    assert "llm2docx" not in system_prompt
    assert "SKILL.md" not in system_prompt
    assert "## Checklist" not in system_prompt
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_plans_mcp_capabilities_as_missing_inputs \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_rejects_mcp_tool_call_without_config \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_manifest_exposes_extension_entrypoints_without_skill_registry \
  -q
```

Expected: FAIL because MCP capability metadata and dispatch are not complete.

- [ ] **Step 4: Complete MCP capability definitions and dispatch**

Extend `src/isotope/capabilities/extensions.py`:

```python
from isotope.extensions.mcp import (
    call_mcp_tool,
    load_mcp_server_configs,
    list_mcp_servers,
    list_mcp_tools,
)


def _mcp_capability_definitions() -> list[Capability]:
    return [
        Capability(
            capability_id=MCP_SERVERS_LIST_CAPABILITY,
            title="MCP Servers List",
            description="List explicitly configured MCP stdio servers and readiness.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("mcp", "extensions", "discovery"),
            input_contract={"type": "object"},
            output_contract={"type": "object", "fields": ["status", "runner_kind", "servers"]},
            safety_boundaries=("configured_servers_only", "command_summary_only", "no_tool_call"),
            default_enabled=True,
            network_required=False,
        ),
        Capability(
            capability_id=MCP_TOOLS_SEARCH_CAPABILITY,
            title="MCP Tools Search",
            description="List or search tools from one explicitly configured MCP stdio server.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("mcp", "tools", "extensions", "discovery"),
            input_contract={
                "type": "object",
                "required": ["server_id"],
                "properties": {
                    "server_id": {"type": "string", "description": "Configured MCP server id."},
                    "query": {"type": "string", "description": "Optional tool search query.", "default": ""},
                },
            },
            output_contract={"type": "object", "fields": ["status", "runner_kind", "tools"]},
            safety_boundaries=("configured_servers_only", "allowed_tool_metadata", "no_tool_call"),
            default_enabled=True,
            network_required=False,
        ),
        Capability(
            capability_id=MCP_TOOL_CALL_CAPABILITY,
            title="MCP Tool Call",
            description="Call one allowlisted tool on one explicitly configured MCP stdio server.",
            maturity="v0.2",
            shelf="product_candidate",
            domain_tags=("mcp", "tools", "extensions", "execution"),
            input_contract={
                "type": "object",
                "required": ["server_id", "tool_name"],
                "properties": {
                    "server_id": {"type": "string", "description": "Configured MCP server id."},
                    "tool_name": {"type": "string", "description": "Allowlisted MCP tool name."},
                    "arguments": {"type": "object", "description": "JSON arguments for the MCP tool.", "default": {}},
                },
            },
            output_contract={"type": "object", "fields": ["status", "runner_kind", "structured_content", "content_summary", "is_error"]},
            safety_boundaries=("configured_servers_only", "allowlisted_tools_only", "bounded_result_summary"),
            default_enabled=True,
            network_required=False,
        ),
    ]
```

Update `extension_capability_definitions()` to return skill definitions plus `_mcp_capability_definitions()`.

Use explicit local MCP configuration from `ISOTOPE_MCP_SERVERS_JSON`:

```python
    if capability_id == MCP_SERVERS_LIST_CAPABILITY:
        return {
            "status": "completed",
            "runner_kind": "extension_mcp_client",
            **list_mcp_servers(configs=load_mcp_server_configs()),
        }
    if capability_id == MCP_TOOLS_SEARCH_CAPABILITY:
        return {
            "status": "completed",
            "runner_kind": "extension_mcp_client",
            **list_mcp_tools(
                str(inputs["server_id"]),
                configs=load_mcp_server_configs(),
                query=str(inputs.get("query", "")),
            ),
        }
    if capability_id == MCP_TOOL_CALL_CAPABILITY:
        return {
            "status": "completed",
            "runner_kind": "extension_mcp_client",
            **call_mcp_tool(
                str(inputs["server_id"]),
                str(inputs["tool_name"]),
                arguments=inputs.get("arguments") if isinstance(inputs.get("arguments"), Mapping) else {},
                configs=load_mcp_server_configs(),
            ),
        }
```

This keeps configuration explicit and local without installing or auto-discovering MCP servers.

- [ ] **Step 5: Run runner and conversation tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_extension_entrypoint_capabilities \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_skills_search_with_explicit_roots \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_skills_describe_with_bounded_body \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_plans_mcp_capabilities_as_missing_inputs \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_rejects_mcp_tool_call_without_config \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_executes_mcp_tool_call_from_explicit_env_config \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_manifest_exposes_extension_entrypoints_without_skill_registry \
  tests/integration/capability/test_capability_runner_cli.py::test_capability_runner_cli_lists_capabilities_as_json \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit Tasks 4 and 5 together**

```bash
git add \
  src/isotope/capabilities/extensions.py \
  src/isotope/capabilities/catalog.py \
  src/isotope/capabilities/runner.py \
  tests/unit/capabilities/test_capability_runner_thin_shell.py \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py \
  tests/integration/capability/test_capability_runner_cli.py
git commit -m "feat(capabilities): expose skills and mcp extension entrypoints"
```

## Task 6: Verification And Documentation Check

**Files:**
- Modify only if tests expose a real contract mismatch.

- [ ] **Step 1: Run focused unit tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/extensions/test_skills_registry.py \
  tests/unit/extensions/test_mcp_client.py \
  tests/unit/capabilities/test_capability_runner_thin_shell.py \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run integration and smoke checks**

Run:

```bash
.venv/bin/python -m pytest \
  tests/integration/capability/test_capability_runner_cli.py::test_capability_runner_cli_lists_capabilities_as_json \
  tests/smoke/test_local_codex_skills_import_smoke.py \
  -q
```

Expected: PASS, with the smoke test allowed to SKIP only when no local Codex skill root exists.

- [ ] **Step 3: Run catalog search manually**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.capabilities.runner search skills --json
```

Expected: JSON includes `skills.search` and `skills.describe`, not the full local skill registry.

- [ ] **Step 4: Inspect status and staged diff**

Run:

```bash
git status --short --branch
git diff --stat
```

Expected: clean status after prior commits, or only intentional changes from verification fixes.

- [ ] **Step 5: Commit verification fixes if needed**

Only if Step 1 or Step 2 required code/test fixes:

```bash
git add <fixed-files>
git commit -m "fix(extensions): align skills mcp bridge verification"
```

- [ ] **Step 6: Report implementation worktree state**

Run:

```bash
git log --oneline --max-count=6
git status --short --branch
```

Expected: implementation branch contains focused commits and has no unexpected dirty files.
