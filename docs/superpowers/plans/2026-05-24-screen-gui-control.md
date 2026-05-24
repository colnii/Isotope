# Screen GUI Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Isotope screen observe/control slice with a cross-platform contract, Windows first backend, policy-gated execution, artifact evidence, and non-unique GUI smoke coverage.

**Architecture:** Add `screen_observe` and `screen_control` as ordinary Isotope tools in the existing `ActionTypeRegistry -> PolicyEngine -> Executor -> ArtifactStore -> event log` chain. Use a `ScreenBackendAdapter` matching the existing terminal backend adapter pattern: Isotope owns grants, artifact policy, event/read-model safety, and backend protocol validation; platform backend code only performs target observation or input execution under the exact request.

**Tech Stack:** Python 3.13, pytest, existing Isotope runtime/schema/event/artifact modules, Windows PowerShell/.NET interop for the first real backend, no new package dependency in the first slice.

---

## File Structure

- Create `src/isotope/execution/screen_backend_types.py`
  - Dataclasses and validation helpers for screen backend config, target selectors, actions, requests, output artifacts, and results.
- Create `src/isotope/execution/screen_backend_policy.py`
  - Request construction and artifact/action policy validation.
- Create `src/isotope/execution/screen_backend_adapter.py`
  - Adapter enforcing grants, backend protocol, artifact creation, and low-sensitive summaries.
- Create `src/isotope/execution/screen_windows_backend.py`
  - Windows first backend using system facilities through `powershell.exe`.
- Create `src/isotope/features/screen/__init__.py`
  - Feature package marker.
- Create `src/isotope/features/screen/runner.py`
  - Manual smoke runner for screen observe/control, not part of default CI.
- Modify `src/isotope/platform/registry/actions.py`
  - Register `screen_observe` and `screen_control`, validate screen required capabilities, and expose model-facing constraints.
- Modify `src/isotope/policy/__init__.py`
  - Grant screen observe/control only under allowlist and approval rules.
- Modify `src/isotope/runtime/action_compiler.py`
  - Compile screen intents and cap requested capabilities.
- Modify `src/isotope/execution/executor.py`
  - Route screen tools through `ScreenBackendAdapter`.
- Modify `src/isotope/runtime/in_process.py`
  - Accept optional `screen_backend` and `screen_backend_config`.
- Modify `src/isotope/runtime/in_process_actions.py`
  - Add low-sensitive requested action summaries for screen tools.
- Modify `pyproject.toml`
  - Add `isotope-screen` CLI entry.
- Create tests:
  - `tests/isotope/test_screen_backend_contract.py`
  - `tests/isotope/test_screen_registry_policy.py`
  - `tests/isotope/test_screen_backend_executor_integration.py`
  - `tests/isotope/test_screen_smoke_runner.py`

## Shared Contract Decisions

- `screen_observe` can produce `screen_screenshot`, `screen_metadata`, or `screen_diagnostic` artifacts.
- `screen_control` can produce `screen_control_plan`, `screen_control_result`, or `screen_diagnostic` artifacts.
- Artifact content may contain screenshots or target details; events/read models must expose only summaries and refs.
- First slice supports `manual`, `assist`, and `auto` control modes in grants, but runtime execution only proceeds when policy grants match the submitted action.
- `screen_control` with `execution_mode="execute"` requires either user approval or an allowlisted action set.
- `screen_control` with `execution_mode="dry_run"` can produce a plan artifact without moving input devices if policy grants it.
- Smoke matrix is manual and non-unique: pass/fail must be reported per sample; one sample never proves generic coverage.

---

### Task 1: Screen Backend Contract Types and Policy

**Files:**
- Create: `src/isotope/execution/screen_backend_types.py`
- Create: `src/isotope/execution/screen_backend_policy.py`
- Test: `tests/isotope/test_screen_backend_contract.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/isotope/test_screen_backend_contract.py`:

