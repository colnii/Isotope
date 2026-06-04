# Native Coding Product Maturity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make native coding usable from Supervisor/Desktop chat with one user-facing `goal`, while the existing agent loop gathers code context, executes in an isolated workspace, verifies, and returns reviewable evidence.

**Architecture:** Do not create a separate coding loop. Add `coding_task.run` as a product entrypoint that Supervisor routes into the existing in-process agent loop; hide `cwd`, `root`, `run_id`, `execution_id`, and `workspace_id` from user/model-facing contracts; inject those fields internally when executing capability calls. The model learns the repo through `code.search` and `code.read` observations, not by being asked to fill environment fields.

**Tech Stack:** Python 3.13, pytest, existing `CapabilityCatalog`, `CapabilityRunner`, `InProcessServer`, agent-loop provider planner, Supervisor conversation stream, low-sensitive capacity summaries.

---

## Scope

In this plan:

- `coding_task.execute` stays as the low-level executor.
- `coding_task.run` becomes the product entrypoint.
- Existing agent-loop functions are extended; no new planner loop is introduced.
- Source workspace remains unchanged. Isolated changes live under the runtime state root.
- `cwd/root` are system routing inputs. They are not user form fields and are not model-authored arguments.

Out of this plan:

- Applying the isolated diff back to the source workspace.
- Automatic commit, push, or merge.
- Broad package installation.
- Replacing `coding_task.execute`.

## File Structure

- Modify `src/isotope/platform/schemas/input_contract.py`
  - Add helpers for system-only and public contract views.
- Modify `src/isotope/capabilities/catalog.py`
  - Mark routing/provenance inputs with `x-system-input`.
  - Register `coding_task.run`.
- Create `src/isotope/capabilities/coding_run.py`
  - Define `coding_task.run` constants and direct-run guard.
- Modify `src/isotope/capabilities/runner.py`
  - Describe and validate `coding_task.run`; reject direct execution outside Supervisor.
- Modify `src/isotope/features/supervisor/conversation_loop.py`
  - Hide system inputs from the manifest and route `coding_task.run` to the existing agent loop.
- Modify `src/isotope/agents/loop/step.py`
  - Merge internal system inputs into capability calls and prevent model overrides.
- Modify `src/isotope/agents/loop/provider_planner.py`
  - Pass safe coding task context to the model and private system inputs to execution.
- Modify `src/isotope/agents/loop/planner_adapter.py`
  - Reject model-authored private system input keys.
- Modify `src/isotope/agents/loop/context.py`
  - Add safe extra default context merging.
- Create `src/isotope/features/supervisor/native_coding_run.py`
  - Adapter that repeatedly calls existing provider planner ticks for a coding run.
- Modify `src/isotope/features/supervisor/commands/capacity_summary.py`
  - Summarize native coding results without raw patch, argv, transcript, or raw file content.
- Tests:
  - `tests/unit/interfaces/http/test_input_contract_schema.py`
  - `tests/unit/capabilities/test_capability_runner_thin_shell.py`
  - `tests/unit/agents/loop/test_agent_loop_step_driver.py`
  - `tests/unit/agents/loop/test_agent_loop_provider_planner.py`
  - `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
  - `tests/unit/features/supervisor/test_capacity_module_boundaries.py`

## Task 1: Add Public Contract Views For System Inputs

**Files:**
- Modify: `src/isotope/platform/schemas/input_contract.py`
- Test: `tests/unit/interfaces/http/test_input_contract_schema.py`

- [ ] **Step 1: Write the failing helper tests**

Append to `tests/unit/interfaces/http/test_input_contract_schema.py`:

```python
def test_public_contract_helpers_exclude_system_inputs():
    contract = {
        "type": "object",
        "required": ["goal", "cwd", "root"],
        "properties": {
            "goal": {"type": "string"},
            "cwd": {"type": "string", "x-system-input": True},
            "root": {"type": "string", "x-system-input": True},
        },
    }

    from isotope.platform.schemas.input_contract import (
        public_contract_properties,
        public_required_contract_keys,
        system_contract_keys,
    )

    assert list(public_contract_properties(contract)) == ["goal"]
    assert public_required_contract_keys(contract) == ["goal"]
    assert system_contract_keys(contract) == ["cwd", "root"]
```

- [ ] **Step 2: Run the helper test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/interfaces/http/test_input_contract_schema.py::test_public_contract_helpers_exclude_system_inputs -q
```

Expected: fail because the new helpers do not exist.

- [ ] **Step 3: Implement the helpers**

Add to `src/isotope/platform/schemas/input_contract.py`:

```python
def public_contract_properties(input_contract: Any) -> dict[str, Any]:
    properties = contract_properties(input_contract)
    return {
        name: schema
        for name, schema in properties.items()
        if isinstance(schema, Mapping) and schema.get("x-system-input") is not True
    }


def system_contract_keys(input_contract: Any) -> list[str]:
    properties = contract_properties(input_contract)
    return [
        name
        for name, schema in properties.items()
        if isinstance(schema, Mapping) and schema.get("x-system-input") is True
    ]


def public_required_contract_keys(input_contract: Any) -> list[str]:
    system_keys = set(system_contract_keys(input_contract))
    return [
        key
        for key in required_contract_keys(input_contract)
        if key not in system_keys
    ]
```

