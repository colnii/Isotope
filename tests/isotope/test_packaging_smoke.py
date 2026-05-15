import ast
import json
import os
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any

import pytest
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SRC_PACKAGE = REPO_ROOT / "src" / "isotope"
FORBIDDEN_REPO_DIRS = ("runs", "artifacts", "checkpoints")
REQUIRED_DEMO_JSON_FIELDS = {
    "run_status",
    "artifact_ref",
    "replay_ok",
    "checkpoint_ok",
    "memory_status",
}
FORBIDDEN_CONTENT_KEYS = {
    "content",
    "artifact_content",
    "full_content",
    "full_text",
    "raw_content",
    "raw_artifact_content",
}


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    return env


def _venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _script_path(python: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return python.parent / f"{name}{suffix}"


def _run(
    cmd: list[str | Path],
    *,
    cwd: Path,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=cwd,
        env=_clean_env(),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture(scope="module")
def installed_python(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("installed-isotope")
    venv_path = root / "venv"
    outside_cwd = root / "outside-cwd"
    outside_cwd.mkdir()
    venv.EnvBuilder(with_pip=True).create(venv_path)
    python = _venv_python(venv_path)

    result = _run(
        [python, "-m", "pip", "install", "--no-deps", "-e", REPO_ROOT],
        cwd=outside_cwd,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return python, outside_cwd


def _repo_dir_snapshot() -> dict[str, list[str] | None]:
    snapshots: dict[str, list[str] | None] = {}
    for name in FORBIDDEN_REPO_DIRS:
        path = REPO_ROOT / name
        if not path.exists():
            snapshots[name] = None
        else:
            snapshots[name] = sorted(str(child.relative_to(path)) for child in path.rglob("*"))
    return snapshots


def _assert_no_forbidden_content_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_CONTENT_KEYS.intersection(value)
        assert forbidden == set()
        for nested in value.values():
            _assert_no_forbidden_content_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_content_keys(nested)


def _contains_pytest_dependency(pyproject: dict[str, Any]) -> bool:
    optional_dependencies = pyproject.get("project", {}).get("optional-dependencies", {})
    for dependencies in optional_dependencies.values():
        if any(str(dependency).startswith("pytest") for dependency in dependencies):
            return True

    dependency_groups = pyproject.get("dependency-groups", {})
    for dependencies in dependency_groups.values():
        if any(str(dependency).startswith("pytest") for dependency in dependencies):
            return True

    return False


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_pyproject_toml_exists():
    assert PYPROJECT.exists()


def test_pyproject_metadata_contains_minimum_package_contract():
    pyproject = _load_pyproject()
    project = pyproject["project"]

    assert project["name"]
    assert project["version"]
    assert project["requires-python"]
    assert _contains_pytest_dependency(pyproject)


def test_pyproject_declares_cli_scripts():
    scripts = _load_pyproject()["project"]["scripts"]

    assert scripts["isotope-demo"] == "isotope.demo:main"
    assert scripts["isotope-capability"] == "isotope.capabilities.runner:main"
    assert scripts["isotope-llm-smoke"] == "isotope.llm_live_smoke:main"
    assert scripts["isotope-api"] == "isotope.apps.api:main"


def test_package_discovery_covers_src_isotope():
    pyproject = _load_pyproject()
    package_find = pyproject["tool"]["setuptools"]["packages"]["find"]

    assert package_find["where"] == ["src"]
    assert SRC_PACKAGE.exists()
    assert (SRC_PACKAGE / "__init__.py").exists()


def test_editable_install_allows_importing_isotope(installed_python):
    python, outside_cwd = installed_python

    result = _run(
        [python, "-c", "import isotope; print(isotope.__file__)"],
        cwd=outside_cwd,
    )

    assert result.returncode == 0, result.stderr
    assert "isotope" in result.stdout


def test_editable_install_runs_plain_text_demo_without_pythonpath(installed_python):
    python, outside_cwd = installed_python

    result = _run([python, "-m", "isotope.demo"], cwd=outside_cwd)

    assert result.returncode == 0, result.stderr
    assert "run_status" in result.stdout
    assert "artifact_ref" in result.stdout
    assert "replay_ok" in result.stdout
    assert "checkpoint_ok" in result.stdout
    assert "memory_status" in result.stdout


def test_editable_install_runs_json_demo_without_pythonpath(installed_python):
    python, outside_cwd = installed_python

    result = _run([python, "-m", "isotope.demo", "--json"], cwd=outside_cwd)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert REQUIRED_DEMO_JSON_FIELDS.issubset(data)
    assert data["memory_status"] == "boundary_only"
    _assert_no_forbidden_content_keys(data)


def test_installed_demo_does_not_write_repo_root_storage_dirs(installed_python):
    python, outside_cwd = installed_python
    before = _repo_dir_snapshot()

    result = _run([python, "-m", "isotope.demo", "--json"], cwd=outside_cwd)

    assert result.returncode == 0, result.stderr
    assert _repo_dir_snapshot() == before


def test_editable_install_runs_demo_console_script(installed_python):
    python, outside_cwd = installed_python

    result = _run(
        [_script_path(python, "isotope-demo"), "--json"],
        cwd=outside_cwd,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert REQUIRED_DEMO_JSON_FIELDS.issubset(data)
    _assert_no_forbidden_content_keys(data)


def test_installed_package_source_does_not_import_x_agent():
    imports: set[str] = set()
    for path in SRC_PACKAGE.rglob("*.py"):
        imports.update(_imported_modules(path))

    assert not any(module == "x_agent" or module.startswith("x_agent.") for module in imports)