```python
from __future__ import annotations

import pytest

from isotope.execution import screen_backend_policy as screen_policy
from isotope.execution import screen_backend_types as screen_types
from isotope.platform.schemas.actions import ActionProposal, PolicyDecision


def _observe_proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_screen_observe",
        run_id="run_screen",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": "screen_observe",
            "target_selector": {
                "kind": "window",
                "selector": {"app": "notepad.exe"},
            },
            "mode": "non_intrusive",
            "capture": ["metadata", "screenshot"],
            "summary": "observe screen target",
        },
        requested_capabilities={
            "tools": ["screen_observe"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
        },
    )


def _control_proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="prop_screen_control",
        run_id="run_screen",
        agent_id="agent_supervisor",
        thread_id="thread_main",
        action_type="call_tool",
        payload={
            "tool": "screen_control",
            "target_selector": {
                "kind": "window",
                "selector": {"title_contains": "sample"},
            },
            "mode": "interactive",
            "execution_mode": "dry_run",
            "actions": [
                {"type": "move", "x": 10, "y": 20},
                {"type": "click", "button": "left", "x": 10, "y": 20},
            ],
            "summary": "dry run screen control",
        },
        requested_capabilities={
            "tools": ["screen_control"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
        },
    )


def _decision(proposal: ActionProposal, *, outcome: str = "approved") -> PolicyDecision:
    return PolicyDecision(
        decision_id="dec_screen",
        proposal_id=proposal.proposal_id,
        outcome=outcome,
        grants={
            "tools": [proposal.payload["tool"]],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 5},
            "screen": {
                "observe": True,
                "control": proposal.payload["tool"] == "screen_control",
                "target_selector_policy": {
                    "allowed_apps": ["notepad.exe"],
                    "allowed_title_contains": ["sample"],
                },
                "action_policy": {
                    "execution_modes": ["dry_run"],
                    "allowed_action_types": ["move", "click"],
                    "allowed_buttons": ["left"],
                    "max_actions": 8,
                },
                "artifact_policy": {
                    "capture": [
                        "screenshot",
                        "metadata",
                        "control_plan",
                        "control_result",
                        "diagnostic",
                    ],
                    "max_screenshot_bytes": 500000,
                    "max_screenshot_width": 1600,
                    "max_screenshot_height": 1200,
                    "full_content_in_events": False,
                    "full_content_in_read_model": False,
                },
            },
        },
        reason_codes=[],
    )


def _workspace_binding() -> dict:
    return {"workspace_id": "workspace_shared_ro", "mode": "shared_ro"}


def test_target_selector_requires_at_least_one_selector_field():
    with pytest.raises(ValueError, match="selector must include"):
        screen_types.ScreenTargetSelector(kind="window", selector={})


def test_screen_action_rejects_unknown_action_type():
    with pytest.raises(ValueError, match="screen action type is not supported"):
        screen_types.ScreenAction(type="double_backflip")


def test_build_observe_request_copies_exact_grants():
    proposal = _observe_proposal()
    decision = _decision(proposal)

    request = screen_policy.build_screen_backend_request(
        proposal=proposal,
        decision=decision,
        execution_id="exec_screen",
        workspace_binding=_workspace_binding(),
        basis_event_ids=["evt_proposed", "evt_decided"],
    )

    assert request.tool_name == "screen_observe"
    assert request.operation == "observe"
    assert request.grants == decision.grants
    assert request.grants is not decision.grants
    assert request.target_selector.selector == {"app": "notepad.exe"}
    assert request.capture == ["metadata", "screenshot"]

    decision.grants["screen"]["target_selector_policy"]["allowed_apps"].append("calc.exe")
    assert request.grants["screen"]["target_selector_policy"]["allowed_apps"] == ["notepad.exe"]


def test_build_control_request_rejects_pending_approval():
    proposal = _control_proposal()

    with pytest.raises(PermissionError, match="pending approval"):
        screen_policy.build_screen_backend_request(
            proposal=proposal,
            decision=_decision(proposal),
            execution_id="exec_screen",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_approval_requested"],
            approval_status="pending",
        )


def test_control_request_enforces_allowed_execution_mode():
    proposal = _control_proposal()
    decision = _decision(proposal)
    decision.grants["screen"]["action_policy"]["execution_modes"] = ["execute"]

    with pytest.raises(screen_types.ScreenBackendProtocolError) as exc_info:
        screen_policy.build_screen_backend_request(
            proposal=proposal,
            decision=decision,
            execution_id="exec_screen",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )

    assert exc_info.value.error_reason_code == "screen_action_policy_denied"


def test_artifact_policy_rejects_full_content_in_events():
    proposal = _observe_proposal()
    decision = _decision(proposal)
    decision.grants["screen"]["artifact_policy"]["full_content_in_events"] = True

    with pytest.raises(screen_types.ScreenBackendProtocolError) as exc_info:
        screen_policy.build_screen_backend_request(
            proposal=proposal,
            decision=decision,
            execution_id="exec_screen",
            workspace_binding=_workspace_binding(),
            basis_event_ids=["evt_decided"],
        )

    assert exc_info.value.error_reason_code == "screen_artifact_policy_denied"
```

