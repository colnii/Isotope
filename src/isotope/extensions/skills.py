"""Public progressive discovery for local Isotope skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable

from importlib.resources.abc import Traversable

from isotope.extensions.sources import (
    ExtensionSource,
    iter_named_files,
    read_text,
    skill_sources,
)


DEFAULT_SKILL_BODY_LIMIT = 12000
_FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---\n?", re.DOTALL)
_LINKED_PATH_RE = re.compile(r"\b(?:references|scripts|assets)/[A-Za-z0-9._/\-]+")


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


def default_skill_roots(*, cwd: Path | str | None = None) -> list[Path]:
    roots: list[Path] = []
    for source in skill_sources(cwd=cwd):
        if isinstance(source.root, Path) and source.root.is_dir():
            roots.append(source.root)
    return roots


def discover_skills(
    *,
    roots: Iterable[Path | str] | None = None,
    cwd: Path | str | None = None,
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    records, skipped = _load_skill_records(_normalize_sources(roots, cwd=cwd))
    normalized_query = query.strip().lower()
    matches: list[SkillRecord] = []
    for record in records:
        haystack = " ".join(
            [record.skill_id, record.name, record.description]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        matches.append(record)
    limited = matches[:limit]
    return {
        "kind": "skill_search_result",
        "query": query,
        "skill_count": len(limited),
        "skills": [record.to_metadata() for record in limited],
        "skipped": skipped,
    }


def describe_skill(
    skill_id: str,
    *,
    roots: Iterable[Path | str] | None = None,
    cwd: Path | str | None = None,
    max_body_chars: int = DEFAULT_SKILL_BODY_LIMIT,
) -> dict[str, Any]:
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise ValueError("skill_id must be a non-empty string")
    if (
        isinstance(max_body_chars, bool)
        or not isinstance(max_body_chars, int)
        or max_body_chars <= 0
    ):
        raise ValueError("max_body_chars must be a positive integer")
    records, _skipped = _load_skill_records(_normalize_sources(roots, cwd=cwd))
    for record in records:
        if record.skill_id == skill_id:
            text = read_text(record.skill_resource)
            markdown_body = _markdown_body(text)
            body = markdown_body[:max_body_chars]
            return {
                "kind": "skill_description",
                "skill": record.to_metadata(),
                "body": body,
                "body_truncated": len(markdown_body) > max_body_chars,
                "linked_paths": _linked_paths(text),
            }
    raise ValueError(f"unknown skill_id: {skill_id}")


def _normalize_sources(
    roots: Iterable[Path | str] | None,
    *,
    cwd: Path | str | None,
) -> list[ExtensionSource]:
    return skill_sources(cwd=cwd, explicit_roots=roots)


def _load_skill_records(
    sources: list[ExtensionSource],
) -> tuple[list[SkillRecord], list[dict[str, str]]]:
    records_by_id: dict[str, SkillRecord] = {}
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
            if skill_id in records_by_id:
                continue
            records_by_id[skill_id] = SkillRecord(
                skill_id=skill_id,
                name=parsed["name"],
                description=parsed["description"],
                source_kind=source.source_kind,
                relative_path=relative_path,
                skill_resource=skill_resource,
            )
    records = sorted(records_by_id.values(), key=lambda item: item.skill_id)
    return records, skipped


def _parse_skill_text(text: str) -> dict[str, str] | None:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    fields = _parse_frontmatter_fields(match.group("body"))
    name = fields.get("name", "").strip()
    description = fields.get("description", "").strip()
    if not name or not description:
        return None
    return {"name": name, "description": description}


def _markdown_body(text: str) -> str:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return text
    return text[match.end() :]


def _parse_frontmatter_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if ":" not in line or line.startswith((" ", "\t")):
            index += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in {"|", ">"}:
            index += 1
            block: list[str] = []
            while index < len(lines) and lines[index].startswith((" ", "\t")):
                block.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(part for part in block if part)
            continue
        fields[key] = value.strip().strip('"').strip("'")
        index += 1
    return fields


def _linked_paths(text: str) -> list[str]:
    return sorted(set(_LINKED_PATH_RE.findall(text)))
