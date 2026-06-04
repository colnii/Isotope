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
    assert "linked_paths" not in rendered