- [ ] **Step 2: Run the tests to verify RED**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_contract.py -q
```

Expected: collection fails with `ModuleNotFoundError` for `isotope.execution.screen_backend_policy` or `screen_backend_types`.

- [ ] **Step 3: Implement screen backend types**

Create `src/isotope/execution/screen_backend_types.py` with dataclasses matching the test names and these validation constants:

```python
SUPPORTED_SCREEN_PROTOCOL_VERSION = "screen-backend.v0.1"
SUPPORTED_BACKEND_MODES = {"external_local"}
ALLOWED_SCREEN_BACKEND_STATUSES = {
    "captured",
    "metadata_only",
    "planned",
    "completed",
    "failed",
    "not_observable",
    "ambiguous_target",
}
ALLOWED_CAPTURE_KINDS = {
    "screenshot",
    "metadata",
    "control_plan",
    "control_result",
    "diagnostic",
}
ALLOWED_SCREEN_ACTION_TYPES = {
    "move",
    "button_down",
    "button_up",
    "click",
    "wheel",
    "key_down",
    "key_up",
    "key_press",
}
```

Required public classes:

```python
class ScreenBackendProtocolError(RuntimeError): ...
class ScreenBackendExecutionError(RuntimeError): ...
class ScreenBackendNotConfiguredError(RuntimeError): ...
@dataclass(frozen=True)
class ScreenBackendConfig: ...
@dataclass(frozen=True)
class ScreenTargetSelector: ...
@dataclass(frozen=True)
class ScreenAction: ...
@dataclass(frozen=True)
class ScreenBackendRequest: ...
@dataclass(frozen=True)
class ScreenBackendOutputArtifact: ...
@dataclass
class ScreenBackendResult: ...
@dataclass(frozen=True)
class ScreenBackendRunResult: ...
```

Make `ScreenTargetSelector(kind="window", selector={})` raise `ValueError("screen target selector must include at least one selector field")`.

Make `ScreenAction(type="double_backflip")` raise `ValueError("screen action type is not supported")`.

- [ ] **Step 4: Implement request policy helpers**

Create `src/isotope/execution/screen_backend_policy.py` with:

```python
def build_screen_backend_request(
    *,
    proposal: ActionProposal,
    decision: PolicyDecision,
    execution_id: str,
    workspace_binding: dict[str, Any],
    basis_event_ids: list[str],
    approval_status: str = "approved",
    backend_config: ScreenBackendConfig | dict[str, Any] | None = None,
) -> ScreenBackendRequest:
    ...
```

Behavior required by tests:

- Reject `approval_status == "pending"` with `PermissionError("pending approval must not call backend")`.
- Reject denied decisions before backend calls.
- Deep-copy `decision.grants`.
- Resolve `operation` as `"observe"` for `screen_observe`, `"control"` for `screen_control`.
- Build `ScreenTargetSelector` from `proposal.payload["target_selector"]`.
- Build `ScreenAction` list from `proposal.payload["actions"]`.
- Validate `execution_mode` is allowed by `grants["screen"]["action_policy"]["execution_modes"]`.
- Validate capture kinds against `grants["screen"]["artifact_policy"]["capture"]`.
- Reject full content in events/read model.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_contract.py -q
```

Expected: all tests in `test_screen_backend_contract.py` pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/isotope/execution/screen_backend_types.py \
        src/isotope/execution/screen_backend_policy.py \
        tests/isotope/test_screen_backend_contract.py
git commit -m "feat(screen): add backend contract"
```

---

### Task 2: Registry, Policy, and Compiler Wiring

**Files:**
- Modify: `src/isotope/platform/registry/actions.py`
- Modify: `src/isotope/policy/__init__.py`
- Modify: `src/isotope/runtime/action_compiler.py`
- Test: `tests/isotope/test_screen_registry_policy.py`

- [ ] **Step 1: Write failing registry/policy/compiler tests**

Create `tests/isotope/test_screen_registry_policy.py`:

```python
from __future__ import annotations

import pytest

from isotope.platform.registry.actions import ActionTypeRegistry
from isotope.policy import PolicyEngine
from isotope.runtime.action_compiler import ActionCompiler


def _runtime_context(*, requires_approval: bool = False) -> dict[str, object]:
    return {
        "run_id": "run_screen",
        "agent_id": "agent_supervisor",
        "thread_id": "thread_main",
        "requires_approval": requires_approval,
    }


def _observe_intent() -> dict:
    return {
        "action": "call_tool",
        "tool": "screen_observe",
        "target_selector": {
            "kind": "window",
            "selector": {"app": "notepad.exe"},
        },
        "mode": "non_intrusive",
        "capture": ["metadata", "screenshot"],
        "summary": "observe target",
    }


def _control_intent(*, execution_mode: str = "execute") -> dict:
    return {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": {
            "kind": "window",
            "selector": {"app": "notepad.exe"},
        },
        "mode": "interactive",
        "execution_mode": execution_mode,
        "actions": [{"type": "click", "button": "left", "x": 5, "y": 6}],
        "summary": "control target",
    }


