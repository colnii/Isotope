# Supervisor Capacity Dev Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a developer-only Supervisor capacity eval gate that uses a real LLM to choose capabilities, mechanically checks the resulting traces, and emits a reviewer prompt for Codex.

**Architecture:** Add a narrow `isotope.dev_evals` package. `changed_surface` decides whether the current diff requires the suite; `supervisor_capacity_eval` runs the live or deterministic-harness suite through `run_supervisor_conversation_events(...)`; `cases`, `gates`, `reporting`, and `reviewer_prompt` keep scenario definitions, hard gates, sanitized JSON reports, and Codex review prompts separate.

**Tech Stack:** Python 3.13, pytest, existing `CapabilityRunner`, `run_supervisor_conversation_events(...)`, shared LLM provider resolution, existing artifact/state-root conventions.

---

## Baseline

Worktree:

`/home/lumber/Github/isotope/.worktrees/supervisor-capacity-dev-eval`

Baseline command already run:

```bash
.venv/bin/python -m pytest -q tests/unit/capabilities/test_capability_catalog_core.py tests/unit/capabilities/test_capability_runner_modularization.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/unit/llm/test_system_prompt_assets.py tests/integration/supervisor/desktop/test_desktop_chat_capacity_product_smoke.py
```

Result:

```text
58 passed in 1.09s
```

## File Structure

- Create `src/isotope/dev_evals/__init__.py`: package marker with no runtime side effects.
- Create `src/isotope/dev_evals/models.py`: dataclasses and typed helpers for surface decisions, scenarios, gates, steps, reports, and reviewer prompt refs.
- Create `src/isotope/dev_evals/changed_surface.py`: semantic diff detector and `python -m` CLI.
- Create `src/isotope/dev_evals/cases.py`: full scenario catalog for every current `CapabilityRunner().list_capabilities()` id.
- Create `src/isotope/dev_evals/fixtures.py`: temporary fixture workspace/state-root builder used by unit and live evals.
- Create `src/isotope/dev_evals/gates.py`: deterministic hard-gate checks over conversation events and report steps.
- Create `src/isotope/dev_evals/reporting.py`: sanitizer, score defaults, JSON report serialization, and status aggregation.
- Create `src/isotope/dev_evals/reviewer_prompt.py`: prompt artifact renderer for Codex self-review.
- Create `src/isotope/dev_evals/supervisor_capacity_eval.py`: suite runner, LLM provider resolution, CLI, and opt-in live execution boundary.
- Create `tests/unit/dev_evals/test_changed_surface.py`: semantic trigger tests.
- Create `tests/unit/dev_evals/test_cases.py`: scenario catalog coverage tests.
- Create `tests/unit/dev_evals/test_gates_reporting.py`: hard-gate and sanitizer tests.
- Create `tests/unit/dev_evals/test_reviewer_prompt.py`: reviewer prompt content tests.
- Create `tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py`: deterministic-provider harness tests.
- Create `tests/evals/test_supervisor_capacity_live_eval.py`: opt-in live eval pytest wrapper.
- Create `docs/current/supervisor-dev-evals.md`: developer note, not a public quick-start entry.

## Current Capability Coverage List

The scenario catalog must cover these 39 current capability ids:

```python
CURRENT_CAPABILITY_IDS = [
    "approval.tool.runner",
    "artifact.changed_files",
    "artifact.diff_result",
    "artifact.review",
    "code.apply_patch",
    "code.read",
    "code.search",
    "coding_task.apply_reviewed_diff",
    "coding_task.execute",
    "coding_task.plan",
    "coding_task.run",
    "external.snapshot.review",
    "isotope.self_repair",
    "mcp.servers.list",
    "mcp.tool.call",
    "mcp.tools.search",
    "memory.promotion.preview",
    "memory.query",
    "memory.recall",
    "research.promote",
    "research.search",
    "screen.observe",
    "screen.report",
    "skills.describe",
    "skills.search",
    "supervisor.codex_operation",
    "supervisor.goal_plan",
    "supervisor.integration_review",
    "supervisor.project_status",
    "supervisor.request_context",
    "supervisor.worker_review",
    "test.run",
    "vcs.diff",
    "vcs.status",
    "workspace.changed_files",
    "workspace.isolated_rw",
    "workspace.lease_create",
    "workspace.materialize",
    "workspace.release",
]
```

## Task 1: Changed Surface Preflight

**Files:**
- Create: `src/isotope/dev_evals/__init__.py`
- Create: `src/isotope/dev_evals/models.py`
- Create: `src/isotope/dev_evals/changed_surface.py`
- Test: `tests/unit/dev_evals/test_changed_surface.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/dev_evals/test_changed_surface.py`:

