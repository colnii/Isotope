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
    sources: list[ExtensionSource] = []
    sources.extend(
        _existing_path_sources(
            SOURCE_PROJECT,
            [project_root / "isotope.extensions" / "skills"],
        )
    )
    env_roots = os.environ.get("ISOTOPE_SKILL_ROOTS")
    if env_roots:
        sources.extend(
            _existing_path_sources(
                SOURCE_USER,
                [
                    Path(item).expanduser()
                    for item in env_roots.split(os.pathsep)
                    if item
                ],
            )
        )
    isotope_home = os.environ.get("ISOTOPE_HOME")
    user_candidates: list[Path] = []
    if isotope_home:
        user_candidates.append(Path(isotope_home).expanduser() / "skills")
    user_candidates.append(Path.home() / ".isotope" / "skills")
    sources.extend(_existing_path_sources(SOURCE_USER, user_candidates))
    sources.extend(_builtin_sources("skills"))
    sources.extend(
        _existing_path_sources(
            SOURCE_LEGACY_PROJECT,
            [project_root / ".isotope" / "skills"],
        )
    )
    return _unique_sources(sources)


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


def iter_named_files(
    root: Path | Traversable,
    name: str,
) -> list[tuple[Path | Traversable, str]]:
    matches: list[tuple[Path | Traversable, str]] = []

    def visit(node: Path | Traversable, relative_prefix: str) -> None:
        try:
            children = sorted(node.iterdir(), key=lambda item: item.name)
        except (FileNotFoundError, NotADirectoryError):
            return
        for child in children:
            relative = (
                f"{relative_prefix}/{child.name}" if relative_prefix else child.name
            )
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
        return [(root, root.name)]
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


def _existing_path_sources(
    source_kind: str,
    roots: Iterable[Path],
) -> list[ExtensionSource]:
    return [
        ExtensionSource(
            source_kind=source_kind,
            root=root,
            label=str(root),
        )
        for root in roots
        if root.exists() and (root.is_dir() or root.is_file())
    ]


def _builtin_sources(subdir: str) -> list[ExtensionSource]:
    try:
        root = resources.files("isotope.builtin.extensions").joinpath(subdir)
    except ModuleNotFoundError:
        return []
    if not root.exists() or not (root.is_dir() or root.is_file()):
        return []
    return [
        ExtensionSource(
            source_kind=SOURCE_BUILTIN,
            root=root,
            label=f"isotope.builtin.extensions/{subdir}",
        )
    ]


def _unique_sources(sources: Iterable[ExtensionSource]) -> list[ExtensionSource]:
    seen: set[object] = set()
    result: list[ExtensionSource] = []
    for source in sources:
        if isinstance(source.root, Path):
            key: object = source.root.resolve()
        else:
            key = (source.source_kind, source.label)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result