def test_default_registry_exposes_screen_tools_with_screen_capabilities():
    registry = ActionTypeRegistry.default()

    assert "screen_observe" in registry.tool_names()
    assert "screen_control" in registry.tool_names()
    observe = registry.get_tool("screen_observe")
    control = registry.get_tool("screen_control")
    assert observe.required_capabilities["screen"]["observe"] is True
    assert observe.required_capabilities["screen"]["control"] is False
    assert control.required_capabilities["screen"]["observe"] is True
    assert control.required_capabilities["screen"]["control"] is True
    assert control.required_capabilities["screen"]["action_policy"]["execution_modes"] == ["dry_run"]


def test_action_compiler_carries_screen_payload_without_raw_input_in_capabilities():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())

    proposal = compiler.compile(_control_intent(execution_mode="dry_run"), _runtime_context())

    assert proposal.payload["tool"] == "screen_control"
    assert proposal.payload["target_selector"]["selector"]["app"] == "notepad.exe"
    assert proposal.payload["actions"] == [{"type": "click", "button": "left", "x": 5, "y": 6}]
    assert proposal.payload["approval_requested"] is False
    assert proposal.requested_capabilities == {
        "tools": ["screen_control"],
        "workspace": {"mode": "shared_ro"},
        "budget": {"seconds": 5},
    }


def test_policy_grants_screen_observe_with_artifact_policy():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    proposal = compiler.compile(_observe_intent(), _runtime_context())

    decision = PolicyEngine(registry=ActionTypeRegistry.default()).decide(proposal)

    assert decision.outcome == "approved"
    assert decision.grants["tools"] == ["screen_observe"]
    assert decision.grants["screen"]["observe"] is True
    assert decision.grants["screen"]["control"] is False
    assert decision.grants["screen"]["artifact_policy"]["full_content_in_events"] is False


def test_policy_denies_execute_control_without_approval():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    proposal = compiler.compile(_control_intent(execution_mode="execute"), _runtime_context())

    decision = PolicyEngine(registry=ActionTypeRegistry.default()).decide(proposal)

    assert decision.outcome == "denied"
    assert decision.reason_codes == ["screen_approval_required"]


def test_policy_allows_execute_control_when_approval_requested():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    proposal = compiler.compile(
        _control_intent(execution_mode="execute"),
        _runtime_context(requires_approval=True),
    )

    decision = PolicyEngine(registry=ActionTypeRegistry.default()).decide(proposal)

    assert decision.outcome == "approved"
    assert decision.grants["tools"] == ["screen_control"]
    assert decision.grants["screen"]["control"] is True
    assert "execute" in decision.grants["screen"]["action_policy"]["execution_modes"]


def test_policy_denies_unknown_screen_action_type_before_executor():
    compiler = ActionCompiler(registry=ActionTypeRegistry.default())
    intent = _control_intent(execution_mode="dry_run")
    intent["actions"] = [{"type": "unknown"}]

    with pytest.raises(ValueError, match="screen action type"):
        compiler.compile(intent, _runtime_context())
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_registry_policy.py -q
```

Expected: tests fail because registry does not expose `screen_observe` / `screen_control`.

- [ ] **Step 3: Add default screen capabilities to registry**

Modify `src/isotope/platform/registry/actions.py`:

- Import no new third-party dependency.
- Add `_validate_screen_capabilities(capabilities: Any)`.
- Add `_screen_observe_tool_entry()`.
- Add `_screen_control_tool_entry()`.
- Include both entries in `ActionTypeRegistry.default()`.

Required default capability shape:

```python
{
    "tools": ["screen_control"],
    "workspace": {"mode": "shared_ro"},
    "budget": {"seconds": 5},
    "screen": {
        "observe": True,
        "control": True,
        "target_selector_policy": {
            "allowed_apps": [],
            "allowed_title_contains": [],
            "allow_any_target_with_approval": True,
        },
        "action_policy": {
            "execution_modes": ["dry_run"],
            "allowed_action_types": ["move", "click", "button_down", "button_up", "wheel", "key_down", "key_up", "key_press"],
            "allowed_buttons": ["left", "right", "middle"],
            "max_actions": 32,
            "requires_approval_for_execute": True,
        },
        "artifact_policy": {
            "capture": ["screenshot", "metadata", "control_plan", "control_result", "diagnostic"],
            "max_screenshot_bytes": 500000,
            "max_screenshot_width": 1600,
            "max_screenshot_height": 1200,
            "full_content_in_events": False,
            "full_content_in_read_model": False,
        },
    },
}
```

- [ ] **Step 4: Compile screen intents**

Modify `src/isotope/runtime/action_compiler.py`:

- Import `ScreenAction` and `ScreenTargetSelector`.
- For `screen_observe`, require `target_selector`, normalize `mode`, default `capture` to `["metadata", "screenshot"]`, and set `approval_requested`.
- For `screen_control`, require `target_selector`, `execution_mode`, and `actions`; validate each action with `ScreenAction`.
- Keep `requested_capabilities` limited to tools/workspace/budget.

- [ ] **Step 5: Add policy grants**

Modify `src/isotope/policy/__init__.py`:

- For `screen_observe`, grant observe and artifact policy when target selector is structurally valid.
- For `screen_control`, deny `execution_mode="execute"` unless `proposal.payload["approval_requested"] is True`.
- For `screen_control`, grant `execution_modes=["dry_run"]` without approval when registry allows dry run.
- Return reason code `screen_approval_required` for execute without approval.
- Return reason code `screen_action_not_allowed` for disallowed action types or max action overflow.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_registry_policy.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Run existing terminal tests to guard regressions**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_controlled_terminal_execution.py tests/isotope/test_executor_registry_integration.py -q
```