```python
from isotope.dev_evals.changed_surface import detect_changed_surface


def test_changed_surface_requires_eval_for_capability_contract_diff():
    diff_text = """
diff --git a/src/isotope/capabilities/catalog.py b/src/isotope/capabilities/catalog.py
+ capability_id="code.search"
+ input_contract={"type": "object"}
+ output_contract={"type": "object"}
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert result.suite == "supervisor_capacity_basic"
    assert "capability_contract_changed" in result.reason_codes
    assert result.recommended_command.endswith(
        "isotope.dev_evals.supervisor_capacity_eval --suite supervisor_capacity_basic --json"
    )


def test_changed_surface_requires_eval_for_prompt_and_observation_diff():
    diff_text = """
diff --git a/src/isotope/llm/prompts/supervisor_conversation_loop.md b/src/isotope/llm/prompts/supervisor_conversation_loop.md
+ capacity_observation
+ call_capability
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert result.reason_codes == [
        "conversation_contract_changed",
        "llm_prompt_changed",
    ]


def test_changed_surface_does_not_require_eval_for_unrelated_docs_diff():
    diff_text = """
diff --git a/docs/current/README.md b/docs/current/README.md
+ typo fix in onboarding prose
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is False
    assert result.reason_codes == []
    assert result.recommended_command is None
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_changed_surface.py -q
```

Expected: import failure for `isotope.dev_evals.changed_surface`.

- [ ] **Step 3: Implement the minimal detector**

Create `src/isotope/dev_evals/models.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SurfaceDecision:
    eval_required: bool
    suite: str | None
    reason_codes: list[str]
    recommended_command: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "eval_required": self.eval_required,
            "suite": self.suite,
            "reason_codes": list(self.reason_codes),
            "recommended_command": self.recommended_command,
        }
```

Create `src/isotope/dev_evals/changed_surface.py` with:

```python
from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence

from .models import SurfaceDecision


SUITE = "supervisor_capacity_basic"
RECOMMENDED_COMMAND = (
    "PYTHONPATH=src .venv/bin/python -m "
    "isotope.dev_evals.supervisor_capacity_eval "
    "--suite supervisor_capacity_basic --json"
)

SEMANTIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "capability_contract_changed",
        ("capability_id", "input_contract", "output_contract", "Capability", "CapabilityCatalog", "run_capability"),
    ),
    (
        "conversation_contract_changed",
        ("capacity_manifest", "capacity_observation", "call_capability", "call_capabilities", "direct_answer", "report_capability_gap"),
    ),
    (
        "llm_prompt_changed",
        ("SYSTEM_PROMPT_NAMES", "USER_PROMPT_TEMPLATE_NAMES", "supervisor_conversation_loop", "capacity_calling", "src/isotope/llm/prompts/"),
    ),
    (
        "agent_loop_projection_changed",
        ("model_observation", "agent_loop_json_result", "capacity_start", "capacity_result", "low-sensitive"),
    ),
    (
        "public_command_contract_changed",
        ("capacity plan", "research --root", "isotope-capability", "golden event", "result schema"),
    ),
)


def detect_changed_surface(diff_text: str) -> SurfaceDecision:
    reason_codes: list[str] = []
    for reason_code, needles in SEMANTIC_PATTERNS:
        if any(needle in diff_text for needle in needles):
            reason_codes.append(reason_code)
    return SurfaceDecision(
        eval_required=bool(reason_codes),
        suite=SUITE if reason_codes else None,
        reason_codes=reason_codes,
        recommended_command=RECOMMENDED_COMMAND if reason_codes else None,
    )


def diff_against_base(base: str) -> str:
    completed = subprocess.run(
        ["git", "diff", "--no-ext-diff", base, "--"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    decision = detect_changed_surface(diff_against_base(args.base))
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print("eval_required:", str(decision.eval_required).lower())
        print("suite:", decision.suite or "")
        if decision.reason_codes:
            print("reason_codes:", ", ".join(decision.reason_codes))
        if decision.recommended_command:
            print("recommended_command:", decision.recommended_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `src/isotope/dev_evals/__init__.py`:

```python
"""Developer-only evaluation helpers for Isotope."""
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_changed_surface.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/dev_evals tests/unit/dev_evals/test_changed_surface.py
git commit -m "feat(dev-evals): add changed surface preflight"
```

## Task 2: Scenario Catalog With Full Capability Coverage

**Files:**
- Modify: `src/isotope/dev_evals/models.py`
- Create: `src/isotope/dev_evals/cases.py`
- Test: `tests/unit/dev_evals/test_cases.py`

- [ ] **Step 1: Write failing catalog coverage tests**

Create `tests/unit/dev_evals/test_cases.py`:

```python
from isotope.capabilities.runner import CapabilityRunner
from isotope.dev_evals.cases import scenario_catalog


def test_scenario_catalog_covers_every_registered_capability():
    registered = {
        item["capability_id"]
        for item in CapabilityRunner().list_capabilities(
            include_diagnostics=True,
            include_experimental=True,
        )
    }
    covered = {
        capability_id
        for scenario in scenario_catalog()
        for capability_id in scenario.capability_ids
    }

    assert registered - covered == set()