If the module has `__all__`, add the three helper names.

- [ ] **Step 4: Run the helper test and verify it passes**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/interfaces/http/test_input_contract_schema.py::test_public_contract_helpers_exclude_system_inputs -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/isotope/platform/schemas/input_contract.py tests/unit/interfaces/http/test_input_contract_schema.py
git commit -m "feat(capabilities): add public input contract views"
```

## Task 2: Hide Routing Inputs In Capability Manifests

**Files:**
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Write the failing catalog marker test**

Append near code access tests in `tests/unit/capabilities/test_capability_runner_thin_shell.py`:

```python
def test_coding_related_capabilities_mark_routing_inputs_as_system_only():
    runner = _runner()

    for capability_id in (
        "code.search",
        "code.read",
        "code.apply_patch",
        "test.run",
        "coding_task.execute",
    ):
        description = runner.describe_capability(capability_id)
        properties = description["input_contract"]["properties"]
        assert properties["root"]["x-system-input"] is True
        assert properties["cwd"]["x-system-input"] is True
```

- [ ] **Step 2: Run the marker test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/capabilities/test_capability_runner_thin_shell.py::test_coding_related_capabilities_mark_routing_inputs_as_system_only -q
```

Expected: fail because existing catalog entries do not mark `root/cwd`.

- [ ] **Step 3: Mark routing fields in the catalog**

In `src/isotope/capabilities/catalog.py`, add `"x-system-input": True` to `root` and `cwd` properties for these capability ids:

```text
code.search
code.read
code.apply_patch
test.run
artifact.changed_files
artifact.diff_summary
workspace.materialize
workspace.status
workspace.release
coding_task.execute
```

Keep each capability's internal `required` list unchanged. This preserves direct runner validation while letting public manifests show a smaller input surface.

- [ ] **Step 4: Write the failing Supervisor manifest test**

Append to `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`:

```python
def test_conversation_manifest_hides_system_routing_inputs(tmp_path):
    provider = RecordingConversationProvider(["你好，我在。"])

    list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=tmp_path / "repo",
            user_message="你好",
            provider=provider,
        )
    )

    system_prompt = provider.calls[0]["messages"][0]["content"]
    assert '"code.search"' in system_prompt
    assert '"query"' in system_prompt
    assert '"cwd"' not in system_prompt
    assert '"root"' not in system_prompt
```

- [ ] **Step 5: Run the manifest test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_manifest_hides_system_routing_inputs -q
```

Expected: fail because public manifest generation still uses raw contract properties.

- [ ] **Step 6: Use public contract views in Supervisor manifest generation**

Modify imports in `src/isotope/features/supervisor/conversation_loop.py`:

```python
from isotope.platform.schemas.input_contract import (
    public_contract_properties,
    public_required_contract_keys,
)
```

In `_conversation_capability_summary(...)`, compute:

```python
public_properties = public_contract_properties(input_contract)
public_required = public_required_contract_keys(input_contract)
```

Use `public_properties` for `input_properties` and `public_required` for `required_inputs`.

- [ ] **Step 7: Run marker and manifest tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_coding_related_capabilities_mark_routing_inputs_as_system_only \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_manifest_hides_system_routing_inputs \
  -q
```

Expected: both pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/isotope/capabilities/catalog.py src/isotope/features/supervisor/conversation_loop.py tests/unit/capabilities/test_capability_runner_thin_shell.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "feat(supervisor): hide routing inputs from capability manifests"
```

## Task 3: Register `coding_task.run` As A Product Entrypoint

**Files:**
- Create: `src/isotope/capabilities/coding_run.py`
- Modify: `src/isotope/capabilities/catalog.py`
- Modify: `src/isotope/capabilities/runner.py`
- Test: `tests/unit/capabilities/test_capability_runner_thin_shell.py`

- [ ] **Step 1: Write the failing discovery and direct-run tests**

Append near existing coding task tests:

```python
def test_runner_discovers_coding_task_run_from_default_catalog():
    runner = _runner()

    assert "coding_task.run" in _ids(runner.list_capabilities())
    description = runner.describe_capability("coding_task.run")

    assert description["input_contract"]["required"] == ["goal"]
    properties = description["input_contract"]["properties"]
    assert properties["goal"]["type"] == "string"
    for name in ("root", "cwd", "run_id", "execution_id", "workspace_id"):
        assert properties[name]["x-system-input"] is True
    assert "uses_existing_agent_loop" in description["safety_boundaries"]
    assert "does_not_replace_coding_task_execute" in description["safety_boundaries"]


def test_runner_rejects_direct_coding_task_run_execution(tmp_path):
    with pytest.raises(ValueError, match="coding_task.run must be routed through Supervisor agent loop"):
        _runner().run_capability(
            "coding_task.run",
            root_path=tmp_path,
            inputs={"goal": "Change src/app.py value to 2."},
        )
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_coding_task_run_from_default_catalog \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_rejects_direct_coding_task_run_execution \
  -q
```

Expected: discovery fails because `coding_task.run` is not registered.

- [ ] **Step 3: Add `coding_run.py`**

Create `src/isotope/capabilities/coding_run.py`:

```python
"""Product-level native coding capability metadata."""