Expected: existing controlled terminal and registry tests remain green.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/isotope/platform/registry/actions.py \
        src/isotope/policy/__init__.py \
        src/isotope/runtime/action_compiler.py \
        tests/isotope/test_screen_registry_policy.py
git commit -m "feat(screen): add registry and policy gates"
```

---

### Task 3: Backend Adapter and Executor Integration

**Files:**
- Create: `src/isotope/execution/screen_backend_adapter.py`
- Modify: `src/isotope/execution/executor.py`
- Modify: `src/isotope/runtime/in_process.py`
- Modify: `src/isotope/runtime/in_process_actions.py`
- Test: `tests/isotope/test_screen_backend_executor_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/isotope/test_screen_backend_executor_integration.py`:

```python
from __future__ import annotations

import json

import pytest

import isotope.runtime.in_process as server


class FakeScreenBackend:
    def __init__(self, result: dict):
        self.result = result
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return self.result


def _backend_result(*, content: str = '{"window_count": 1}'):
    return {
        "backend_session_id": "screen_backend_001",
        "status": "captured",
        "started_at": "2026-05-24T00:00:00Z",
        "finished_at": "2026-05-24T00:00:01Z",
        "summary": "screen observe captured",
        "output_artifacts": [
            {
                "artifact_type": "screen_metadata",
                "summary": "screen metadata captured",
                "content": content,
            }
        ],
        "reason_code": "screen_observe_captured",
        "retryable": False,
        "resource_usage": {"duration_ms": 10},
    }


def _new_run(tmp_path, backend):
    api = server.InProcessServer(
        tmp_path,
        screen_backend=backend,
        screen_backend_config={
            "backend_id": "fake_screen",
            "backend_version": "0.1",
        },
    )
    session = api.create_session()
    run = api.create_run(session["session_id"], goal="screen backend integration")
    return api, run["run_id"]


def _observe_intent():
    return {
        "action": "call_tool",
        "tool": "screen_observe",
        "target_selector": {
            "kind": "window",
            "selector": {"app": "notepad.exe"},
        },
        "mode": "non_intrusive",
        "capture": ["metadata"],
        "summary": "observe screen",
    }


def _control_intent(*, execution_mode: str = "dry_run"):
    return {
        "action": "call_tool",
        "tool": "screen_control",
        "target_selector": {
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        "mode": "interactive",
        "execution_mode": execution_mode,
        "actions": [{"type": "click", "button": "left", "x": 1, "y": 2}],
        "summary": "control screen",
    }


def _event_types(api, run_id):
    return [event.event_type for event in api.get_events(run_id)]


def _approved_body():
    return {
        "resolution": "approved",
        "reason": "operator approved screen control",
        "resolver": "human_reviewer",
    }


def test_screen_observe_creates_artifact_without_leaking_content_to_events(tmp_path):
    secret = '{"window_title": "secret title"}'
    backend = FakeScreenBackend(_backend_result(content=secret))
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _observe_intent())

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    assert backend.calls[0].tool_name == "screen_observe"
    assert backend.calls[0].operation == "observe"
    assert _event_types(api, run_id) == [
        "run.created",
        "agent.created",
        "thread.created",
        "action.proposed",
        "action.decided",
        "action.started",
        "artifact.created",
        "action.completed",
        "run.completed",
    ]
    assert secret not in repr(api.get_events(run_id))
    assert api.artifact_store.get_content(result["artifact_ref"]) == secret