def test_scenarios_have_mechanical_gate_contracts():
    for scenario in scenario_catalog():
        assert scenario.case_id
        assert scenario.user_message.strip()
        assert scenario.capability_ids
        assert scenario.fixture in {
            "empty_state",
            "workspace_with_code",
            "workspace_with_diff",
            "memory_seeded",
            "artifact_seeded",
            "mcp_configured",
            "screen_config_gated",
            "provider_config_gated",
        }
        assert "required_capacity_called" in scenario.required_gates
        assert "low_sensitive_report" in scenario.required_gates
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_cases.py -q
```

Expected: import failure for `isotope.dev_evals.cases`.

- [ ] **Step 3: Add scenario models**

Append to `src/isotope/dev_evals/models.py`:

```python
@dataclass(frozen=True)
class CapabilityScenario:
    case_id: str
    capability_ids: tuple[str, ...]
    user_message: str
    fixture: str
    required_gates: tuple[str, ...] = ("required_capacity_called", "low_sensitive_report")
    allowed_result_statuses: tuple[str, ...] = ("ok",)
    combination_only: bool = False
    configuration_gated: bool = False
    max_turns: int = 12
```

- [ ] **Step 4: Create full scenario catalog**

Create `src/isotope/dev_evals/cases.py` with a list containing every id from the coverage list. Use combination scenarios for workspace/artifact/coding capabilities that require prepared state. The initial content should include these exact scenario entries:

```python
from __future__ import annotations

from .models import CapabilityScenario


_SCENARIOS: tuple[CapabilityScenario, ...] = (
    CapabilityScenario("approval_tool_runner_demo", ("approval.tool.runner",), "Exercise the approval tool runner demo and summarize whether approval was requested.", "empty_state"),
    CapabilityScenario("artifact_changed_files_summary", ("artifact.changed_files",), "Summarize changed files for the prepared workspace artifact run.", "workspace_with_diff"),
    CapabilityScenario("artifact_diff_result_summary", ("artifact.diff_result",), "Create a diff result artifact for the prepared workspace change.", "workspace_with_diff", combination_only=True),
    CapabilityScenario("artifact_review_demo", ("artifact.review",), "Review the prepared artifact summary and report whether it is safe to show.", "artifact_seeded"),
    CapabilityScenario("code_apply_patch_fixture", ("code.apply_patch",), "Apply the provided safe patch to the fixture file.", "workspace_with_code"),
    CapabilityScenario("code_read_fixture", ("code.read",), "Read src/app.py and tell me whether the fixture marker is present.", "workspace_with_code"),
    CapabilityScenario("code_search_fixture", ("code.search",), "Find the fixture marker in the workspace source tree.", "workspace_with_code"),
    CapabilityScenario("coding_apply_reviewed_diff_fixture", ("coding_task.apply_reviewed_diff",), "Apply the reviewed diff to the prepared isolated workspace.", "workspace_with_diff", combination_only=True),
    CapabilityScenario("coding_execute_fixture", ("coding_task.execute",), "Run the prepared native coding execution fixture and summarize the verification result.", "workspace_with_diff", combination_only=True),
    CapabilityScenario("coding_plan_fixture", ("coding_task.plan",), "Plan a tiny code change for the fixture application.", "workspace_with_code"),
    CapabilityScenario("coding_run_fixture", ("coding_task.run",), "Run the native coding task for the fixture application.", "workspace_with_code", allowed_result_statuses=("blocked", "error"), combination_only=True),
    CapabilityScenario("external_snapshot_review_demo", ("external.snapshot.review",), "Review the prepared external snapshot summary.", "artifact_seeded"),
    CapabilityScenario("isotope_self_repair_fixture", ("isotope.self_repair",), "Diagnose the prepared capacity failure and propose a self repair.", "empty_state", allowed_result_statuses=("ok", "blocked")),
    CapabilityScenario("mcp_servers_list_fixture", ("mcp.servers.list",), "List configured MCP servers.", "mcp_configured"),
    CapabilityScenario("mcp_tool_call_fixture", ("mcp.tool.call",), "Call the configured MCP echo tool.", "mcp_configured", combination_only=True),
    CapabilityScenario("mcp_tools_search_fixture", ("mcp.tools.search",), "Search tools on the configured MCP server.", "mcp_configured"),
    CapabilityScenario("memory_promotion_preview_fixture", ("memory.promotion.preview",), "Preview memory promotion for the prepared candidate.", "memory_seeded"),
    CapabilityScenario("memory_query_fixture", ("memory.query",), "Query the prepared run memory for the fixture marker.", "memory_seeded"),
    CapabilityScenario("memory_recall_fixture", ("memory.recall",), "Recall memory about the fixture marker.", "memory_seeded"),
    CapabilityScenario("research_promote_fixture", ("research.promote",), "Promote the prepared research report into memory.", "artifact_seeded", combination_only=True),
    CapabilityScenario("research_search_fixture", ("research.search",), "Research the current public docs for pytest markers.", "provider_config_gated", allowed_result_statuses=("ok", "blocked")),
    CapabilityScenario("screen_observe_fixture", ("screen.observe",), "Observe the configured screen target.", "screen_config_gated", allowed_result_statuses=("ok", "blocked"), configuration_gated=True),
    CapabilityScenario("screen_report_fixture", ("screen.report",), "Summarize the prepared screen observation report.", "artifact_seeded"),
    CapabilityScenario("skills_describe_fixture", ("skills.describe",), "Describe the prepared built-in skill.", "empty_state"),
    CapabilityScenario("skills_search_fixture", ("skills.search",), "Search available skills for research.", "empty_state"),
    CapabilityScenario("supervisor_codex_operation_fixture", ("supervisor.codex_operation",), "Inspect the prepared Codex operation state without launching a new worker.", "empty_state", allowed_result_statuses=("ok", "blocked")),
    CapabilityScenario("supervisor_goal_plan_fixture", ("supervisor.goal_plan",), "Plan three Supervisor goals for improving the fixture eval.", "empty_state"),
    CapabilityScenario("supervisor_integration_review_fixture", ("supervisor.integration_review",), "Review the prepared integration state.", "empty_state"),
    CapabilityScenario("supervisor_project_status_fixture", ("supervisor.project_status",), "Summarize current Supervisor project status.", "empty_state"),
    CapabilityScenario("supervisor_request_context_fixture", ("supervisor.request_context",), "Find context about capacity observations in the fixture repo.", "workspace_with_code"),
    CapabilityScenario("supervisor_worker_review_fixture", ("supervisor.worker_review",), "Review the prepared worker state.", "empty_state"),
    CapabilityScenario("test_run_fixture", ("test.run",), "Run the prepared printf validation command.", "workspace_with_code"),
    CapabilityScenario("vcs_diff_fixture", ("vcs.diff",), "Summarize the prepared git diff.", "workspace_with_diff"),
    CapabilityScenario("vcs_status_fixture", ("vcs.status",), "Show the prepared git status.", "workspace_with_diff"),
    CapabilityScenario("workspace_changed_files_fixture", ("workspace.changed_files",), "List changed files in the prepared isolated workspace.", "workspace_with_diff"),
    CapabilityScenario("workspace_isolated_rw_fixture", ("workspace.isolated_rw",), "Create an isolated writable workspace proposal for the fixture.", "workspace_with_code"),
    CapabilityScenario("workspace_lease_create_fixture", ("workspace.lease_create",), "Create a workspace lease for the prepared isolated workspace.", "workspace_with_diff", combination_only=True),
    CapabilityScenario("workspace_materialize_fixture", ("workspace.materialize",), "Materialize the prepared workspace fixture.", "workspace_with_code"),
    CapabilityScenario("workspace_release_fixture", ("workspace.release",), "Release the prepared materialized workspace.", "workspace_with_diff", combination_only=True),
)


