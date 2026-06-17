import json

import pytest

from isotope.capabilities.runner import CapabilityRunner


def test_runner_discovers_ast_edit_from_default_catalog():
    runner = CapabilityRunner()

    assert "code.ast_edit" in {
        entry["capability_id"] for entry in runner.list_capabilities()
    }
    description = runner.describe_capability("code.ast_edit")

    assert description["input_contract"]["required"] == [
        "root",
        "cwd",
        "path",
        "selector",
        "replacement",
    ]
    assert "tree_sitter_parse_required" in description["safety_boundaries"]
    assert "universal_syntax_tree_projection" in description["safety_boundaries"]
    assert "syntax_error_rejected_before_write" in description["safety_boundaries"]


def test_ast_edit_replaces_selected_tree_sitter_node_and_reparses(tmp_path):
    workspace = tmp_path / "repo"
    source = workspace / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def greet(name):\n"
        "    return f'hello {name}'\n"
        "\n"
        "def untouched():\n"
        "    return 'same'\n",
        encoding="utf-8",
    )

    result = CapabilityRunner().run_capability(
        "code.ast_edit",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(workspace),
            "path": "src/app.py",
            "selector": {
                "node_type": "function_definition",
                "text_contains": "def greet",
            },
            "replacement": "def greet(name):\n    return name.upper()\n",
        },
    )

    ast_edit = result["ast_edit"]
    assert result["kind"] == "capability_run_result"
    assert result["capability_id"] == "code.ast_edit"
    assert result["status"] == "completed"
    assert result["runner_kind"] == "deterministic_local"
    assert ast_edit["status"] == "applied"
    assert ast_edit["language"] == "python"
    assert ast_edit["parse_engine"] == "tree-sitter"
    assert ast_edit["universal_tree"]["root_type"] == "module"
    assert ast_edit["selected_node"]["type"] == "function_definition"
    assert ast_edit["selected_node"]["path"] == [0]
    assert ast_edit["selected_node"]["text_sha256"]
    assert ast_edit["replacement"]["line_count"] == 2
    assert ast_edit["changed_files"] == ["src/app.py"]
    assert ast_edit["syntax_check"] == {
        "status": "passed",
        "has_error": False,
        "root_type": "module",
    }
    assert "hello" not in source.read_text(encoding="utf-8")
    assert "return name.upper()" in source.read_text(encoding="utf-8")
    assert "def untouched()" in source.read_text(encoding="utf-8")
    assert "hello" not in json.dumps(ast_edit, ensure_ascii=False)


def test_ast_edit_uses_same_universal_contract_for_javascript(tmp_path):
    workspace = tmp_path / "repo"
    source = workspace / "src" / "app.js"
    source.parent.mkdir(parents=True)
    source.write_text(
        "function greet(name) {\n"
        "  return `hello ${name}`;\n"
        "}\n"
        "\n"
        "function untouched() {\n"
        "  return 1;\n"
        "}\n",
        encoding="utf-8",
    )

    result = CapabilityRunner().run_capability(
        "code.ast_edit",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(workspace),
            "path": "src/app.js",
            "selector": {
                "node_type": "function_declaration",
                "text_contains": "function greet",
            },
            "replacement": "function greet(name) {\n  return name.toUpperCase();\n}\n",
        },
    )

    ast_edit = result["ast_edit"]
    assert ast_edit["language"] == "javascript"
    assert ast_edit["universal_tree"]["root_type"] == "program"
    assert ast_edit["selected_node"]["type"] == "function_declaration"
    assert ast_edit["selected_node"]["path"] == [0]
    assert ast_edit["syntax_check"]["status"] == "passed"
    assert "return name.toUpperCase();" in source.read_text(encoding="utf-8")
    assert "function untouched()" in source.read_text(encoding="utf-8")


def test_ast_edit_rejects_invalid_replacement_without_writing(tmp_path):
    workspace = tmp_path / "repo"
    source = workspace / "src" / "app.py"
    source.parent.mkdir(parents=True)
    original = "def greet(name):\n    return name\n"
    source.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="replacement produces syntax errors"):
        CapabilityRunner().run_capability(
            "code.ast_edit",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(workspace),
                "path": "src/app.py",
                "selector": {
                    "node_type": "function_definition",
                    "text_contains": "def greet",
                },
                "replacement": "def broken(:\n",
            },
        )

    assert source.read_text(encoding="utf-8") == original


def test_ast_edit_rejects_workspace_escape(tmp_path):
    with pytest.raises(ValueError, match="path must stay inside the workspace"):
        CapabilityRunner().run_capability(
            "code.ast_edit",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path),
                "path": "../outside.py",
                "selector": {"node_type": "module"},
                "replacement": "value = 1\n",
            },
        )