def test_screen_control_execute_requires_approval_before_backend_call(tmp_path):
    backend = FakeScreenBackend(_backend_result(content='{"clicked": true}'))
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _control_intent(execution_mode="execute"))

    assert result["status"] == "denied"
    assert result["decision"].reason_codes == ["screen_approval_required"]
    assert backend.calls == []
    assert api.artifact_store.list_artifacts(run_id) == []


def test_screen_control_execute_runs_after_approval(tmp_path):
    backend = FakeScreenBackend(
        {
            "backend_session_id": "screen_backend_001",
            "status": "completed",
            "started_at": "2026-05-24T00:00:00Z",
            "finished_at": "2026-05-24T00:00:01Z",
            "summary": "screen control completed",
            "output_artifacts": [
                {
                    "artifact_type": "screen_control_result",
                    "summary": "screen control completed",
                    "content": json.dumps({"action_count": 1}, sort_keys=True),
                }
            ],
            "reason_code": "screen_control_completed",
            "retryable": False,
            "resource_usage": {"duration_ms": 10},
        }
    )
    api, run_id = _new_run(tmp_path, backend)

    pending = api.submit_action(
        run_id,
        _control_intent(execution_mode="execute"),
        requires_approval=True,
    )
    assert pending["status"] == "pending_user_approval"
    assert backend.calls == []

    result = api.resolve_approval(pending["approval_id"], _approved_body())

    assert result["status"] == "completed"
    assert len(backend.calls) == 1
    assert backend.calls[0].operation == "control"
    assert backend.calls[0].actions[0].type == "click"


def test_backend_reported_widened_grants_are_rejected(tmp_path):
    raw_result = _backend_result()
    raw_result["reported_grants"] = {"tools": ["screen_observe", "screen_control"]}
    backend = FakeScreenBackend(raw_result)
    api, run_id = _new_run(tmp_path, backend)

    result = api.submit_action(run_id, _observe_intent())

    assert result["status"] == "failed"
    failed = next(event for event in api.get_events(run_id) if event.event_type == "action.failed")
    assert failed.payload["error_reason_code"] == "screen_backend_protocol_error"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_executor_integration.py -q
```

Expected: tests fail because `InProcessServer` does not accept `screen_backend`.

- [ ] **Step 3: Implement `ScreenBackendAdapter`**

Create `src/isotope/execution/screen_backend_adapter.py` following `TerminalBackendAdapter` structure:

- `prepare_and_run(...)` builds request with `build_screen_backend_request`.
- `_normalize_result(...)` accepts `ScreenBackendResult` or dict.
- `_accept_result(...)` rejects unknown status, widened grants, summary containing artifact full content, and unsupported artifact types.
- Creates artifacts from backend `output_artifacts`.
- Returns `ScreenBackendRunResult`.

The adapter must call `artifact_store.create_artifact(...)` with `artifact_type`, `summary`, `content`, `proposal_id`, and `decision_id`.

- [ ] **Step 4: Wire Executor**

Modify `src/isotope/execution/executor.py`:

- Import `ScreenBackendAdapter`, `ScreenBackendExecutionError`, `ScreenBackendNotConfiguredError`, `ScreenBackendProtocolError`.
- Add `screen_backend=None`, `screen_backend_config=None` constructor params.
- Build `self.screen_backend_adapter` when `screen_backend` is present.
- Route `tool_name in {"screen_observe", "screen_control"}` before generic handlers.
- If no backend configured, raise `ScreenBackendNotConfiguredError`.
- On backend status not completed/captured/metadata_only/planned, raise `ScreenBackendExecutionError`.
- Require at least one artifact ref from backend.
- Append completion metadata under `{"screen_backend": ...}`.

- [ ] **Step 5: Wire InProcessServer**

Modify `src/isotope/runtime/in_process.py`:

- Add `screen_backend=None`, `screen_backend_config=None` to `InProcessServer.__init__`.
- Pass both to `Executor(...)`.

- [ ] **Step 6: Add low-sensitive requested action summaries**

Modify `src/isotope/runtime/in_process_actions.py::_requested_action_summary`:

```python
if tool_name in {"screen_observe", "screen_control"}:
    summary["tool"] = tool_name
    target_selector = proposal.payload.get("target_selector")
    if isinstance(target_selector, dict):
        summary["target_kind"] = target_selector.get("kind")
        selector = target_selector.get("selector")
        if isinstance(selector, dict):
            summary["selector_keys"] = sorted(str(key) for key in selector.keys())
    if tool_name == "screen_control":
        actions = proposal.payload.get("actions")
        if isinstance(actions, list):
            summary["action_count"] = len(actions)
        summary["execution_mode"] = proposal.payload.get("execution_mode")