from __future__ import annotations

from typing import Any, Mapping


CODING_TASK_RUN_CAPABILITY = "coding_task.run"


def is_coding_run_capability(capability_id: str) -> bool:
    return capability_id == CODING_TASK_RUN_CAPABILITY


def validate_coding_run_inputs(inputs: Mapping[str, Any] | None) -> dict[str, Any]:
    input_mapping = dict(inputs or {})
    goal = input_mapping.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("goal must be a non-empty string")
    input_mapping["goal"] = goal.strip()
    return input_mapping


def reject_direct_coding_task_run() -> dict[str, Any]:
    raise ValueError("coding_task.run must be routed through Supervisor agent loop")
```

- [ ] **Step 4: Register `coding_task.run` in the catalog**

Add a `Capability(...)` near `coding_task.execute` in `src/isotope/capabilities/catalog.py`:

```python
Capability(
    capability_id="coding_task.run",
    title="Native Coding Task Run",
    description=(
        "Run a native coding task through the existing agent loop, bounded "
        "code context capabilities, isolated execution, and artifact evidence."
    ),
    maturity="v0.3",
    shelf="product_candidate",
    domain_tags=("native", "coding", "agent-loop", "workspace", "artifact"),
    input_contract={
        "type": "object",
        "required": ["goal"],
        "properties": {
            "goal": {"type": "string", "description": "Natural-language coding goal."},
            "include_paths": {"type": "array", "items": {"type": "string"}, "default": ["."]},
            "forbidden_paths": {"type": "array", "items": {"type": "string"}, "default": []},
            "verification_intent": {"type": "string"},
            "max_steps": {"type": "integer", "default": 6},
            "timeout_seconds": {"type": "integer", "default": 120},
            "root": {"type": "string", "x-system-input": True},
            "cwd": {"type": "string", "x-system-input": True},
            "run_id": {"type": "string", "x-system-input": True},
            "execution_id": {"type": "string", "x-system-input": True},
            "workspace_id": {"type": "string", "x-system-input": True},
        },
    },
    output_contract={
        "type": "object",
        "fields": ["status", "workspace_id", "changed_files", "verification", "artifact_refs", "next_action"],
    },
    safety_boundaries=(
        "uses_existing_agent_loop",
        "agent_loop_orchestrated",
        "isolated_workspace_write_only",
        "source_workspace_write_requires_explicit_apply",
        "does_not_replace_coding_task_execute",
        "low_sensitive_summary_only",
    ),
    default_enabled=True,
    network_required=False,
)
```

- [ ] **Step 5: Wire runner validation and direct-run rejection**

Modify imports in `src/isotope/capabilities/runner.py`:

```python
from .coding_run import (
    CODING_TASK_RUN_CAPABILITY,
    is_coding_run_capability,
    reject_direct_coding_task_run,
    validate_coding_run_inputs,
)
```

In planning and running validation, add:

```python
if is_coding_run_capability(capability_id):
    input_mapping = validate_coding_run_inputs(input_mapping)
```

In `run_capability(...)` dispatch:

```python
if capability_id == CODING_TASK_RUN_CAPABILITY:
    return reject_direct_coding_task_run()
```

- [ ] **Step 6: Run discovery and direct-run tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_coding_task_run_from_default_catalog \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_rejects_direct_coding_task_run_execution \
  tests/unit/capabilities/test_capability_runner_thin_shell.py::test_runner_discovers_coding_task_execute_from_default_catalog \
  -q
```

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/isotope/capabilities/coding_run.py src/isotope/capabilities/catalog.py src/isotope/capabilities/runner.py tests/unit/capabilities/test_capability_runner_thin_shell.py
git commit -m "feat(capabilities): add native coding run entrypoint"
```

## Task 4: Inject System Inputs Without Model Authorship

**Files:**
- Modify: `src/isotope/agents/loop/step.py`
- Modify: `src/isotope/agents/loop/planner_adapter.py`
- Modify: `src/isotope/agents/loop/provider_planner.py`
- Test: `tests/unit/agents/loop/test_agent_loop_step_driver.py`
- Test: `tests/unit/agents/loop/test_agent_loop_provider_planner.py`

- [ ] **Step 1: Write the failing step-driver injection test**

Append to `tests/unit/agents/loop/test_agent_loop_step_driver.py`:

```python
def test_agent_loop_step_uses_internal_system_inputs_and_ignores_model_routing(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)
    captured: dict[str, Any] = {}

    class RecordingRunner:
        def describe_capability(self, capability_id: str) -> dict[str, Any]:
            return {
                "input_contract": {
                    "type": "object",
                    "required": ["root", "cwd", "query"],
                    "properties": {
                        "query": {"type": "string"},
                        "root": {"type": "string", "x-system-input": True},
                        "cwd": {"type": "string", "x-system-input": True},
                        "run_id": {"type": "string", "x-system-input": True},
                        "execution_id": {"type": "string", "x-system-input": True},
                    },
                }
            }

        def run_capability(self, capability_id: str, *, root_path, inputs):
            captured["inputs"] = dict(inputs)
            return {"kind": "capability_run_result", "capability_id": capability_id, "status": "completed"}

    monkeypatch.setattr("isotope.capabilities.runner.CapabilityRunner", lambda: RecordingRunner())

    api.run_agent_loop_step(
        run_id,
        {
            "step": "call_capability",
            "capability_id": "code.search",
            "inputs": {
                "query": "value",
                "root": "/model/must/not/win",
                "cwd": "/model/must/not/win",
            },
            "_system_inputs": {
                "root": str(tmp_path / "state"),
                "cwd": str(tmp_path / "repo"),
            },
        },
    )

    assert captured["inputs"]["query"] == "value"
    assert captured["inputs"]["root"] == str(tmp_path / "state")
    assert captured["inputs"]["cwd"] == str(tmp_path / "repo")
    assert captured["inputs"]["run_id"] == run_id
    assert captured["inputs"]["execution_id"].startswith("exec_")