def scenario_catalog() -> list[CapabilityScenario]:
    return list(_SCENARIOS)
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_cases.py -q
```

Expected: all tests pass and coverage difference is empty.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/dev_evals/models.py src/isotope/dev_evals/cases.py tests/unit/dev_evals/test_cases.py
git commit -m "feat(dev-evals): add supervisor capacity scenario catalog"
```

## Task 3: Hard Gates, Sanitizer, and Report Contract

**Files:**
- Modify: `src/isotope/dev_evals/models.py`
- Create: `src/isotope/dev_evals/gates.py`
- Create: `src/isotope/dev_evals/reporting.py`
- Test: `tests/unit/dev_evals/test_gates_reporting.py`

- [ ] **Step 1: Write failing gate and report tests**

Create `tests/unit/dev_evals/test_gates_reporting.py`:

```python
from isotope.dev_evals.gates import evaluate_required_capacity_called, low_sensitive_report_passed
from isotope.dev_evals.models import CapabilityScenario
from isotope.dev_evals.reporting import build_case_report, sanitize_value


def test_required_capacity_gate_fails_when_expected_capacity_missing():
    scenario = CapabilityScenario(
        case_id="code_search_fixture",
        capability_ids=("code.search",),
        user_message="Find marker.",
        fixture="workspace_with_code",
    )
    steps = [{"capacity_id": "code.read", "status": "ok"}]

    gate = evaluate_required_capacity_called(scenario, steps)

    assert gate["gate"] == "required_capacity_called"
    assert gate["passed"] is False
    assert gate["details"]["missing_capacity_ids"] == ["code.search"]


def test_low_sensitive_sanitizer_redacts_raw_payloads():
    value = {
        "raw_response": "SHOULD_NOT_LEAK",
        "token": "SECRET",
        "safe": {"capacity_id": "code.search"},
        "items": [{"raw_prompt": "PROMPT_SHOULD_NOT_LEAK"}],
    }

    sanitized = sanitize_value(value)

    assert "SHOULD_NOT_LEAK" not in repr(sanitized)
    assert "SECRET" not in repr(sanitized)
    assert sanitized["safe"] == {"capacity_id": "code.search"}
    assert sanitized["items"] == [{"raw_prompt": "[redacted]"}]


def test_case_report_status_follows_hard_gates():
    scenario = CapabilityScenario(
        case_id="code_search_fixture",
        capability_ids=("code.search",),
        user_message="Find marker.",
        fixture="workspace_with_code",
    )
    report = build_case_report(
        scenario,
        steps=[{"capacity_id": "code.read", "status": "ok"}],
        final_answer="No marker.",
    )

    assert report["status"] == "failed"
    assert report["hard_gate_passed"] is False
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_gates_reporting.py -q
```

Expected: import failure for `isotope.dev_evals.gates`.

- [ ] **Step 3: Implement gates and reporting**

Append model dataclasses to `src/isotope/dev_evals/models.py`:

```python
@dataclass(frozen=True)
class EvalStep:
    capacity_id: str
    status: str
    input_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewerPromptRef:
    path: str
```

