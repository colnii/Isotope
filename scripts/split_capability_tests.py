#!/usr/bin/env python3
"""Split tests/unit/capabilities/test_capability_runner_thin_shell.py into domain files.

Approach: extract each test function with its body only (not gap content).
Post-process to include decorators that belong to each test.
"""
import re
from pathlib import Path
from collections import defaultdict

SRC = Path("tests/unit/capabilities/test_capability_runner_thin_shell.py")
OUT = Path("tests/unit/capabilities")

COMMON_IMPORTS = """\
import importlib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from isotope.capabilities.catalog import Capability, CapabilityCatalog
from isotope.features.supervisor.registry import (
    ManagedCodexRecord,
    append_managed_record,
    default_registry_path,
)
from isotope.platform.schemas.memory import MemoryRecord
from isotope.workspace.artifacts import ArtifactStore


FORBIDDEN_RESULT_KEYS = {
    "api_key",
    "content",
    "full_content",
    "local_path",
    "prompt",
    "raw_content",
    "transcript",
}


def _runner_module():
    return importlib.import_module("isotope.capabilities.runner")


def _runner(*, catalog=None):
    return _runner_module().CapabilityRunner(
        catalog=catalog or CapabilityCatalog.default()
    )


def _ids(entries):
    return [entry["capability_id"] for entry in entries]


def _walk_mapping(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mapping(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mapping(child)


def _write_memory_record(memory_dir, record):
    from dataclasses import asdict
    (memory_dir / f"{record.memory_id}.json").write_text(
        json.dumps(asdict(record), sort_keys=True),
        encoding="utf-8",
    )


def _capability(capability_id, shelf, **overrides):
    data = {
        "capability_id": capability_id,
        "title": capability_id.replace(".", " ").title(),
        "description": f"{capability_id} capability metadata.",
        "maturity": "v0.2",
        "shelf": shelf,
        "domain_tags": tuple(capability_id.split(".")),
        "input_contract": {"type": "object"},
        "output_contract": {"type": "object"},
        "safety_boundaries": ("public_metadata_manifest_only",),
        "default_enabled": True,
        "required_env": (),
        "network_required": False,
        "provider": None,
        "model": None,
    }
    data.update(overrides)
    return Capability(**data)
"""

GIT_HELPERS = """\
import subprocess
from pathlib import Path


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    (repo / "app.py").write_text("print('old')\\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    return repo
"""


def group_test(name: str) -> str:
    domain = name.removeprefix("test_")
    if domain.startswith("capability_runner_module"):
        return "test_core"
    if domain.startswith("runner_rejects_malformed"):
        return "test_core"
    if domain.startswith("runner_list_"):
        return "test_core"
    if domain.startswith("runner_discovers_extension"):
        return "test_core"
    if domain.startswith("runner_describe_"):
        return "test_core"
    if domain.startswith("runner_plans_"):
        return "test_core"
    if domain.startswith("runner_rejects_mcp"):
        return "test_mcp"
    if domain.startswith("runner_executes_skills"):
        return "test_mcp"
    if domain.startswith("runner_executes_mcp"):
        return "test_mcp"
    if domain.startswith("project_status_"):
        return "test_supervisor"
    if domain.startswith("supervisor_"):
        return "test_supervisor"
    if domain.startswith("isotope_self_repair"):
        return "test_supervisor"
    if domain.startswith("memory_"):
        return "test_memory"
    if domain.startswith("screen_"):
        return "test_screen"
    if domain.startswith("research_"):
        return "test_research"
    if domain.startswith("workspace_"):
        return "test_workspace"
    if domain.startswith("coding_"):
        return "test_coding"
    if domain.startswith("runner_rejects_direct_coding"):
        return "test_coding"
    if domain.startswith("runner_executes_native_coding"):
        return "test_coding"
    if domain.startswith("runner_applies_reviewed"):
        return "test_coding"
    if domain.startswith("runner_builds_coding"):
        return "test_coding"
    if domain.startswith("runner_applies_unified"):
        return "test_coding"
    if domain.startswith("runner_discovers_supervisor"):
        return "test_supervisor"
    if domain.startswith("runner_discovers_memory"):
        return "test_memory"
    if domain.startswith("runner_discovers_screen"):
        return "test_screen"
    if domain.startswith("runner_discovers_research"):
        return "test_research"
    if domain.startswith("runner_discovers_coding"):
        return "test_coding"
    if domain.startswith("runner_discovers_workspace"):
        return "test_workspace"
    if domain.startswith("runner_discovers_isotope"):
        return "test_supervisor"
    if domain.startswith("runner_runs_workspace"):
        return "test_workspace"
    if domain.startswith("runner_runs_allowlisted"):
        return "test_core"
    if domain.startswith("runner_executes_allowlisted"):
        return "test_core"
    if domain.startswith("runner_rejects_artifact"):
        return "test_core"
    if domain.startswith("runner_archive_"):
        return "test_core"
    if domain.startswith("runner_advise_"):
        return "test_core"
    return "test_core"


