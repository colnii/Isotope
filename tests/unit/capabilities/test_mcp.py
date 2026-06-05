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



def test_runner_executes_skills_describe_with_scoped_body(tmp_path):
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



def test_runner_rejects_mcp_tool_call_without_config(monkeypatch):
    monkeypatch.delenv("ISOTOPE_MCP_SERVERS_JSON", raising=False)
    runner = _runner()

    with pytest.raises(ValueError, match="unknown MCP server"):
        runner.run_capability(
            "mcp.tool.call",
            inputs={"server_id": "missing", "tool_name": "echo", "arguments": {}},
        )



def test_runner_executes_mcp_tool_call_from_explicit_env_config(monkeypatch):
    fixture_server = (
        Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"
    )
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