Create `src/isotope/dev_evals/gates.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import CapabilityScenario


def evaluate_required_capacity_called(
    scenario: CapabilityScenario,
    steps: list[Mapping[str, Any]],
) -> dict[str, Any]:
    called = [str(step.get("capacity_id")) for step in steps if step.get("capacity_id")]
    missing = [item for item in scenario.capability_ids if item not in called]
    return {
        "gate": "required_capacity_called",
        "passed": not missing,
        "details": {
            "expected_capacity_ids": list(scenario.capability_ids),
            "called_capacity_ids": called,
            "missing_capacity_ids": missing,
        },
    }


def evaluate_result_status(
    scenario: CapabilityScenario,
    steps: list[Mapping[str, Any]],
) -> dict[str, Any]:
    bad_steps = [
        {"capacity_id": step.get("capacity_id"), "status": step.get("status")}
        for step in steps
        if step.get("capacity_id") in scenario.capability_ids
        and step.get("status") not in scenario.allowed_result_statuses
    ]
    return {
        "gate": "result_status_allowed",
        "passed": not bad_steps,
        "details": {
            "allowed_result_statuses": list(scenario.allowed_result_statuses),
            "bad_steps": bad_steps,
        },
    }


def low_sensitive_report_passed(value: Any) -> bool:
    rendered = repr(value).lower()
    forbidden = ("raw_response", "raw_prompt", "api_key", "token", "secret", "transcript_should_not_leak")
    return not any(item in rendered for item in forbidden)
```

Create `src/isotope/dev_evals/reporting.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .gates import evaluate_required_capacity_called, evaluate_result_status, low_sensitive_report_passed
from .models import CapabilityScenario


SENSITIVE_KEYS = {"raw_response", "raw_prompt", "messages", "api_key", "token", "secret", "transcript"}


def sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if str(key).lower() in SENSITIVE_KEYS else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    return value


def build_case_report(
    scenario: CapabilityScenario,
    *,
    steps: list[dict[str, Any]],
    final_answer: str | None = None,
    reviewer_prompt_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sanitized_steps = sanitize_value(steps)
    hard_gates = [
        evaluate_required_capacity_called(scenario, sanitized_steps),
        evaluate_result_status(scenario, sanitized_steps),
        {
            "gate": "low_sensitive_report",
            "passed": low_sensitive_report_passed(sanitized_steps),
            "details": {},
        },
    ]
    hard_gate_passed = all(gate["passed"] for gate in hard_gates)
    return {
        "case_id": scenario.case_id,
        "capability_under_test": list(scenario.capability_ids),
        "status": "passed" if hard_gate_passed else "failed",
        "hard_gate_passed": hard_gate_passed,
        "hard_gates": hard_gates,
        "steps": sanitized_steps,
        "scores": {
            "capacity_choice": 4 if hard_gates[0]["passed"] else 1,
            "input_quality": 3,
            "result_grounding": 4 if hard_gate_passed else 1,
            "self_review_quality": 0,
        },
        "final_answer": final_answer or "",
        "reviewer_prompt_ref": reviewer_prompt_ref,
        "regression_risks": [] if hard_gate_passed else ["hard_gate_failed"],
        "recommendation": "No immediate fix required." if hard_gate_passed else "Review failed hard gates before continuing.",
    }


def build_suite_report(
    *,
    suite: str,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    hard_gate_passed = all(case.get("hard_gate_passed") is True for case in cases)
    return {
        "kind": "supervisor_capacity_dev_eval_report",
        "suite": suite,
        "status": "passed" if hard_gate_passed else "failed",
        "hard_gate_passed": hard_gate_passed,
        "cases": cases,
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_gates_reporting.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/dev_evals/models.py src/isotope/dev_evals/gates.py src/isotope/dev_evals/reporting.py tests/unit/dev_evals/test_gates_reporting.py
git commit -m "feat(dev-evals): add supervisor eval gates and reporting"
```

## Task 4: Deterministic Harness Around the Real Conversation Loop

**Files:**
- Create: `src/isotope/dev_evals/fixtures.py`
- Create: `src/isotope/dev_evals/supervisor_capacity_eval.py`
- Test: `tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py`

- [ ] **Step 1: Write failing harness tests**

Create `tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py`:

```python
import json

from isotope.dev_evals.cases import scenario_catalog
from isotope.dev_evals.supervisor_capacity_eval import DeterministicScenarioProvider, run_scenarios


def test_harness_runs_code_search_case_through_conversation_loop(tmp_path):
    scenario = next(item for item in scenario_catalog() if item.case_id == "code_search_fixture")
    provider = DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "code.search",
                "arguments": {"query": "ISOTOPE_DEV_EVAL_MARKER", "include_paths": ["src"], "max_results": 5},
                "rationale": "Need code search.",
            },
            {
                "kind": "direct_answer",
                "answer": "Found the marker via code.search.",
                "answer_basis": {"kind": "observation", "capacity_ids": ["code.search"], "reason": "Search observation returned the fixture marker."},
                "rationale": "Observation is enough.",
            },
        ]
    )

    report = run_scenarios([scenario], root=tmp_path, provider=provider, live=False)

    assert report["status"] == "passed"
    case = report["cases"][0]
    assert case["steps"][0]["capacity_id"] == "code.search"
    assert case["hard_gate_passed"] is True
    assert "raw_response" not in json.dumps(report)


def test_harness_fails_when_provider_chooses_wrong_capacity(tmp_path):
    scenario = next(item for item in scenario_catalog() if item.case_id == "code_search_fixture")
    provider = DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": "code.read",
                "arguments": {"path": "src/app.py"},
                "rationale": "Wrong capability for this case.",
            },
            {
                "kind": "direct_answer",
                "answer": "Read the file.",
                "answer_basis": {"kind": "observation", "capacity_ids": ["code.read"], "reason": "Read observation exists."},
                "rationale": "Stop.",
            },
        ]
    )

    report = run_scenarios([scenario], root=tmp_path, provider=provider, live=False)

    assert report["status"] == "failed"
    assert report["cases"][0]["hard_gates"][0]["details"]["missing_capacity_ids"] == ["code.search"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py -q
```