def _find_test_body(lines, start_idx):
    """Find the actual end of a test function body.
    
    Walk forward from start_idx. The body ends when we hit
    a line at column 0 that starts with 'def ', '@', or is
    a blank line followed by such a line.
    """
    # Start at the def line
    dec_start = start_idx
    found_pytest_at = None
    depth = 0
    i = start_idx
    while i > 0:
        prev = lines[i - 1]
        raw_stripped = prev.lstrip()
        col0 = prev[0] not in (' ', '\t')

        # Track bracket depth (reversed: going backward, close means enter, open means exit)
        for ch in prev:
            if ch in ')]}':
                depth += 1
            elif ch in '([{':
                depth -= 1

        # Previous top-level def → stop
        if col0 and raw_stripped.startswith('def '):
            break

        # Found @pytest decorator
        if raw_stripped.startswith('@pytest.mark.parametrize'):
            found_pytest_at = i - 1
            break

        # Blank lines
        if not raw_stripped.strip():
            i -= 1
            continue

        # Inside parametrize arguments (bracket depth > 0)
        if depth > 0:
            i -= 1
            continue

        # Indented parametrize argument at column 0 (e.g., single `)` or `],`)
        if col0 and raw_stripped in (')', ']', '),', '],'):
            i -= 1
            continue

        # Stop: this is likely previous test body code
        break
    
    if found_pytest_at is not None:
        # Check if the test signature matches the parametrize params
        # Only include the @pytest line (the argument lines will be picked
        # up by the forward scan naturally since they're between @pytest and def)
        # Actually, find the START of the parametrize block (scan backward from @pytest)
        dec_start = found_pytest_at
        # Go further back to find the START of the parametrize content
        # (the @pytest line IS the start, argument content is after it)
        # Skip blank lines before @pytest
        while dec_start > 0:
            if not lines[dec_start - 1].strip():
                dec_start -= 1
            else:
                break
        # Include everything from here to the test def
        # (this naturally captures the full @pytest.mark.parametrize block)
    
    # Walk forward from start_idx to find body end
    # Stop at the next 'def ' or '@pytest' line (gap content)
    i = start_idx + 1
    while i < len(lines):
        raw = lines[i]
        trimmed = raw.lstrip()
        # Only break on 'def ' at column 0 (top-level, not nested in class)
        if raw[0] not in (' ', '\t') and trimmed.startswith('def ') and i > start_idx:
            break
        if trimmed.startswith('@pytest'):
            break
        i += 1
    return dec_start, i


def main():
    lines = SRC.read_text().splitlines(keepends=True)
    
    # Find all test function defs with their source ranges
    test_defs = []
    for i, l in enumerate(lines):
        stripped = l.lstrip()
        if stripped.startswith("def test_"):
            paren = l.find("(")
            if paren > 0:
                name = l[l.index("def ") + 4 : paren].strip()
                test_defs.append((i, name))
    
    # For each test, find the actual body range
    entries = []
    for idx, (start, name) in enumerate(test_defs):
        dec_start, body_end = _find_test_body(lines, start)
        entries.append((dec_start, body_end, name))
    
    # Group by target file
    file_map = defaultdict(list)
    for dec_start, body_end, name in entries:
        group = group_test(name)
        file_map[group].append((dec_start, body_end, name))
    
    # Write each file
    for filename, file_entries in sorted(file_map.items()):
        path = OUT / f"{filename}.py"
        body = [COMMON_IMPORTS, "\n"]
        
        is_git = any("_git_" in name for _, _, name in file_entries)
        if is_git:
            body.append(GIT_HELPERS)
            body.append("\n")
        
        for dec_start, body_end, name in file_entries:
            body.extend(lines[dec_start:body_end])
            body.append("\n")
        
        content = "".join(body)
        path.write_text(content)
        lc = len(content.splitlines())
        print(f"  {filename}.py: {len(file_entries)} tests, {lc} lines")
    
    total = sum(len(v) for v in file_map.values())
    print(f"\nTotal: {total} tests across {len(file_map)} files")


if __name__ == "__main__":
    main()
