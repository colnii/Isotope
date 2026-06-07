from __future__ import annotations

from pathlib import Path

from isotope.extensions.skills import (
    DEFAULT_SKILL_BODY_LIMIT,
    describe_skill,
    discover_skills,
)


def _write_skill(
    root: Path,
    relative: str,
    *,
    name: str,
    description: str,
    body: str = "",
) -> None:
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


def test_describe_skill_returns_scoped_body_without_linked_files(tmp_path) -> None:
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
    (references / "deep-guide.md").write_text(
        "MUST NOT AUTO LOAD",
        encoding="utf-8",
    )

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


def test_default_skill_roots_are_isotope_native_and_project_local(
    tmp_path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    isotope_home = tmp_path / "isotope-home"
    project = tmp_path / "project"
    codex_home = tmp_path / "codex-home"
    _write_skill(
        isotope_home / "skills",
        "native",
        name="native-skill",
        description="Isotope native skill.",
    )
    _write_skill(
        project / ".isotope" / "skills",
        "project",
        name="project-skill",
        description="Project local skill.",
    )
    _write_skill(
        codex_home / "skills",
        "codex",
        name="codex-skill",
        description="Codex compatibility skill.",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ISOTOPE_HOME", str(isotope_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(project)

    result = discover_skills()

    assert [skill["skill_id"] for skill in result["skills"]] == [
        "native-skill",
        "project-skill",
    ]