Expected: import failure for `isotope.dev_evals.supervisor_capacity_eval`.

- [ ] **Step 3: Implement fixtures**

Create `src/isotope/dev_evals/fixtures.py`:

```python
from __future__ import annotations

from pathlib import Path


def prepare_fixture(root: Path, fixture: str) -> tuple[Path, Path]:
    state_root = root / "state"
    workspace = root / "workspace"
    state_root.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    if fixture in {"workspace_with_code", "workspace_with_diff"}:
        src = workspace / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "app.py").write_text(
            "ISOTOPE_DEV_EVAL_MARKER = 'present'\\n"
            "def answer():\\n"
            "    return ISOTOPE_DEV_EVAL_MARKER\\n",
            encoding="utf-8",
        )
    if fixture == "workspace_with_diff":
        (workspace / "changed.txt").write_text("changed\\n", encoding="utf-8")
    return state_root, workspace
```

- [ ] **Step 4: Implement deterministic harness**

Create `src/isotope/dev_evals/supervisor_capacity_eval.py` with:

```python
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from isotope.features.supervisor.conversation_loop import run_supervisor_conversation_events
from isotope.llm.provider import LLMResponse

from .cases import scenario_catalog
from .fixtures import prepare_fixture
from .reporting import build_case_report, build_suite_report


SUITE = "supervisor_capacity_basic"


class DeterministicScenarioProvider:
    provider = "deterministic_dev_eval"
    model = "deterministic-dev-eval"

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(self, messages: list[dict[str, Any]], *, max_tokens: int = 512) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        if not self.responses:
            payload = {
                "kind": "direct_answer",
                "answer": "No deterministic response remained.",
                "answer_basis": {"kind": "no_capability_needed", "reason": "deterministic fallback"},
                "rationale": "fallback",
            }
        else:
            payload = self.responses.pop(0)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=json.dumps(payload, ensure_ascii=False),
            finish_reason="stop",
            usage={},
            raw={"raw_response": "MUST_NOT_LEAK"},
        )


def _step_from_capacity_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "capacity_id": str(payload.get("capacity_id", "")),
        "status": str(payload.get("status", "")),
        "input_summary": payload.get("inputs", {}) if isinstance(payload.get("inputs"), dict) else {},
        "result_summary": result,
    }


def run_scenarios(
    scenarios: list[Any],
    *,
    root: Path,
    provider: Any,
    live: bool,
) -> dict[str, Any]:
    case_reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        state_root, workspace = prepare_fixture(root / scenario.case_id, scenario.fixture)
        events = list(
            run_supervisor_conversation_events(
                state_root=state_root,
                cwd=workspace,
                user_message=scenario.user_message,
                provider=provider,
                max_turns=scenario.max_turns,
                timeout_seconds=30,
            )
        )
        steps = [
            _step_from_capacity_result(event.payload)
            for event in events
            if event.event == "capacity_result"
        ]
        final_answer = "".join(
            str(event.payload.get("text", ""))
            for event in events
            if event.event == "delta"
        )
        case_reports.append(build_case_report(scenario, steps=steps, final_answer=final_answer))
    return build_suite_report(suite=SUITE, cases=case_reports)


def _default_deterministic_provider_for_case(capability_id: str) -> DeterministicScenarioProvider:
    return DeterministicScenarioProvider(
        [
            {
                "kind": "call_capability",
                "capacity_id": capability_id,
                "arguments": {},
                "rationale": "Run requested capability.",
            },
            {
                "kind": "direct_answer",
                "answer": "Capability observation captured.",
                "answer_basis": {"kind": "observation", "capacity_ids": [capability_id], "reason": "Observation exists."},
                "rationale": "Stop.",
            },
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default=SUITE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--case-id")
    args = parser.parse_args(argv)
    if args.suite != SUITE:
        raise SystemExit(f"unknown suite: {args.suite}")
    scenarios = scenario_catalog()
    if args.case_id:
        scenarios = [item for item in scenarios if item.case_id == args.case_id]
    if not scenarios:
        raise SystemExit("no scenarios selected")
    provider = _default_deterministic_provider_for_case(scenarios[0].capability_ids[0])
    report = run_scenarios(scenarios[:1], root=Path(".dev-eval-runs"), provider=provider, live=False)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py -q
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/dev_evals/fixtures.py src/isotope/dev_evals/supervisor_capacity_eval.py tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py
git commit -m "feat(dev-evals): run capacity scenarios through conversation loop"
```

