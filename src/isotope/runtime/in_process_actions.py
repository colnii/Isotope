"""Action submission helpers for the in-process runtime facade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..platform.ids import new_id
from ..platform.schemas.actions import PolicyDecision


class InProcessActionMixin:
    """Submit, retry, cancel, and supersede runtime actions."""

    def submit_input(
        self,
        run_id: str,
        text: str,
        *,
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        return self.submit_tool_request(
            run_id,
            tool="write_artifact_tool",
            text=text,
            requires_approval=requires_approval,
        )

    def submit_action(
        self,
        run_id: str,
        intent: dict[str, Any],
        requires_approval: bool = False,
        complete_run: bool = True,
    ) -> dict[str, Any]:
        self._validate_action_intent(intent)
        return self._submit_action_internal(
            run_id,
            deepcopy(intent),
            requires_approval=requires_approval,
            complete_run=complete_run,
        )

    def get_model_tool_catalog(self) -> dict[str, Any]:
        return self.registry.model_tool_catalog()

    def submit_tool_request(
        self,
        run_id: str,
        tool: str,
        text: str,
        requires_approval: bool = False,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("tool", tool)
        self._validate_non_empty_string("text", text)
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a bool")

        return self._submit_action_internal(
            run_id,
            {
                "action": "call_tool",
                "tool": tool,
                "text": text,
                "requested_tools": [tool],
            },
            requires_approval=requires_approval,
        )

    def request_retry(
        self,
        run_id: str,
        *,
        basis_execution_id: str,
        reason: str,
        requested_by: str,
        replacement_intent: dict[str, Any],
        explicit_rerun: bool = False,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("basis_execution_id", basis_execution_id)
        self._validate_non_empty_string("reason", reason)
        self._validate_non_empty_string("requested_by", requested_by)
        self._validate_action_intent(replacement_intent)
        if not isinstance(explicit_rerun, bool):
            raise ValueError("explicit_rerun must be a bool")

        state = self.get_run_state(run_id)
        action = self._require_execution_action(state, basis_execution_id)
        basis_status = action.get("status")
        if basis_status == "completed" and not explicit_rerun:
            raise ValueError("completed action retry requires explicit rerun")
        if basis_status not in {"failed", "completed"}:
            raise ValueError(f"retry requires failed execution or explicit rerun; basis status was {basis_status}")

        original_proposal_id = self._require_action_proposal_id(action)
        retry_id = new_id("retry")
        replacement_proposal_id = new_id("prop")
        replacement_execution_id = new_id("exec")
        request_payload: dict[str, Any] = {
            "retry_id": retry_id,
            "run_id": run_id,
            "original_proposal_id": original_proposal_id,
            "original_execution_id": basis_execution_id,
            "reason": reason,
            "requested_by": requested_by,
        }
        if explicit_rerun:
            request_payload["explicit_rerun"] = True
        request_event = self._append(run_id, "action.retry_requested", request_payload)
        self._append(
            run_id,
            "action.retry_created",
            {
                "retry_id": retry_id,
                "new_proposal_id": replacement_proposal_id,
                "new_execution_id": replacement_execution_id,
                "original_proposal_id": original_proposal_id,
                "basis_event_id": request_event.event_id,
                "policy_basis": {
                    "decision_id": action.get("decision_id"),
                    "mode": "replacement_reference",
                },
            },
        )
        return {
            "status": "created",
            "retry_id": retry_id,
            "basis_execution_id": basis_execution_id,
            "basis_proposal_id": original_proposal_id,
            "replacement_proposal_id": replacement_proposal_id,
            "replacement_execution_id": replacement_execution_id,
            "basis_event_id": request_event.event_id,
        }

    def request_cancel(
        self,
        run_id: str,
        *,
        reason: str,
        requested_by: str,
        basis_proposal_id: str | None = None,
        basis_execution_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("reason", reason)
        self._validate_non_empty_string("requested_by", requested_by)
        if basis_execution_id is None and basis_proposal_id is None:
            raise ValueError("cancel requires basis_execution_id or basis_proposal_id")

        state = self.get_run_state(run_id)
        execution_id = ""
        if basis_execution_id is not None:
            self._validate_non_empty_string("basis_execution_id", basis_execution_id)
            action = self._require_execution_action(state, basis_execution_id)
            basis_status = str(action.get("status", ""))
            if basis_status in {"completed", "failed", "denied", "cancelled", "superseded"}:
                raise ValueError(f"cannot cancel terminal action with status {basis_status}")
            if basis_status != "running":
                raise ValueError(f"cancel requires running or pending action; basis status was {basis_status}")
            proposal_id = self._require_action_proposal_id(action)
            execution_id = basis_execution_id
        else:
            self._validate_non_empty_string("basis_proposal_id", basis_proposal_id)
            proposal_id = str(basis_proposal_id)
            action = state.actions.get(proposal_id)
            if action is None:
                raise ValueError("unknown proposal basis")
            basis_status = str(action.get("status", ""))
            if basis_status != "pending_user_approval":
                raise ValueError(f"cancel requires running or pending action; basis status was {basis_status}")

        cancel_id = new_id("cancel")
        payload: dict[str, Any] = {
            "cancel_id": cancel_id,
            "run_id": run_id,
            "proposal_id": proposal_id,
            "reason": reason,
            "requested_by": requested_by,
            "logical_only": True,
            "process_kill": False,
        }
        if execution_id:
            payload["execution_id"] = execution_id
        event = self._append(run_id, "action.cancel_requested", payload)
        return {
            "status": "cancel_requested",
            "cancel_id": cancel_id,
            "basis_proposal_id": proposal_id,
            "basis_execution_id": execution_id or None,
            "basis_event_id": event.event_id,
            "logical_only": True,
            "process_kill": False,
        }

    def request_supersede(
        self,
        run_id: str,
        *,
        old_proposal_id: str,
        reason: str,
        requested_by: str,
        old_execution_id: str | None = None,
        replacement_intent: dict[str, Any] | None = None,
        replacement_proposal_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_existing_run_id(run_id)
        self._validate_non_empty_string("old_proposal_id", old_proposal_id)
        self._validate_non_empty_string("reason", reason)
        self._validate_non_empty_string("requested_by", requested_by)
        if replacement_intent is None and replacement_proposal_id is None:
            raise ValueError("supersede requires replacement intent or replacement proposal identity")
        if replacement_intent is not None:
            self._validate_action_intent(replacement_intent)
        if replacement_proposal_id is not None:
            self._validate_non_empty_string("replacement_proposal_id", replacement_proposal_id)

        state = self.get_run_state(run_id)
        action = state.actions.get(old_proposal_id)
        if old_execution_id is not None:
            self._validate_non_empty_string("old_execution_id", old_execution_id)
            action = self._require_execution_action(state, old_execution_id)
            if action.get("proposal_id") != old_proposal_id:
                raise ValueError("supersede basis proposal does not match execution")
        if action is None:
            raise ValueError("unknown proposal basis")

        basis_event = self._find_action_started_event(run_id, old_proposal_id)
        if basis_event is None:
            raise ValueError("supersede basis requires started action")

        supersession_id = new_id("supersede")
        new_proposal_id = replacement_proposal_id or new_id("prop")
        new_execution_id = new_id("exec")
        self._append(
            run_id,
            "action.superseded",
            {
                "supersession_id": supersession_id,
                "old_proposal_id": old_proposal_id,
                "old_execution_id": old_execution_id,
                "new_proposal_id": new_proposal_id,
                "new_execution_id": new_execution_id,
                "reason": reason,
                "reason_code": "superseded_by_replacement",
                "requested_by": requested_by,
                "basis_event_id": basis_event.event_id,
                "provenance": {
                    "requested_by": requested_by,
                    "basis_event_id": basis_event.event_id,
                },
            },
        )
        return {
            "status": "created",
            "supersession_id": supersession_id,
            "old_proposal_id": old_proposal_id,
            "old_execution_id": old_execution_id,
            "replacement_proposal_id": new_proposal_id,
            "replacement_execution_id": new_execution_id,
            "reason_code": "superseded_by_replacement",
            "basis_event_id": basis_event.event_id,
        }

    def _submit_action_internal(
        self,
        run_id: str,
        intent: dict[str, Any],
        requires_approval: bool,
        complete_run: bool = True,
    ) -> dict[str, Any]:
        if not isinstance(requires_approval, bool):
            raise ValueError("requires_approval must be a bool")
        if not isinstance(complete_run, bool):
            raise ValueError("complete_run must be a bool")

        run = self._runtime_context_for_write_helper(run_id)
        proposal = self.compiler.compile(
            intent,
            {
                "run_id": run_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
                "requires_approval": requires_approval,
            },
        )
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal.proposal_id,
                "agent_id": proposal.agent_id,
                "thread_id": proposal.thread_id,
                "action_type": proposal.action_type,
                "registry_id": proposal.registry_id,
                "registry_version": proposal.registry_version,
                "registry_basis": proposal.registry_basis,
                "requested_action_summary": self._requested_action_summary(proposal),
            },
        )

        decision = self.policy.decide(proposal)
        if requires_approval and decision.outcome != "denied":
            decision = PolicyDecision(
                decision_id=new_id("dec"),
                proposal_id=proposal.proposal_id,
                outcome="pending_user_approval",
                grants=decision.grants,
                reason_codes=["approval_required"],
                policy_profile_id=decision.policy_profile_id,
                policy_version=decision.policy_version,
            )
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision.decision_id,
                "proposal_id": decision.proposal_id,
                "outcome": decision.outcome,
                "reason_codes": list(decision.reason_codes),
                "policy_profile_id": decision.policy_profile_id,
                "policy_version": decision.policy_version,
                "policy_basis": decision.policy_basis,
            },
        )
        result_base = {
            "proposal_id": proposal.proposal_id,
            "decision_id": decision.decision_id,
            "decision": decision,
        }

        if decision.outcome == "denied":
            return {
                **result_base,
                "status": "denied",
                "execution": None,
                "run_state": self.get_run_state(run_id),
            }
        if decision.outcome == "pending_user_approval":
            approval_id = new_id("approval")
            payload_ref = self._store_pending_approval_payload(
                run_id,
                approval_id,
                proposal.payload,
            )
            self._append(
                run_id,
                "approval.requested",
                {
                    "approval_id": approval_id,
                    "run_id": run_id,
                    "proposal_id": proposal.proposal_id,
                    "decision_id": decision.decision_id,
                    "action_type": proposal.action_type,
                    "resolution_context": {
                        "complete_run": complete_run,
                        "proposal": {
                            "proposal_id": proposal.proposal_id,
                            "run_id": proposal.run_id,
                            "agent_id": proposal.agent_id,
                            "thread_id": proposal.thread_id,
                            "action_type": proposal.action_type,
                            "payload_ref": payload_ref,
                            "requested_capabilities": deepcopy(proposal.requested_capabilities),
                            "registry_id": proposal.registry_id,
                            "registry_version": proposal.registry_version,
                        },
                        "decision": {
                            "decision_id": decision.decision_id,
                            "proposal_id": decision.proposal_id,
                            "outcome": decision.outcome,
                            "grants": deepcopy(decision.grants),
                            "reason_codes": list(decision.reason_codes),
                            "policy_profile_id": decision.policy_profile_id,
                            "policy_version": decision.policy_version,
                        },
                    },
                },
            )
            self._pending_approvals[approval_id] = {
                "run_id": run_id,
                "proposal": proposal,
                "decision": decision,
                "complete_run": complete_run,
            }
            return {
                **result_base,
                "status": "pending_user_approval",
                "approval_id": approval_id,
                "execution": None,
                "run_state": self.get_run_state(run_id),
            }

        try:
            execution = self.executor.execute(decision, proposal)
        except Exception as exc:
            execution_id = self._latest_failed_execution_id(
                run_id,
                proposal_id=proposal.proposal_id,
                decision_id=decision.decision_id,
            )
            if not execution_id:
                raise RuntimeError("executor failed without action.failed event") from exc
            return {
                **result_base,
                "status": "failed",
                "execution": None,
                "execution_id": execution_id,
                "run_state": self.get_run_state(run_id),
            }

        if complete_run:
            self._append(run_id, "run.completed", {"status": "completed"})

        state = self.get_run_state(run_id)
        result = {
            **result_base,
            "status": state.status,
            "tool_execution_status": "completed",
            "run_state": state,
            "execution_id": execution.execution_id,
        }
        artifact_ref = self._completed_artifact_ref(run_id, execution.execution_id)
        if artifact_ref is not None:
            result["artifact_ref"] = artifact_ref
        return result

    def _requested_action_summary(self, proposal) -> dict[str, Any]:
        summary: dict[str, Any] = {"action_type": proposal.action_type}
        tool_name = proposal.payload.get("tool")
        if tool_name == "terminal_exec":
            summary["tool"] = tool_name
            argv = proposal.payload.get("argv")
            if isinstance(argv, list) and argv and isinstance(argv[0], str):
                summary["terminal_command"] = argv[0]
                summary["argv_count"] = len(argv)
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
        return summary


    def _validate_action_intent(self, intent: object) -> None:
        if not isinstance(intent, dict):
            raise ValueError("intent must be a dict")
        if not intent:
            raise ValueError("intent must be a non-empty dict")
