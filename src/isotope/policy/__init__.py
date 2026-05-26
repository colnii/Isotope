"""Policy engine boundary for the Isotope v0.1 slice."""

from __future__ import annotations

from ..capabilities.tools.terminal import validate_argv
from ..execution.screen.backend_types import ScreenAction, ScreenTargetSelector
from ..platform.ids import new_id
from ..platform.registry.actions import ActionTypeRegistry
from ..platform.schemas.actions import ActionProposal, PolicyDecision


class PolicyEngine:
    """Minimal policy boundary backed by action/tool metadata."""

    def __init__(
        self,
        registry: ActionTypeRegistry | None = None,
        *,
        policy_profile_id: str = "default",
        policy_version: str = "v0.2",
    ) -> None:
        self.registry = registry if registry is not None else ActionTypeRegistry.default()
        self.policy_profile_id = self._metadata_string("policy_profile_id", policy_profile_id)
        self.policy_version = self._metadata_string("policy_version", policy_version)

    def decide(self, proposal: ActionProposal) -> PolicyDecision:
        budget_seconds = self._validate_proposal(proposal)
        requested_tools = proposal.requested_capabilities.get("tools", [])
        requested_workspace = proposal.requested_capabilities.get("workspace", {})

        if not isinstance(proposal.action_type, str) or not proposal.action_type:
            return self._denied(proposal, "unsupported_action")
        tool_name = proposal.payload.get("tool")
        if not isinstance(tool_name, str) or not tool_name:
            return self._denied(proposal, "unsupported_tool")
        try:
            entry = self.registry.get_tool(tool_name)
        except KeyError:
            return self._denied(proposal, "unsupported_tool")
        if not entry.enabled:
            return self._denied(proposal, "disabled_tool")
        if entry.action_type != proposal.action_type:
            return self._denied(proposal, "unsupported_action")

        required_capabilities = entry.required_capabilities
        required_tools = required_capabilities.get("tools", [])
        if not isinstance(required_tools, list):
            raise ValueError("registry required_capabilities.tools must be a list")
        if tool_name not in required_tools:
            return self._denied(proposal, "tool_requirement_missing")
        if tool_name not in requested_tools:
            return self._denied(proposal, "tool_not_requested")

        required_budget = required_capabilities.get("budget", {})
        if not isinstance(required_budget, dict):
            raise ValueError("registry required_capabilities.budget must be a dict")
        try:
            budget_cap = int(required_budget.get("seconds", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("registry budget.seconds must be int-like") from exc
        if budget_cap < 0:
            raise ValueError("registry budget.seconds must be non-negative")

        grants = {
            "tools": [tool_name],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": min(budget_seconds, budget_cap)},
        }
        if tool_name == "terminal_exec":
            terminal_capabilities = required_capabilities.get("terminal")
            if not isinstance(terminal_capabilities, dict):
                raise ValueError("registry required_capabilities.terminal must be a dict")
            allowed_commands = terminal_capabilities.get("allowed_commands", [])
            if not isinstance(allowed_commands, list) or not all(
                isinstance(item, str) for item in allowed_commands
            ):
                raise ValueError("registry terminal.allowed_commands must be a list of strings")
            approval_required_commands = terminal_capabilities.get("approval_required_commands", [])
            if not isinstance(approval_required_commands, list) or not all(
                isinstance(item, str) for item in approval_required_commands
            ):
                raise ValueError("registry terminal.approval_required_commands must be a list of strings")
            argv = validate_argv(proposal.payload.get("argv"))
            command = argv[0]
            allowed_command_set = set(allowed_commands)
            approval_required_command_set = set(approval_required_commands)
            if command in approval_required_command_set and proposal.payload.get("approval_requested") is not True:
                return self._denied(proposal, "terminal_approval_required")
            if command not in allowed_command_set and command not in approval_required_command_set:
                return self._denied(proposal, "terminal_command_not_allowed")
            granted_commands = list(allowed_commands)
            if command in approval_required_command_set and command not in granted_commands:
                granted_commands.append(command)
            try:
                max_output_bytes = int(terminal_capabilities.get("max_output_bytes", 4096))
            except (TypeError, ValueError) as exc:
                raise ValueError("registry terminal.max_output_bytes must be int-like") from exc
            if max_output_bytes <= 0:
                raise ValueError("registry terminal.max_output_bytes must be positive")
            if terminal_capabilities.get("shell", False) is not False:
                raise ValueError("registry terminal.shell must be false")
            if terminal_capabilities.get("argv_policy", "allowlist") != "allowlist":
                raise ValueError("registry terminal.argv_policy must be allowlist")
            grants["terminal"] = {
                "shell": False,
                "argv_policy": "allowlist",
                "allowed_commands": granted_commands,
                "max_output_bytes": max_output_bytes,
            }
        if tool_name == "codex_task":
            codex_capabilities = required_capabilities.get("codex_task")
            if not isinstance(codex_capabilities, dict):
                raise ValueError("registry required_capabilities.codex_task must be a dict")
            prompt = proposal.payload.get("prompt")
            if not isinstance(prompt, str) or not prompt:
                return self._denied(proposal, "codex_task_prompt_required")
            if proposal.payload.get("approval_requested") is not True:
                return self._denied(proposal, "codex_task_approval_required")
            grants["codex_task"] = {
                "adapter_required": codex_capabilities.get("adapter_required", True) is True,
            }
        if tool_name == "write_memory":
            if proposal.payload.get("approval_requested") is not True:
                return self._denied(proposal, "memory_approval_required")
        if tool_name in {"screen_observe", "screen_control"}:
            screen_capabilities = required_capabilities.get("screen")
            if not isinstance(screen_capabilities, dict):
                raise ValueError("registry required_capabilities.screen must be a dict")
            screen_grant = _screen_grant_from_capabilities(screen_capabilities)
            _apply_target_allowlist(
                screen_grant,
                proposal.payload.get("target_allowlist"),
            )
            target_selector = _screen_target_selector_from_payload(
                proposal.payload.get("target_selector")
            )
            target_denial = _target_policy_denial(
                target_selector,
                screen_grant.get("target_selector_policy", {}),
            )
            if target_denial is not None:
                return self._denied(proposal, target_denial)
            if tool_name == "screen_observe":
                if screen_grant.get("observe") is not True:
                    return self._denied(proposal, "screen_observe_not_allowed")
                grants["screen"] = screen_grant
            else:
                if screen_grant.get("control") is not True:
                    return self._denied(proposal, "screen_control_not_allowed")
                execution_mode = proposal.payload.get("execution_mode")
                if not isinstance(execution_mode, str):
                    return self._denied(proposal, "screen_execution_mode_required")
                actions = _screen_actions_from_payload(proposal.payload.get("actions"))
                action_denial = _action_policy_denial(
                    execution_mode=execution_mode,
                    actions=actions,
                    action_policy=screen_grant.get("action_policy", {}),
                )
                if action_denial is not None:
                    return self._denied(proposal, action_denial)
                if execution_mode == "execute":
                    if proposal.payload.get("approval_requested") is not True:
                        return self._denied(proposal, "screen_approval_required")
                    screen_grant["action_policy"]["execution_modes"] = _with_unique(
                        screen_grant["action_policy"]["execution_modes"],
                        "execute",
                    )
                grants["screen"] = screen_grant
        requested_matches = (
            requested_tools == grants["tools"]
            and requested_workspace.get("mode", "shared_ro") == "shared_ro"
            and budget_seconds <= budget_cap
        )
        return self._validated_decision(PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="approved" if requested_matches else "modified",
            grants=grants,
            reason_codes=[] if requested_matches else ["capabilities_reduced"],
            policy_profile_id=self.policy_profile_id,
            policy_version=self.policy_version,
        ))

    def _denied(self, proposal: ActionProposal, reason_code: str) -> PolicyDecision:
        return self._validated_decision(PolicyDecision(
            decision_id=new_id("dec"),
            proposal_id=proposal.proposal_id,
            outcome="denied",
            grants={"tools": [], "workspace": {"mode": "none"}, "budget": {"seconds": 0}},
            reason_codes=[reason_code],
            policy_profile_id=self.policy_profile_id,
            policy_version=self.policy_version,
        ))

    def _validate_proposal(self, proposal: ActionProposal) -> int:
        if not isinstance(proposal, ActionProposal):
            raise TypeError("PolicyEngine.decide requires an ActionProposal")
        if not isinstance(proposal.payload, dict):
            raise TypeError("proposal payload must be a dict")
        if not isinstance(proposal.requested_capabilities, dict):
            raise TypeError("requested_capabilities must be a dict")
        requested_tools = proposal.requested_capabilities.get("tools", [])
        if not isinstance(requested_tools, list):
            raise TypeError("requested tools must be a list")
        requested_workspace = proposal.requested_capabilities.get("workspace", {})
        if not isinstance(requested_workspace, dict):
            raise TypeError("requested workspace must be a dict")
        requested_budget = proposal.requested_capabilities.get("budget", {})
        if not isinstance(requested_budget, dict):
            raise TypeError("requested budget must be a dict")
        try:
            budget_seconds = int(requested_budget.get("seconds", 30))
        except (TypeError, ValueError) as exc:
            raise ValueError("budget.seconds must be int-like") from exc
        if budget_seconds < 0:
            raise ValueError("budget.seconds must be non-negative")
        return budget_seconds

    def _validated_decision(self, decision: PolicyDecision) -> PolicyDecision:
        if decision.outcome not in {"approved", "modified", "denied"}:
            raise ValueError("unknown policy decision outcome")
        if decision.outcome == "denied":
            if decision.grants.get("tools"):
                raise ValueError("denied decision cannot grant tools")
            if decision.grants.get("workspace", {}).get("mode") not in {None, "none"}:
                raise ValueError("denied decision cannot grant workspace")
            if int(decision.grants.get("budget", {}).get("seconds", 0)) > 0:
                raise ValueError("denied decision cannot grant positive budget")
            return decision

        if not isinstance(decision.grants.get("tools"), list):
            raise ValueError("approved or modified decision requires tools grant")
        if not decision.grants.get("workspace", {}).get("mode"):
            raise ValueError("approved or modified decision requires workspace.mode grant")
        if "seconds" not in decision.grants.get("budget", {}):
            raise ValueError("approved or modified decision requires budget.seconds grant")
        return decision

    def _metadata_string(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")
        return value


def _screen_grant_from_capabilities(capabilities: dict) -> dict:
    target_policy = capabilities.get("target_selector_policy", {})
    action_policy = capabilities.get("action_policy", {})
    artifact_policy = capabilities.get("artifact_policy", {})
    if not isinstance(target_policy, dict):
        raise ValueError("registry screen.target_selector_policy must be a dict")
    if not isinstance(action_policy, dict):
        raise ValueError("registry screen.action_policy must be a dict")
    if not isinstance(artifact_policy, dict):
        raise ValueError("registry screen.artifact_policy must be a dict")
    return {
        "observe": capabilities.get("observe") is True,
        "control": capabilities.get("control") is True,
        "target_selector_policy": {
            "allowed_apps": list(target_policy.get("allowed_apps", [])),
            "allowed_title_contains": list(target_policy.get("allowed_title_contains", [])),
            "allow_first_match_execute": target_policy.get("allow_first_match_execute") is True,
        },
        "action_policy": {
            "modes": list(action_policy.get("modes", [])),
            "execution_modes": list(action_policy.get("execution_modes", [])),
            "allowed_action_types": list(action_policy.get("allowed_action_types", [])),
            "allowed_buttons": list(action_policy.get("allowed_buttons", [])),
            "max_actions": action_policy.get("max_actions", 0),
        },
        "artifact_policy": {
            "capture": list(artifact_policy.get("capture", [])),
            "max_screenshot_bytes": artifact_policy.get("max_screenshot_bytes"),
            "max_screenshot_width": artifact_policy.get("max_screenshot_width"),
            "max_screenshot_height": artifact_policy.get("max_screenshot_height"),
            "full_content_in_events": artifact_policy.get("full_content_in_events", False),
            "full_content_in_read_model": artifact_policy.get("full_content_in_read_model", False),
        },
    }


def _screen_target_selector_from_payload(value: object) -> ScreenTargetSelector:
    if not isinstance(value, dict):
        raise ValueError("screen target_selector must be a dict")
    selector = value.get("selector")
    if not isinstance(selector, dict):
        raise ValueError("screen target_selector.selector must be a dict")
    return ScreenTargetSelector(kind=value.get("kind"), selector=dict(selector))


def _apply_target_allowlist(screen_grant: dict, target_allowlist: object) -> None:
    if target_allowlist is None:
        return
    if not isinstance(target_allowlist, dict):
        raise ValueError("screen target_allowlist must be a dict")
    allowed_apps = target_allowlist.get("allowed_apps", [])
    if not isinstance(allowed_apps, list):
        raise ValueError("screen target_allowlist.allowed_apps must be a list")
    allowed_titles = target_allowlist.get("allowed_title_contains", [])
    if not isinstance(allowed_titles, list):
        raise ValueError("screen target_allowlist.allowed_title_contains must be a list")
    screen_grant["target_selector_policy"] = {
        "allowed_apps": list(allowed_apps),
        "allowed_title_contains": list(allowed_titles),
        "allow_first_match_execute": target_allowlist.get("allow_first_match_execute") is True,
    }


def _target_policy_denial(
    target_selector: ScreenTargetSelector,
    target_policy: object,
) -> str | None:
    if not isinstance(target_policy, dict):
        raise ValueError("screen target_selector_policy must be a dict")
    allowed_apps = target_policy.get("allowed_apps", [])
    if not isinstance(allowed_apps, list):
        raise ValueError("screen target_selector_policy.allowed_apps must be a list")
    allowed_titles = target_policy.get("allowed_title_contains", [])
    if not isinstance(allowed_titles, list):
        raise ValueError("screen target_selector_policy.allowed_title_contains must be a list")
    app = target_selector.selector.get("app")
    if allowed_apps and app is not None and app not in allowed_apps:
        return "screen_target_not_allowed"
    title = target_selector.selector.get("title_contains")
    if allowed_titles and title is not None and title not in allowed_titles:
        return "screen_target_not_allowed"
    return None


def _screen_actions_from_payload(value: object) -> list[ScreenAction]:
    if not isinstance(value, list) or not value:
        raise ValueError("screen actions must be a non-empty list")
    return [ScreenAction.from_dict(action) for action in value]


def _action_policy_denial(
    *,
    execution_mode: str,
    actions: list[ScreenAction],
    action_policy: object,
) -> str | None:
    if not isinstance(action_policy, dict):
        raise ValueError("screen action_policy must be a dict")
    execution_modes = action_policy.get("execution_modes", [])
    if not isinstance(execution_modes, list):
        raise ValueError("screen action_policy.execution_modes must be a list")
    if execution_mode not in execution_modes and execution_mode != "execute":
        return "screen_execution_mode_not_allowed"
    max_actions = action_policy.get("max_actions", 0)
    if not isinstance(max_actions, int) or max_actions <= 0 or len(actions) > max_actions:
        return "screen_action_not_allowed"
    allowed_action_types = action_policy.get("allowed_action_types", [])
    if not isinstance(allowed_action_types, list):
        raise ValueError("screen action_policy.allowed_action_types must be a list")
    allowed_buttons = action_policy.get("allowed_buttons", [])
    if not isinstance(allowed_buttons, list):
        raise ValueError("screen action_policy.allowed_buttons must be a list")
    for action in actions:
        if action.type not in allowed_action_types:
            return "screen_action_not_allowed"
        if action.button is not None and action.button not in allowed_buttons:
            return "screen_action_not_allowed"
    return None


def _with_unique(values: list[str], value: str) -> list[str]:
    if value in values:
        return values
    return [*values, value]
