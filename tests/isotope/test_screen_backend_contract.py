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
