import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CLOUD_CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-cloud.yml"
ACTIONLINT_CONFIG = REPO_ROOT / ".github" / "actionlint.yaml"


def _workflow_text() -> str:
    if not CI_WORKFLOW.exists():
        pytest.skip(".github/workflows/ci.yml is not implemented yet")
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _cloud_workflow_text() -> str:
    if not CLOUD_CI_WORKFLOW.exists():
        pytest.skip(".github/workflows/ci-cloud.yml is not implemented yet")
    return CLOUD_CI_WORKFLOW.read_text(encoding="utf-8")


def _contains_trigger(text: str, trigger: str) -> bool:
    flow_list_pattern = rf"(?m)^\s*on\s*:\s*\[[^\]]*\b{re.escape(trigger)}\b[^\]]*\]"
    multiline_pattern = rf"(?m)^\s*{re.escape(trigger)}\s*:"
    return bool(re.search(flow_list_pattern, text)) or bool(re.search(multiline_pattern, text))


def _contains_command(text: str, command: str) -> bool:
    normalized = re.sub(r"\s+", " ", text)
    return command in normalized


def _contains_editable_test_extra_install(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text)
    commands = (
        'python -m pip install -e ".[test]"',
        "python -m pip install -e '.[test]'",
    )
    return any(command in normalized for command in commands)


def test_ci_workflow_file_exists():
    assert CI_WORKFLOW.exists(), "expected .github/workflows/ci.yml to define CI smoke"


def test_ci_workflow_runs_on_push_and_pull_request():
    text = _workflow_text()

    assert re.search(r"(?m)^\s*on\s*:", text)
    assert _contains_trigger(text, "push")
    assert _contains_trigger(text, "pull_request")


def test_ci_workflow_uses_github_hosted_runner():
    text = _workflow_text()

    assert "runs-on: ubuntu-latest" in text


def test_ci_workflow_cancels_superseded_runs_per_ref():
    text = _workflow_text()

    assert re.search(r"(?m)^\s*concurrency\s*:", text)
    assert "group: ${{ github.workflow }}-${{ github.ref }}" in text
    assert re.search(r"(?m)^\s*cancel-in-progress\s*:\s*true\s*$", text)


def test_ci_workflow_uses_node24_compatible_actions():
    text = _workflow_text()

    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text


def test_ci_workflow_runs_one_supported_python_version():
    text = _workflow_text()

    assert "actions/setup-python" in text
    assert "matrix.python-version" not in text
    assert re.search(r"(?m)^\s*python-version\s*:\s*['\"]?3\.13['\"]?\s*$", text)
    assert not re.search(r"(?m)^\s*-\s*['\"]?3\.12['\"]?\s*$", text)
    assert not re.search(r"(?m)^\s*-\s*['\"]?3\.14['\"]?\s*$", text)


def test_ci_workflow_installs_editable_project_with_test_extra():
    text = _workflow_text()

    assert _contains_command(text, "python -m pip install -U pip")
    assert _contains_editable_test_extra_install(text)


def test_ci_workflow_runs_full_kernel_tests():
    text = _workflow_text()

    assert _contains_command(text, "python -m pytest tests/ -q")


def test_ci_workflow_runs_demo_smoke_plain_and_json():
    text = _workflow_text()

    assert _contains_command(text, "python -m isotope.demo")
    assert _contains_command(text, "python -m isotope.demo --json")


def test_ci_workflow_does_not_require_secrets():
    text = _workflow_text()

    assert "secrets." not in text
    assert "${{ secrets" not in text


def test_ci_workflow_avoids_external_service_calls_beyond_dependency_install():
    text = _workflow_text().lower()

    forbidden_terms = (
        "services:",
        "curl ",
        "wget ",
        "docker login",
        "ssh ",
        "scp ",
        "gh auth",
        "npm ",
        "pnpm ",
        "yarn ",
    )
    assert not any(term in text for term in forbidden_terms)


def test_ci_workflow_does_not_reference_local_absolute_paths():
    text = _workflow_text()

    assert "/home/lumber/" not in text
    assert "/mnt/" not in text


def test_ci_workflow_does_not_reference_x_agent():
    text = _workflow_text()

    assert "x_agent" not in text
    assert "x-agent" not in text


def test_cloud_ci_workflow_is_manual_only():
    text = _cloud_workflow_text()

    assert _contains_trigger(text, "workflow_dispatch")
    assert not _contains_trigger(text, "push")
    assert not _contains_trigger(text, "pull_request")
    assert re.search(r"(?m)^\s*runs-on\s*:\s*ubuntu-latest\s*$", text)


def test_cloud_ci_workflow_runs_same_python313_smoke():
    text = _cloud_workflow_text()

    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text
    assert re.search(r"(?m)^\s*python-version\s*:\s*['\"]?3\.13['\"]?\s*$", text)
    assert _contains_editable_test_extra_install(text)
    assert _contains_command(text, "python -m pytest tests/ -q")
    assert _contains_command(text, "python -m isotope.demo")
    assert _contains_command(text, "python -m isotope.demo --json")


def test_actionlint_knows_project_self_hosted_label():
    text = ACTIONLINT_CONFIG.read_text(encoding="utf-8")

    assert re.search(r"(?m)^\s*self-hosted-runner\s*:", text)
    assert re.search(r"(?m)^\s*-\s*isotope-ci\s*$", text)