```

- [ ] **Step 2: Run the step-driver test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/agents/loop/test_agent_loop_step_driver.py::test_agent_loop_step_uses_internal_system_inputs_and_ignores_model_routing -q
```

Expected: fail because `_system_inputs` is not merged and model `root/cwd` can override system values.

- [ ] **Step 3: Merge only contract-declared system inputs**

Modify imports in `src/isotope/agents/loop/step.py`:

```python
from ...platform.schemas.input_contract import contract_properties, system_contract_keys
```

Replace `_capability_inputs_for_agent_loop(...)` body with:

```python
inputs = _optional_dict(request, "inputs") or {}
request_system_inputs = _optional_dict(request, "_system_inputs") or {}
capability = runner.describe_capability(capability_id)
input_contract = capability.get("input_contract", {})
properties = contract_properties(input_contract)
system_keys = set(system_contract_keys(input_contract))

model_inputs = {
    key: value
    for key, value in inputs.items()
    if key not in system_keys
}
system_inputs: dict[str, Any] = {
    key: value
    for key, value in request_system_inputs.items()
    if key in system_keys
}
if "run_id" in properties or "run_id" in system_keys:
    system_inputs["run_id"] = run_id
if "execution_id" in properties or "execution_id" in system_keys:
    system_inputs["execution_id"] = new_id("exec")
if "workspace_id" in system_keys and "workspace_id" not in system_inputs:
    system_inputs["workspace_id"] = "workspace_coding_task_run_" + new_id("workspace").split("_", 1)[-1]
return {**model_inputs, **system_inputs}
```

- [ ] **Step 4: Write the failing provider-planner private-input test**

Append to `tests/unit/agents/loop/test_agent_loop_provider_planner.py`:

```python
def test_provider_planner_adds_system_inputs_to_execution_not_prompt(tmp_path, monkeypatch):
    api, run_id = _new_run(tmp_path)
    captured: dict[str, Any] = {}

    class RecordingRunner:
        def describe_capability(self, capability_id: str) -> dict[str, Any]:
            return {
                "input_contract": {
                    "type": "object",
                    "required": ["root", "cwd", "query"],
                    "properties": {
                        "query": {"type": "string"},
                        "root": {"type": "string", "x-system-input": True},
                        "cwd": {"type": "string", "x-system-input": True},
                    },
                }
            }

        def run_capability(self, capability_id: str, *, root_path, inputs):
            captured["inputs"] = dict(inputs)
            return {"kind": "capability_run_result", "capability_id": capability_id, "status": "completed"}

    monkeypatch.setattr("isotope.capabilities.runner.CapabilityRunner", lambda: RecordingRunner())
    provider = RecordingPlannerProvider(
        {
            "planner_run_id": "planner-1",
            "basis": {"run_id": run_id, "last_event_id": api.get_agent_loop_control(run_id)["last_event_id"]},
            "decision": {
                "step": "call_capability",
                "request": {"capability_id": "code.search", "inputs": {"query": "value"}},
            },
        }
    )

    api.run_agent_loop_provider_planner_tick(
        run_id,
        provider=provider,
        agent_id="agent-coding",
        tick_id="tick-coding-1",
        decision_id="decision-coding-1",
        capability_system_inputs={"root": str(tmp_path / "state"), "cwd": str(tmp_path / "repo")},
    )

    prompt = provider.calls[0]["messages"][1]["content"]
    assert str(tmp_path / "state") not in prompt
    assert str(tmp_path / "repo") not in prompt
    assert captured["inputs"]["root"] == str(tmp_path / "state")
    assert captured["inputs"]["cwd"] == str(tmp_path / "repo")
```

- [ ] **Step 5: Run the provider-planner test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/agents/loop/test_agent_loop_provider_planner.py::test_provider_planner_adds_system_inputs_to_execution_not_prompt -q
```

Expected: fail because `capability_system_inputs` is not accepted.

- [ ] **Step 6: Add private system input attachment**

In `src/isotope/agents/loop/provider_planner.py`, add parameter:

```python
capability_system_inputs: dict[str, Any] | None = None,
```

Before calling `api.run_agent_loop_real_planner_contract_step(...)`, attach private inputs:

```python
provider_result = _attach_capability_system_inputs(
    provider_result,
    capability_system_inputs,
)
```

Add:

```python
def _attach_capability_system_inputs(
    provider_result: dict[str, Any],
    system_inputs: dict[str, Any] | None,
) -> dict[str, Any]:
    if not system_inputs:
        return provider_result
    result = deepcopy(provider_result)
    parsed = result.get("parsed_planner_output")
    if not isinstance(parsed, dict):
        return result
    decision = parsed.get("decision")
    if not isinstance(decision, dict) or decision.get("step") != "call_capability":
        return result
    request = decision.get("request")
    if not isinstance(request, dict):
        return result
    request["_system_inputs"] = {
        key: value
        for key, value in system_inputs.items()
        if isinstance(key, str)
    }
    return result