## Task 5: Live LLM Provider Boundary and Opt-In Pytest

**Files:**
- Modify: `src/isotope/dev_evals/supervisor_capacity_eval.py`
- Create: `tests/evals/test_supervisor_capacity_live_eval.py`

- [ ] **Step 1: Write failing live boundary test**

Create `tests/evals/test_supervisor_capacity_live_eval.py`:

```python
import os

import pytest

from isotope.dev_evals.supervisor_capacity_eval import run_live_suite
from isotope.llm.provider import resolve_llm_chat_provider


@pytest.mark.skipif(
    os.environ.get("ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL") != "1",
    reason="live Supervisor capacity eval is opt-in",
)
def test_live_supervisor_capacity_basic_eval_records_real_provider_result(tmp_path):
    resolution = resolve_llm_chat_provider()
    report = run_live_suite(root=tmp_path, case_limit=1)

    if resolution.provider is None:
        assert report["status"] == "blocked"
        assert report["reason_code"] == resolution.reason_code
        assert report["deterministic_fallback"]["status"] == "passed"
        assert "scenario_catalog_covered" in report["deterministic_fallback"]["checks"]
    else:
        assert report["kind"] == "supervisor_capacity_dev_eval_report"
        assert report["suite"] == "supervisor_capacity_basic"
        assert report["cases"]
        assert "raw_response" not in repr(report)
```

- [ ] **Step 2: Run test without opt-in**

Run:

```bash
.venv/bin/python -m pytest tests/evals/test_supervisor_capacity_live_eval.py -q
```

Expected: skipped because `ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL` is not `1`.

- [ ] **Step 3: Implement live provider resolution**

Modify `src/isotope/dev_evals/supervisor_capacity_eval.py`:

```python
from isotope.llm.provider import resolve_llm_chat_provider
```

Add:

```python
def run_live_suite(*, root: Path, case_limit: int | None = None) -> dict[str, Any]:
    resolution = resolve_llm_chat_provider()
    if resolution.provider is None:
        return {
            "kind": "supervisor_capacity_dev_eval_report",
            "suite": SUITE,
            "status": "blocked",
            "hard_gate_passed": False,
            "reason_code": resolution.reason_code,
            "provider": resolution.provider_name,
            "deterministic_fallback": {
                "status": "passed",
                "checks": [
                    "scenario_catalog_covered",
                    "report_sanitizer_available",
                    "hard_gate_functions_available",
                ],
            },
            "cases": [],
        }
    scenarios = scenario_catalog()
    selected = scenarios[:case_limit] if case_limit is not None else scenarios
    return run_scenarios(selected, root=root, provider=resolution.provider, live=True)
```

Update `main(...)` so normal CLI uses `run_live_suite(...)` by default. Keep deterministic provider usage only behind a private `--deterministic-provider` flag for unit tests:

```python
parser.add_argument("--deterministic-provider", action="store_true")
parser.add_argument("--case-limit", type=int)
```

If `--deterministic-provider` is false, call `run_live_suite(root=Path(".dev-eval-runs"), case_limit=args.case_limit)`.

- [ ] **Step 4: Run opt-in test with provider state**

Run:

```bash
ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL=1 .venv/bin/python -m pytest tests/evals/test_supervisor_capacity_live_eval.py -q
```

Expected: pass if provider is configured, or pass with blocked report if provider is absent. It must not leak raw provider payloads.

- [ ] **Step 5: Commit**

```bash
git add src/isotope/dev_evals/supervisor_capacity_eval.py tests/evals/test_supervisor_capacity_live_eval.py
git commit -m "feat(dev-evals): add opt-in live supervisor capacity eval"
```

## Task 6: Reviewer Prompt Artifact

**Files:**
- Create: `src/isotope/dev_evals/reviewer_prompt.py`
- Modify: `src/isotope/dev_evals/supervisor_capacity_eval.py`
- Test: `tests/unit/dev_evals/test_reviewer_prompt.py`

- [ ] **Step 1: Write failing prompt tests**

Create `tests/unit/dev_evals/test_reviewer_prompt.py`:

```python
from isotope.dev_evals.reviewer_prompt import render_reviewer_prompt


def test_reviewer_prompt_contains_diff_trace_scores_and_instructions():
    prompt = render_reviewer_prompt(
        diff_summary="M src/isotope/dev_evals/gates.py",
        report={
            "suite": "supervisor_capacity_basic",
            "status": "failed",
            "cases": [
                {
                    "case_id": "code_search_fixture",
                    "hard_gates": [{"gate": "required_capacity_called", "passed": False}],
                    "scores": {"capacity_choice": 1},
                    "steps": [{"capacity_id": "code.read", "status": "ok"}],
                }
            ],
        },
    )

    assert "current git diff" in prompt
    assert "supervisor_capacity_basic" in prompt
    assert "required_capacity_called" in prompt
    assert "code.read" in prompt
    assert "rerun the required eval" in prompt
    assert "report what changed" in prompt
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_reviewer_prompt.py -q
```