```

Do not include coordinates, screenshot content, OCR text, or raw target title.

- [ ] **Step 7: Verify GREEN and regression tests**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_executor_integration.py -q
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_contract.py tests/isotope/test_screen_registry_policy.py tests/isotope/test_controlled_terminal_execution.py -q
```

Expected: all listed tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/isotope/execution/screen_backend_adapter.py \
        src/isotope/execution/executor.py \
        src/isotope/runtime/in_process.py \
        src/isotope/runtime/in_process_actions.py \
        tests/isotope/test_screen_backend_executor_integration.py
git commit -m "feat(screen): route backend through executor"
```

---

### Task 4: Windows Backend

**Files:**
- Create: `src/isotope/execution/screen_windows_backend.py`
- Test: extend `tests/isotope/test_screen_backend_contract.py`

- [ ] **Step 1: Add backend construction tests**

Append to `tests/isotope/test_screen_backend_contract.py`:

```python
def test_windows_backend_reports_not_configured_off_windows(monkeypatch):
    from isotope.execution.screen_windows_backend import WindowsScreenBackend

    monkeypatch.setattr("sys.platform", "linux")
    backend = WindowsScreenBackend()

    result = backend.run(
        screen_types.ScreenBackendRequest(
            run_id="run_screen",
            proposal_id="prop_screen",
            decision_id="dec_screen",
            execution_id="exec_screen",
            tool_name="screen_observe",
            operation="observe",
            policy_profile_id="default",
            policy_version="v0.2",
            registry_id="default",
            registry_version="v0.2",
            grants={"tools": ["screen_observe"], "screen": {"observe": True}},
            workspace_binding={"workspace_id": "workspace_shared_ro", "mode": "shared_ro"},
            target_selector=screen_types.ScreenTargetSelector(
                kind="window",
                selector={"app": "notepad.exe"},
            ),
            mode="non_intrusive",
            capture=["metadata"],
            execution_mode=None,
            actions=[],
            budget={"seconds": 5},
            artifact_policy={
                "capture": ["metadata", "diagnostic"],
                "full_content_in_events": False,
                "full_content_in_read_model": False,
            },
            basis_event_ids=["evt_decided"],
            backend_config={"backend_id": "windows_screen", "backend_version": "0.1"},
        )
    )

    assert result.status == "failed"
    assert result.reason_code == "screen_windows_backend_unavailable"
    assert result.retryable is False
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_contract.py::test_windows_backend_reports_not_configured_off_windows -q
```

Expected: import fails because `screen_windows_backend.py` does not exist.

- [ ] **Step 3: Implement `WindowsScreenBackend`**

Create `src/isotope/execution/screen_windows_backend.py`.

Implementation requirements:

- Return structured `ScreenBackendResult`.
- On non-Windows Python platform without `powershell.exe`, return failed result with `reason_code="screen_windows_backend_unavailable"`.
- For observe, call a PowerShell script that enumerates windows by title/process and writes JSON metadata.
- For screenshot, write PNG bytes to a temporary file, then base64 encode or read bytes as Latin-1-safe artifact content only after applying size limits. Prefer saving screenshot artifact content as base64 JSON:

```json
{
  "encoding": "base64",
  "media_type": "image/png",
  "scaled": false,
  "width": 800,
  "height": 600,
  "data": "..."
}
```

- For control, execute only when request `operation == "control"` and `execution_mode == "execute"`.
- Use PowerShell/.NET P/Invoke or WScript only inside the backend implementation.
- Keep all raw PowerShell output inside `screen_diagnostic` artifact on failure, not in event metadata.

First implementation can support:

- observe metadata
- observe foreground or target window screenshot when capturable
- control click/key/wheel through a small event sequence

- [ ] **Step 4: Verify unit behavior**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_backend_contract.py -q
```

Expected: all screen backend contract tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/isotope/execution/screen_windows_backend.py tests/isotope/test_screen_backend_contract.py
git commit -m "feat(screen): add windows backend shell"
```

---

### Task 5: Manual Smoke Runner

**Files:**
- Create: `src/isotope/features/screen/__init__.py`
- Create: `src/isotope/features/screen/runner.py`
- Modify: `pyproject.toml`
- Test: `tests/isotope/test_screen_smoke_runner.py`

- [ ] **Step 1: Write CLI tests**

Create `tests/isotope/test_screen_smoke_runner.py`:

```python
from __future__ import annotations

import json

from isotope.features.screen import runner


def test_parse_target_selector_from_cli_args():
    selector = runner._target_selector_from_args(
        app="notepad.exe",
        title_contains=None,
        window_id=None,
    )

    assert selector == {
        "kind": "window",
        "selector": {"app": "notepad.exe"},
    }