```

- [ ] **Step 7: Reject model-authored private system keys**

In `src/isotope/agents/loop/planner_adapter.py`, after copying `request`:

```python
if "_system_inputs" in request:
    raise ValueError("planner request may not provide private system inputs")
```

Then adjust `run_agent_loop_real_planner_contract_step(...)` or `provider_planner.py` so the internally attached `_system_inputs` is added after this check. The simplest route is to attach inside `planner_adapter.run_agent_loop_planner_step(...)` from a separate `planner_output["_private_system_inputs"]` value:

```python
private_system_inputs = planner_output.get("_private_system_inputs")
if isinstance(private_system_inputs, dict) and step == "call_capability":
    request["_system_inputs"] = deepcopy(private_system_inputs)
```

Update `_attach_capability_system_inputs(...)` to set `parsed["_private_system_inputs"]` instead of putting `_system_inputs` directly in `request`.

- [ ] **Step 8: Run injection tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/agents/loop/test_agent_loop_step_driver.py::test_agent_loop_step_uses_internal_system_inputs_and_ignores_model_routing \
  tests/unit/agents/loop/test_agent_loop_provider_planner.py::test_provider_planner_adds_system_inputs_to_execution_not_prompt \
  -q
```

Expected: both pass.

- [ ] **Step 9: Commit Task 4**

```bash
git add src/isotope/agents/loop/step.py src/isotope/agents/loop/planner_adapter.py src/isotope/agents/loop/provider_planner.py tests/unit/agents/loop/test_agent_loop_step_driver.py tests/unit/agents/loop/test_agent_loop_provider_planner.py
git commit -m "feat(agent-loop): inject private capability system inputs"
```

## Task 5: Pass Safe Coding Context To The Existing Planner

**Files:**
- Modify: `src/isotope/agents/loop/context.py`
- Modify: `src/isotope/agents/loop/provider_planner.py`
- Test: `tests/unit/agents/loop/test_agent_loop_provider_planner.py`

- [ ] **Step 1: Write the failing safe-context test**

Append to `tests/unit/agents/loop/test_agent_loop_provider_planner.py`:

```python
def test_provider_planner_receives_coding_goal_without_raw_paths(tmp_path):
    api, run_id = _new_run(tmp_path)
    provider = RecordingPlannerProvider(
        {
            "planner_run_id": "planner-1",
            "basis": {"run_id": run_id, "last_event_id": api.get_agent_loop_control(run_id)["last_event_id"]},
            "decision": {
                "step": "call_capability",
                "request": {"capability_id": "code.search", "inputs": {"query": "value"}},
            },
        }
    )

    api.run_agent_loop_provider_planner_tick(
        run_id,
        provider=provider,
        agent_id="agent-coding",
        tick_id="tick-coding-1",
        decision_id="decision-coding-1",
        default_context_extra={
            "coding_task": {
                "goal": "Change src/app.py value to 2.",
                "workspace_label": "current_project",
                "allowed_capabilities": ["code.search", "code.read", "coding_task.execute"],
                "cwd": str(tmp_path / "repo"),
                "root": str(tmp_path / "state"),
            }
        },
        capability_system_inputs={"root": str(tmp_path / "state"), "cwd": str(tmp_path / "repo")},
    )

    prompt = provider.calls[0]["messages"][1]["content"]
    assert "Change src/app.py value to 2." in prompt
    assert "code.search" in prompt
    assert "current_project" in prompt
    assert str(tmp_path / "repo") not in prompt
    assert str(tmp_path / "state") not in prompt
```