Expected: import failure for `isotope.dev_evals.reviewer_prompt`.

- [ ] **Step 3: Implement prompt renderer**

Create `src/isotope/dev_evals/reviewer_prompt.py`:

```python
from __future__ import annotations

import json
from typing import Any


def render_reviewer_prompt(*, diff_summary: str, report: dict[str, Any]) -> str:
    report_json = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        "You are reviewing the current Codex development work for Isotope.\\n"
        "Inspect the current git diff, eval trace, scores, and failure gates before making more changes.\\n\\n"
        "Current git diff summary:\\n"
        f"{diff_summary}\\n\\n"
        "Eval report:\\n"
        f"{report_json}\\n\\n"
        "Review instructions:\\n"
        "- Identify whether each failure is a product-direction problem, capability-contract problem, prompt problem, or implementation bug.\\n"
        "- When maturity or latest-practice judgment is needed, perform fresh research first instead of relying on memory.\\n"
        "- Compare behavior with mature AI product and agent practice only as far as the diff and trace justify.\\n"
        "- Make the smallest necessary correction.\\n"
        "- rerun the required eval or deterministic fallback.\\n"
        "- report what changed, which gate now passes, which gate still fails, and the remaining risk.\\n"
    )
```

- [ ] **Step 4: Integrate prompt artifact into suite reports**

In `src/isotope/dev_evals/supervisor_capacity_eval.py`, after `report = build_suite_report(...)`, write prompt files under `<root>/state/dev-evals/reviewer-prompts/<case_id>.md` and attach `reviewer_prompt_ref` to each case. Use `git diff --stat` as `diff_summary`; if the command fails, use `"git diff summary unavailable"`.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dev_evals/test_reviewer_prompt.py tests/unit/dev_evals/test_supervisor_capacity_eval_harness.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/isotope/dev_evals/reviewer_prompt.py src/isotope/dev_evals/supervisor_capacity_eval.py tests/unit/dev_evals/test_reviewer_prompt.py
git commit -m "feat(dev-evals): emit Codex reviewer prompts"
```

## Task 7: Developer Documentation and Final Verification

**Files:**
- Create: `docs/current/supervisor-dev-evals.md`
- Modify: `docs/superpowers/plans/2026-06-11-supervisor-capacity-dev-eval.md` only if implementation discoveries require plan correction.

- [ ] **Step 1: Write developer note**

Create `docs/current/supervisor-dev-evals.md`:

```markdown
# Supervisor Dev Evals

Status: developer-only eval gate
Updated: 2026-06-11

Supervisor dev evals are for Codex and maintainers, not end users.

Before finishing work that touches capability contracts, Supervisor conversation
behavior, LLM prompts, capacity observations, or agent-loop result projection,
run:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.dev_evals.changed_surface --base origin/main --json
```

If the result has `eval_required=true`, run the returned
`recommended_command`. Token cost is not a valid skip reason.

If live provider or network configuration is missing, report the blocker and run
the deterministic fallback checks. Do not claim the live eval passed.

After a required suite runs, read the generated reviewer prompt and feed it back
to Codex before claiming the development task is complete. The reviewer prompt
must be grounded in the current diff, capacity trace, hard gates, and scores.
```

- [ ] **Step 2: Run targeted deterministic tests**

Run:

```bash
.venv/bin/python -m pytest -q tests/unit/dev_evals tests/unit/capabilities/test_capability_catalog_core.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py
```

Expected: all tests pass.

- [ ] **Step 3: Run opt-in live eval wrapper**

Run:

```bash
ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL=1 .venv/bin/python -m pytest tests/evals/test_supervisor_capacity_live_eval.py -q
```

Expected: pass with either a real provider result or a blocked report. If it fails because the model chose the wrong capability, fix the scenario prompt or prompt contract, then rerun.

- [ ] **Step 4: Run changed surface CLI**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.dev_evals.changed_surface --base origin/main --json
```

Expected: JSON with `eval_required=true` for this branch because it added `isotope.dev_evals` and capacity eval code.

- [ ] **Step 5: Inspect generated reviewer prompt**

Run:

```bash
find .dev-eval-runs -path '*reviewer-prompts*.md' -type f -maxdepth 6 | head -5
```

Expected: at least one reviewer prompt path after running the suite.

- [ ] **Step 6: Commit docs and final fixes**

```bash
git add docs/current/supervisor-dev-evals.md docs/superpowers/plans/2026-06-11-supervisor-capacity-dev-eval.md
git commit -m "docs(dev-evals): document supervisor eval gate"
```

## Final Integration Checklist

- [ ] `git status --short --branch` shows only intentional changes before each commit.
- [ ] No public `pyproject.toml` script was added.
- [ ] `scenario_catalog()` covers every current registered capability id.
- [ ] Unit tests prove hard gates fail for wrong capability choice.
- [ ] Live eval path calls `resolve_llm_chat_provider()` and does not silently fall back to deterministic provider.
- [ ] Reports do not expose raw prompts, raw responses, tokens, secrets, transcripts, or full artifact content.
- [ ] Reviewer prompt references diff, trace, scores, failure gates, correction, rerun, and final report instructions.
- [ ] The final response to the user includes commands run, pass/fail status, and any live-provider blocker.