def test_smoke_matrix_output_requires_non_unique_samples():
    matrix = runner._default_smoke_matrix()

    assert len(matrix) >= 3
    assert len({entry["category"] for entry in matrix}) >= 3


def test_build_observe_intent_is_screen_observe():
    intent = runner._build_observe_intent(
        target_selector={
            "kind": "window",
            "selector": {"title_contains": "sample"},
        },
        capture=["metadata"],
    )

    assert intent["action"] == "call_tool"
    assert intent["tool"] == "screen_observe"
    assert intent["capture"] == ["metadata"]


def test_json_print_writes_serializable_payload(capsys):
    runner._print_json({"status": "ok"})

    out = capsys.readouterr().out
    assert json.loads(out) == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_smoke_runner.py -q
```

Expected: import fails because `isotope.features.screen` does not exist.

- [ ] **Step 3: Implement runner**

Create `src/isotope/features/screen/__init__.py` as an empty package marker.

Create `src/isotope/features/screen/runner.py` with:

- `observe` command.
- `control` command supporting `--dry-run` and `--approve-execute`.
- `smoke-matrix` command that prints required manual sample categories.
- Helper `_target_selector_from_args(app, title_contains, window_id)`.
- Helper `_default_smoke_matrix()`.
- Helper `_build_observe_intent(...)`.
- Helper `_print_json(...)`.

Manual command examples:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m isotope.features.screen.runner smoke-matrix --json
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m isotope.features.screen.runner observe --app notepad.exe --capture metadata --json
```

- [ ] **Step 4: Add project script**

Modify `pyproject.toml`:

```toml
isotope-screen = "isotope.features.screen.runner:main"
```

- [ ] **Step 5: Verify GREEN**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope/test_screen_smoke_runner.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/isotope/features/screen/__init__.py \
        src/isotope/features/screen/runner.py \
        pyproject.toml \
        tests/isotope/test_screen_smoke_runner.py
git commit -m "feat(screen): add manual smoke runner"
```

---

### Task 6: Documentation Sync and Focused Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-05-24-screen-gui-control-design.md`
- Modify if present and relevant: `docs/current/status.md`

- [ ] **Step 1: Update spec decisions**

Update `docs/superpowers/specs/2026-05-24-screen-gui-control-design.md` section `10. Open Questions` to `10. Decisions for first slice` with these decisions:

- Windows screenshot backend uses built-in Windows/PowerShell/.NET paths first.
- Screenshot artifacts are PNG payloads with byte/dimension caps.
- OCR is outside first slice.
- macOS contract is reserved, Windows implementation ships first.
- First slice uses existing cancel/pause semantics; dedicated emergency stop is a subsequent hardening item.

- [ ] **Step 2: Run focused tests**

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest \
  tests/isotope/test_screen_backend_contract.py \
  tests/isotope/test_screen_registry_policy.py \
  tests/isotope/test_screen_backend_executor_integration.py \
  tests/isotope/test_screen_smoke_runner.py \
  tests/isotope/test_controlled_terminal_execution.py \
  tests/isotope/test_terminal_backend_adapter_contract.py \
  -q
```

Expected: all listed tests pass.

- [ ] **Step 3: Run diff hygiene**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors; branch shows only intended tracked modifications before commit.

- [ ] **Step 4: Commit Task 6**

```bash
git add docs/superpowers/specs/2026-05-24-screen-gui-control-design.md docs/current/status.md
git commit -m "docs: sync screen gui control decisions"
```

If `docs/current/status.md` has no relevant change, omit it from `git add`.

---

## Final Verification

Run:

```bash
/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/isotope -q
git diff --check
git status --short --branch
```

Expected:

- Full `tests/isotope` passes or any unrelated existing failure is documented with exact failing test names.
- `git diff --check` passes.
- Working tree is clean after commits.

Manual smoke commands:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m isotope.features.screen.runner smoke-matrix --json
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m isotope.features.screen.runner observe --app notepad.exe --capture metadata --json
```

Manual smoke result must report per sample category. Do not summarize one sample as generic GUI coverage.

## Self-Review

- Spec coverage: observe/control tools, cross-platform contract, Windows first backend, human priority, allow list, artifact/read-model boundary, non-unique smoke matrix, and Open Questions decisions are covered by Tasks 1-6.
- Placeholder scan: this plan contains no unresolved placeholder markers and no instruction to leave code unspecified.
- Type consistency: screen request/result names are `ScreenBackendRequest`, `ScreenBackendResult`, `ScreenBackendRunResult`; target selector and actions are `ScreenTargetSelector` and `ScreenAction`; tool names are `screen_observe` and `screen_control`.
