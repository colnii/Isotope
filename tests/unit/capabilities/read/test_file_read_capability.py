from __future__ import annotations

import pytest

from isotope.capabilities.runner import CapabilityRunner


def test_file_read_workspace_scope_returns_bounded_excerpt(tmp_path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("marker = 'ISOTOPE_READ_MARKER'\n" * 20, encoding="utf-8")

    result = CapabilityRunner().run_capability(
        "file.read",
        inputs={
            "root": str(tmp_path / "state"),
            "cwd": str(tmp_path),
            "scope": "workspace",
            "path": "src/app.py",
            "max_excerpt_chars": 40,
        },
    )

    assert result["capability_id"] == "file.read"
    assert result["status"] == "completed"
    assert result["read"]["scope"] == "workspace"
    assert result["read"]["status"] == "readable"
    assert result["read"]["path"] == "src/app.py"
    assert result["read"]["truncated"] is True
    assert result["read"]["excerpt"] == "marker = 'ISOTOPE_READ_MARKER'\nmarker = "
    assert result["read"]["ref"]["scope"] == "workspace"
    assert result["read"]["content_policy"] == "limited_excerpts_only"


def test_file_read_workspace_scope_rejects_workspace_escape(tmp_path) -> None:
    with pytest.raises(ValueError, match="path must stay inside the workspace"):
        CapabilityRunner().run_capability(
            "file.read",
            inputs={
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path),
                "scope": "workspace",
                "path": "../outside.md",
            },
        )


def test_file_read_local_file_scope_requires_root_for_approval(tmp_path) -> None:
    with pytest.raises(ValueError, match="root must be a non-empty string"):
        CapabilityRunner().run_capability(
            "file.read",
            inputs={
                "cwd": str(tmp_path),
                "scope": "local_file",
                "path": str(tmp_path / "note.md"),
            },
        )