- [ ] **Step 2: Run the safe-context test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/agents/loop/test_agent_loop_provider_planner.py::test_provider_planner_receives_coding_goal_without_raw_paths -q
```

Expected: fail because extra context is not accepted or raw fields are not filtered.

- [ ] **Step 3: Add safe context merging**

In `src/isotope/agents/loop/context.py`, add:

```python
def merge_agent_loop_default_context(
    default_context: dict[str, Any],
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(default_context)
    if isinstance(extra, dict):
        for key, value in extra.items():
            if isinstance(key, str) and isinstance(value, (dict, list, str, int, float, bool)):
                merged[key] = value
    return merged
```

Modify `safe_agent_loop_default_context(...)` to include only safe coding fields:

```python
coding_task = default_context.get("coding_task")
if isinstance(coding_task, dict):
    safe["coding_task"] = {
        key: value
        for key, value in coding_task.items()
        if key in {"goal", "workspace_label", "allowed_capabilities", "verification_intent"}
        and isinstance(value, (str, list))
    }
```

- [ ] **Step 4: Use extra context in provider planner**

In `src/isotope/agents/loop/provider_planner.py`, import `merge_agent_loop_default_context` and add parameter:

```python
default_context_extra: dict[str, Any] | None = None,
```

After `build_agent_loop_default_context(...)`:

```python
default_context = merge_agent_loop_default_context(default_context, default_context_extra)
```

- [ ] **Step 5: Run provider-planner context tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/agents/loop/test_agent_loop_provider_planner.py::test_provider_planner_receives_coding_goal_without_raw_paths \
  tests/unit/agents/loop/test_agent_loop_provider_planner.py::test_provider_planner_adds_system_inputs_to_execution_not_prompt \
  -q
```

Expected: both pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/isotope/agents/loop/context.py src/isotope/agents/loop/provider_planner.py tests/unit/agents/loop/test_agent_loop_provider_planner.py
git commit -m "feat(agent-loop): pass safe coding context to planner"
```

## Task 6: Route `coding_task.run` Through Supervisor Agent Loop

**Files:**
- Create: `src/isotope/features/supervisor/native_coding_run.py`
- Modify: `src/isotope/features/supervisor/conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`

- [ ] **Step 1: Write the failing end-to-end Supervisor test**

Append to `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`:

```python
def test_conversation_loop_runs_coding_task_run_through_existing_agent_loop(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    provider = RecordingConversationProvider(
        [
            json.dumps(
                {
                    "kind": "call_capability",
                    "capacity_id": "coding_task.run",
                    "arguments": {"goal": "Change src/app.py value to 2."},
                    "rationale": "Use native coding.",
                }
            ),
            json.dumps(
                {
                    "planner_run_id": "planner-search",
                    "basis": {"run_id": "filled-by-test-helper", "last_event_id": "filled-by-test-helper"},
                    "decision": {
                        "step": "call_capability",
                        "request": {"capability_id": "code.search", "inputs": {"query": "value", "include_paths": ["src"]}},
                    },
                }
            ),
            json.dumps(
                {
                    "planner_run_id": "planner-read",
                    "basis": {"run_id": "filled-by-test-helper", "last_event_id": "filled-by-test-helper"},
                    "decision": {
                        "step": "call_capability",
                        "request": {"capability_id": "code.read", "inputs": {"path": "src/app.py"}},
                    },
                }
            ),
            json.dumps(
                {
                    "planner_run_id": "planner-execute",
                    "basis": {"run_id": "filled-by-test-helper", "last_event_id": "filled-by-test-helper"},
                    "decision": {
                        "step": "call_capability",
                        "request": {
                            "capability_id": "coding_task.execute",
                            "inputs": {
                                "goal": "Change src/app.py value to 2.",
                                "patch": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n",
                                "argv": [
                                    "python3",
                                    "-c",
                                    "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'",
                                ],
                                "allowed_commands": ["python3"],
                                "include_paths": ["src"],
                            },
                        },
                    },
                }
            ),
            json.dumps({"kind": "direct_answer", "answer": "改动已验证，等待你审阅。"}),
        ]
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="把 src/app.py 的 value 改成 2。",
            provider=provider,
            max_turns=4,
        )
    )

    assert events[0].event == "capacity_start"
    assert events[0].payload["capacity_id"] == "coding_task.run"
    assert events[1].event == "capacity_result"
    assert events[1].payload["status"] == "ok"
    summary = events[1].payload["result_summary"]
    assert summary["agent_loop_coding_status"] == "verified"
    assert summary["agent_loop_coding_context_calls"] >= 2
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    rendered = json.dumps([event.payload for event in events], ensure_ascii=False)
    assert "value = 2" not in rendered
    assert "argv" not in rendered
```

If the local fake provider requires exact planner basis ids, wrap it in a helper that rewrites `"filled-by-test-helper"` to the current `run_id` and `last_event_id` before returning the JSON string.

- [ ] **Step 2: Run the Supervisor test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_runs_coding_task_run_through_existing_agent_loop -q
```

Expected: fail because `coding_task.run` is still handled as a direct capability run.

- [ ] **Step 3: Create the Supervisor adapter**

Create `src/isotope/features/supervisor/native_coding_run.py`:

```python
"""Supervisor adapter for product-level native coding.

This module drives the existing agent loop. It is not a separate coding loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from isotope.platform.ids import new_id
from isotope.runtime.in_process import InProcessServer


CODING_TASK_RUN_CAPABILITY = "coding_task.run"


def run_native_coding_agent_loop(
    *,
    state_root: Path,
    cwd: Path,
    goal: str,
    inputs: Mapping[str, Any],
    provider: Any,
    max_steps: int,
) -> dict[str, Any]:
    server = InProcessServer(state_root / "supervisor" / "native-coding-runs")
    session = server.create_session()
    run = server.create_run(session["session_id"], goal)
    workspace_id = _string(inputs.get("workspace_id"), "workspace_" + new_id("coding_task"))
    ticks: list[dict[str, Any]] = []

    for index in range(max_steps):
        tick = server.run_agent_loop_provider_planner_tick(
            run["run_id"],
            provider=provider,
            agent_id="agent_native_coding",
            tick_id=f"tick_native_coding_{index + 1}",
            decision_id=f"decision_native_coding_{index + 1}",
            tick_budget={"max_ticks": max_steps, "ticks_used": index, "budget_basis": "coding_task.run"},
            default_context_extra={
                "coding_task": {
                    "goal": goal,
                    "workspace_label": "current_project",
                    "allowed_capabilities": ["code.search", "code.read", "coding_task.execute"],
                    "verification_intent": _string(inputs.get("verification_intent"), ""),
                }
            },
            capability_system_inputs={
                "root": str(state_root),
                "cwd": str(cwd),
                "workspace_id": workspace_id,
            },
            max_tokens=512,
        )
        ticks.append(tick)
        if _coding_status([tick]) == "verified":
            break
        after_policy = tick.get("after_policy")
        if isinstance(after_policy, Mapping) and after_policy.get("should_continue") is not True:
            break

    return {
        "kind": "native_coding_agent_loop",
        "status": _coding_status(ticks),
        "workspace_id": workspace_id,
        "tick_count": len(ticks),
        "context_call_count": _capability_call_count(ticks, {"code.search", "code.read"}),
        "source_workspace_write": "not_performed",
        "ticks": ticks,
    }
```

Add the helper functions in the same file:

```python
def _coding_status(ticks: list[dict[str, Any]]) -> str:
    for tick in reversed(ticks):
        execution = _coding_execution(tick)
        if isinstance(execution, Mapping):
            status = execution.get("status")
            if isinstance(status, str):
                return status
    return "blocked"


def _coding_execution(tick: Mapping[str, Any]) -> Mapping[str, Any] | None:
    capability_run = _capability_run(tick)
    if not isinstance(capability_run, Mapping):
        return None
    execution = capability_run.get("coding_execution")
    return execution if isinstance(execution, Mapping) else None


def _capability_call_count(ticks: list[dict[str, Any]], capability_ids: set[str]) -> int:
    return sum(
        1
        for tick in ticks
        if isinstance(_capability_run(tick), Mapping)
        and _capability_run(tick).get("capability_id") in capability_ids
    )


def _capability_run(tick: Mapping[str, Any]) -> Mapping[str, Any] | None:
    contract = tick.get("planner_contract_result")
    if not isinstance(contract, Mapping):
        return None
    planner = contract.get("planner_result")
    if not isinstance(planner, Mapping):
        return None
    step_result = planner.get("step_result")
    if not isinstance(step_result, Mapping):
        return None
    action_result = step_result.get("action_result")
    if not isinstance(action_result, Mapping):
        return None
    capability_run = action_result.get("capability_run")
    return capability_run if isinstance(capability_run, Mapping) else None


def _string(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default
```

- [ ] **Step 4: Route conversation decisions through the adapter**

In `src/isotope/features/supervisor/conversation_loop.py`, import:

```python
from isotope.features.supervisor.native_coding_run import (
    CODING_TASK_RUN_CAPABILITY,
    run_native_coding_agent_loop,
)
```

Pass `provider` into the helper that executes capability decisions. Before the generic `_execute_capacity_step_with_timeout(...)` path:

```python
if capacity_id == CODING_TASK_RUN_CAPABILITY:
    result = run_native_coding_agent_loop(
        state_root=state_root,
        cwd=Path(context["system_context"]["cwd"]),
        goal=_require_text(inputs.get("goal"), "goal"),
        inputs=inputs,
        provider=provider,
        max_steps=_bounded_coding_steps(inputs.get("max_steps")),
    )
else:
    result = _execute_capacity_step_with_timeout(...)
```

Add:

```python
def _bounded_coding_steps(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 6
    return min(max(value, 1), 12)
```

- [ ] **Step 5: Run the Supervisor test**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_runs_coding_task_run_through_existing_agent_loop -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 6**

```bash
git add src/isotope/features/supervisor/native_coding_run.py src/isotope/features/supervisor/conversation_loop.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py
git commit -m "feat(supervisor): run native coding through agent loop"
```

## Task 7: Summarize Results And Support Bounded Revision

**Files:**
- Modify: `src/isotope/features/supervisor/native_coding_run.py`
- Modify: `src/isotope/features/supervisor/commands/capacity_summary.py`
- Test: `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`
- Test: `tests/unit/features/supervisor/test_capacity_module_boundaries.py`

- [ ] **Step 1: Write the failing summary assertions**

In `test_conversation_loop_runs_coding_task_run_through_existing_agent_loop`, add:

```python
summary = events[1].payload["result_summary"]
assert summary["agent_loop_coding_workspace_id"].startswith("workspace_")
assert summary["agent_loop_coding_source_workspace_write"] == "not_performed"
```

- [ ] **Step 2: Run the summary test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_runs_coding_task_run_through_existing_agent_loop -q
```

Expected: fail if summary fields are absent.

- [ ] **Step 3: Add low-sensitive summary fields**

In `src/isotope/features/supervisor/commands/capacity_summary.py`, add:

```python
def _agent_loop_native_coding_summary(agent_loop: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "agent_loop_coding_status": agent_loop.get("status"),
        "agent_loop_coding_workspace_id": agent_loop.get("workspace_id"),
        "agent_loop_coding_tick_count": agent_loop.get("tick_count"),
        "agent_loop_coding_context_calls": agent_loop.get("context_call_count"),
        "agent_loop_coding_source_workspace_write": agent_loop.get("source_workspace_write"),
    }
```

Then call it from `agent_loop_json_summary(...)` when `agent_loop.get("kind") == "native_coding_agent_loop"`.

- [ ] **Step 4: Write the failing bounded-revision test**

Append to `tests/unit/features/supervisor/test_supervisor_conversation_loop.py`:

```python
def test_coding_task_run_allows_bounded_revision_after_failed_verification(tmp_path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    provider = provider_for_native_coding_sequence(
        [
            ("coding_task.execute", {"goal": "Wrong attempt.", "patch": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 3\n", "argv": ["python3", "-c", "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'"], "allowed_commands": ["python3"], "include_paths": ["src"]}),
            ("coding_task.execute", {"goal": "Correct attempt.", "patch": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n", "argv": ["python3", "-c", "from pathlib import Path; assert Path('src/app.py').read_text() == 'value = 2\\n'"], "allowed_commands": ["python3"], "include_paths": ["src"]}),
        ],
        first_conversation_decision={"capacity_id": "coding_task.run", "arguments": {"goal": "Change value to 2.", "max_steps": 4}},
    )

    events = list(
        run_supervisor_conversation_events(
            state_root=tmp_path / "state",
            cwd=workspace,
            user_message="把 value 改成 2。",
            provider=provider,
            max_turns=4,
        )
    )

    summary = events[1].payload["result_summary"]
    assert summary["agent_loop_coding_status"] == "verified"
    assert summary["agent_loop_coding_tick_count"] == 2
```

Add `provider_for_native_coding_sequence(...)` as a local test helper if the existing `RecordingConversationProvider` cannot rewrite planner basis fields dynamically.

- [ ] **Step 5: Run revision test and verify it fails**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_coding_task_run_allows_bounded_revision_after_failed_verification -q
```

Expected: fail if the adapter stops after `needs_revision`.

- [ ] **Step 6: Continue after failed verification until verified or budget exhausted**

In `src/isotope/features/supervisor/native_coding_run.py`, keep the loop running unless `_coding_status([tick]) == "verified"` or tick policy stops. Do not stop on `needs_revision`.

- [ ] **Step 7: Run Supervisor and boundary tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_conversation_loop_runs_coding_task_run_through_existing_agent_loop \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py::test_coding_task_run_allows_bounded_revision_after_failed_verification \
  tests/unit/features/supervisor/test_capacity_module_boundaries.py \
  -q
```

Expected: pass.

- [ ] **Step 8: Commit Task 7**

```bash
git add src/isotope/features/supervisor/native_coding_run.py src/isotope/features/supervisor/commands/capacity_summary.py tests/unit/features/supervisor/test_supervisor_conversation_loop.py tests/unit/features/supervisor/test_capacity_module_boundaries.py
git commit -m "feat(supervisor): summarize native coding runs"
```

## Task 8: Final Verification

**Files:**
- Modify only if behavior docs are required by maintainers: `docs/current/supervisor-command-reference.md`

- [ ] **Step 1: Run contract and capability tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/interfaces/http/test_input_contract_schema.py \
  tests/unit/capabilities/test_capability_runner_thin_shell.py \
  -q
```

Expected: pass.

- [ ] **Step 2: Run agent-loop tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/agents/loop/test_agent_loop_step_driver.py \
  tests/unit/agents/loop/test_agent_loop_provider_planner.py \
  -q
```

Expected: pass.

- [ ] **Step 3: Run Supervisor tests**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/features/supervisor/test_supervisor_conversation_loop.py \
  tests/unit/features/supervisor/test_capacity_module_boundaries.py \
  -q
```

Expected: pass.

- [ ] **Step 4: Inspect for raw detail leaks**

Run:

```bash
rg -n '"patch"|"argv"|raw_response|raw_content|transcript' src/isotope/features/supervisor tests/unit/features/supervisor/test_supervisor_conversation_loop.py
```

Expected: only filtering code and explicit absence assertions mention these strings in streamed capacity payload tests.

- [ ] **Step 5: Commit docs only if user-facing docs changed**

If behavior docs are changed:

```bash
git add docs/current/supervisor-command-reference.md
git commit -m "docs(supervisor): document native coding run"
```

If no behavior docs are changed, say in the final implementation summary: the design spec plus this plan are the current implementation docs for this maturity slice.

## Self-Review Checklist

- Spec coverage:
  - Existing agent loop reuse: Tasks 4, 5, 6.
  - `coding_task.run` product entrypoint: Task 3.
  - `cwd/root` hidden from user/model forms: Tasks 1 and 2.
  - System injection instead of model-authored routing: Task 4.
  - Model environment understanding via `code.search` and `code.read`: Tasks 5 and 6.
  - Isolated execution and source non-mutation: Task 6.
  - Bounded revision after failed verification: Task 7.
  - Low-sensitive result summaries: Task 7.
- Placeholder scan: no task relies on unspecified implementation text.
- Type consistency:
  - Capability id is always `coding_task.run`.
  - System-only marker is always `x-system-input`.
  - Private execution key is `_private_system_inputs` until `planner_adapter` converts it to `_system_inputs`.
  - Public summary keys use `agent_loop_coding_*`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-native-coding-product-maturity.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Choose the execution approach before implementation starts.
