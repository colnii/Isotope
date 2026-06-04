"""Agent-loop helpers for the in-process runtime facade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ...agents.loop.control import build_agent_loop_control, build_agent_loop_tick_policy
from ...agents.loop.conversation import arbitrate_agent_conversation_turn
from ...agents.loop.planner_adapter import run_agent_loop_planner_step
from ...agents.loop.planner_contract import run_agent_loop_real_planner_contract_step
from ...agents.loop.provider_planner import run_agent_loop_provider_planner_tick
from ...agents.loop.runner import run_agent_loop_until_stop
from ...agents.loop.step import run_agent_loop_step
from ...agents.loop.tick import run_agent_loop_tick
from ...platform.ids import new_id
from ...platform.schemas.actions import ActionExecution
from ...platform.schemas.memory import MemoryRecord


class InProcessAgentLoopMixin:
    """Expose agent-loop control, memory, and planner steps."""

    def get_agent_loop_control(self, run_id: str) -> dict[str, Any]:
        return build_agent_loop_control(self.get_run_state(run_id))

    def get_agent_loop_tick_policy(
        self,
        run_id: str,
        *,
        tick_budget: dict[str, Any] | None = None,
        user_pause: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_agent_loop_tick_policy(
            self.get_agent_loop_control(run_id),
            tick_budget=tick_budget,
            user_pause=user_pause,
        )

    def run_agent_loop_step(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return run_agent_loop_step(self, run_id, request)

    def run_agent_loop_tick(
        self,
        run_id: str,
        planner_output: dict[str, Any] | None,
        *,
        tick_budget: dict[str, Any] | None = None,
        user_pause: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return run_agent_loop_tick(
            self,
            run_id,
            planner_output,
            tick_budget=tick_budget,
            user_pause=user_pause,
        )

    def run_agent_loop_until_stop(
        self,
        run_id: str,
        *,
        planner: Any,
        max_ticks: int,
        budget_basis: str | None = None,
        user_pause: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return run_agent_loop_until_stop(
            self,
            run_id,
            planner=planner,
            max_ticks=max_ticks,
            budget_basis=budget_basis,
            user_pause=user_pause,
        )

    def arbitrate_agent_conversation_turn(
        self,
        candidates: Any,
        *,
        turn_id: str,
        max_visible_messages: int,
    ) -> dict[str, Any]:
        return arbitrate_agent_conversation_turn(
            candidates,
            turn_id=turn_id,
            max_visible_messages=max_visible_messages,
        )

    def run_agent_loop_provider_planner_tick(
        self,
        run_id: str,
        *,
        provider: Any,
        agent_id: str,
        tick_id: str,
        decision_id: str,
        tick_budget: dict[str, Any] | None = None,
        user_pause: dict[str, Any] | None = None,
        default_context_extra: dict[str, Any] | None = None,
        capability_system_inputs: dict[str, Any] | None = None,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        return run_agent_loop_provider_planner_tick(
            self,
            run_id,
            provider=provider,
            agent_id=agent_id,
            tick_id=tick_id,
            decision_id=decision_id,
            tick_budget=tick_budget,
            user_pause=user_pause,
            default_context_extra=default_context_extra,
            capability_system_inputs=capability_system_inputs,
            max_tokens=max_tokens,
        )

    def record_agent_loop_turn_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        run = self._runtime_context_for_write_helper(run_id)
        summary = self._dict_string(request, "summary")
        content = request.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("memory content must be a non-empty structured dict")
        scope = request.get("scope", "run")
        if scope not in {"thread", "run", "session"}:
            raise ValueError("memory scope must be thread, run, or session")
        if scope == "session":
            raise ValueError("session memory must be promoted with promote_run_memory")
        source_refs = request.get("source_refs", [])
        if not isinstance(source_refs, list):
            raise ValueError("memory source_refs must be a list")
        supersedes = request.get("supersedes", [])
        if not isinstance(supersedes, list):
            raise ValueError("memory supersedes must be a list")
        quality = request.get("quality", "candidate")
        if not isinstance(quality, str) or not quality:
            raise ValueError("memory quality must be a non-empty string")

        proposal_id = new_id("prop")
        decision_id = new_id("dec")
        execution_id = new_id("exec")
        grants = {
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "budget": {"seconds": 30},
        }
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
                "action_type": "write_memory",
                "registry_id": "agent_loop_memory",
                "registry_version": "v0.2",
                "requested_action_summary": {"action_type": "write_memory"},
            },
        )
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "outcome": "approved",
                "grants": deepcopy(grants),
                "reason_codes": [],
                "policy_profile_id": self.policy.policy_profile_id,
                "policy_version": self.policy.policy_version,
                "policy_basis": {
                    "policy_profile_id": self.policy.policy_profile_id,
                    "policy_version": self.policy.policy_version,
                    "mode": "agent_loop_turn_memory",
                },
            },
        )
        self._append(
            run_id,
            "action.started",
            {
                "execution_id": execution_id,
                "proposal_id": proposal_id,
                "decision_id": decision_id,
            },
        )
        completed = self._append(
            run_id,
            "action.completed",
            {
                "execution_id": execution_id,
                "status": "completed",
                "artifact_refs": [],
            },
        )
        record = MemoryRecord(
            memory_id=new_id("mem"),
            scope=scope,
            content=deepcopy(content),
            summary=summary,
            source_refs=[dict(ref) for ref in source_refs],
            provenance={
                "run_id": run_id,
                "session_id": run["session_id"],
                "execution_id": execution_id,
                "action_type": "write_memory",
            },
            created_at="2026-04-27T00:00:00Z",
            supersedes=[str(record_id) for record_id in supersedes],
            quality=quality,
        )
        memory_event = self._build_event(
            run_id,
            "memory.record_created",
            {
                "record_id": record.memory_id,
                "execution_id": execution_id,
                "summary": record.summary,
                "source_refs": [dict(ref) for ref in record.source_refs],
                "provenance": dict(record.provenance),
                "basis_event_id": completed.event_id,
                "quality": record.quality,
            },
        )
        self._project_with_candidate(run_id, memory_event)
        execution = ActionExecution(
            execution_id=execution_id,
            proposal_id=proposal_id,
            decision_id=decision_id,
            action_type="write_memory",
            status="completed",
            effective_grants_snapshot=deepcopy(grants),
        )
        self.memory_store.save_record(record, execution=execution, grants=grants)
        appended = self.event_store.append(memory_event)
        return {
            "step_status": "completed",
            "status": "completed",
            "record_id": record.memory_id,
            "execution_id": execution_id,
            "basis_event_id": appended.event_id,
            "summary": record.summary,
            "scope": record.scope,
            "source_refs": [dict(ref) for ref in record.source_refs],
            "provenance": dict(record.provenance),
            "quality": record.quality,
        }

    def promote_agent_loop_run_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        run = self._runtime_context_for_write_helper(run_id)
        source_record_id = self._dict_string(request, "source_record_id")
        reason = self._dict_string(request, "reason")
        source_record = self.memory_store.load_record(source_record_id)
        if source_record is None:
            raise ValueError("source memory record not found")
        if source_record.scope != "run":
            raise ValueError("only run memory can be promoted to session memory")
        if source_record.provenance.get("run_id") != run_id:
            raise ValueError("source memory record must belong to the current run")

        summary_value = request.get("summary", source_record.summary)
        if not isinstance(summary_value, str) or not summary_value.strip():
            raise ValueError("summary must be a non-empty string")
        quality_value = request.get("quality", source_record.quality)
        if not isinstance(quality_value, str) or not quality_value.strip():
            raise ValueError("memory quality must be a non-empty string")
        supersedes = request.get("supersedes", [])
        if not isinstance(supersedes, list):
            raise ValueError("memory supersedes must be a list")

        proposal_id = new_id("prop")
        decision_id = new_id("dec")
        execution_id = new_id("exec")
        grants = {
            "tools": ["write_memory"],
            "workspace": {"mode": "shared_ro"},
            "memory": {
                "promotion": True,
                "from_scope": "run",
                "to_scope": "session",
            },
            "budget": {"seconds": 30},
        }
        self._append(
            run_id,
            "action.proposed",
            {
                "proposal_id": proposal_id,
                "agent_id": run["agent_id"],
                "thread_id": run["thread_id"],
                "action_type": "write_memory",
                "registry_id": "agent_loop_memory_promotion",
                "registry_version": "v0.2",
                "requested_action_summary": {
                    "action_type": "write_memory",
                    "promotion": "run_to_session",
                    "source_record_id": source_record.memory_id,
                },
            },
        )
        self._append(
            run_id,
            "action.decided",
            {
                "decision_id": decision_id,
                "proposal_id": proposal_id,
                "outcome": "approved",
                "grants": deepcopy(grants),
                "reason_codes": [],
                "policy_profile_id": self.policy.policy_profile_id,
                "policy_version": self.policy.policy_version,
                "policy_basis": {
                    "policy_profile_id": self.policy.policy_profile_id,
                    "policy_version": self.policy.policy_version,
                    "mode": "agent_loop_memory_promotion",
                },
            },
        )
        self._append(
            run_id,
            "action.started",
            {
                "execution_id": execution_id,
                "proposal_id": proposal_id,
                "decision_id": decision_id,
            },
        )
        completed = self._append(
            run_id,
            "action.completed",
            {
                "execution_id": execution_id,
                "status": "completed",
                "artifact_refs": [],
            },
        )
        record = MemoryRecord(
            memory_id=new_id("mem"),
            scope="session",
            content=deepcopy(source_record.content),
            summary=summary_value.strip(),
            source_refs=[dict(ref) for ref in source_record.source_refs],
            provenance={
                "run_id": run_id,
                "session_id": run["session_id"],
                "execution_id": execution_id,
                "action_type": "write_memory",
                "promotion_source_record_id": source_record.memory_id,
                "promotion_source_scope": source_record.scope,
            },
            created_at="2026-04-27T00:00:00Z",
            supersedes=[str(record_id) for record_id in supersedes],
            quality=quality_value.strip(),
        )
        memory_event = self._build_event(
            run_id,
            "memory.record_created",
            {
                "record_id": record.memory_id,
                "execution_id": execution_id,
                "summary": record.summary,
                "source_refs": [dict(ref) for ref in record.source_refs],
                "provenance": dict(record.provenance),
                "basis_event_id": completed.event_id,
                "quality": record.quality,
            },
        )
        self._project_with_candidate(run_id, memory_event)
        execution = ActionExecution(
            execution_id=execution_id,
            proposal_id=proposal_id,
            decision_id=decision_id,
            action_type="write_memory",
            status="completed",
            effective_grants_snapshot=deepcopy(grants),
        )
        self.memory_store.save_record(record, execution=execution, grants=grants)
        appended = self.event_store.append(memory_event)
        return {
            "step_status": "completed",
            "status": "completed",
            "record_id": record.memory_id,
            "execution_id": execution_id,
            "basis_event_id": appended.event_id,
            "summary": record.summary,
            "scope": record.scope,
            "source_refs": [dict(ref) for ref in record.source_refs],
            "provenance": dict(record.provenance),
            "quality": record.quality,
            "promotion": {
                "source_record_id": source_record.memory_id,
                "source_scope": source_record.scope,
                "target_scope": "session",
                "reason": reason,
            },
        }

    def query_agent_loop_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        self._validate_known_run_id(run_id)
        query = self._dict_string(request, "query")
        scope = request.get("scope")
        if scope is not None and scope not in {"thread", "run", "session"}:
            raise ValueError("memory query scope must be thread, run, or session")
        control = self.get_agent_loop_control(run_id)
        session_id = control.get("session_id") if scope == "session" else None
        controlled_expand = _memory_query_controlled_expand(request)
        grants: dict[str, Any] = {"memory": {"query": True}}
        if controlled_expand:
            memory_grants = grants["memory"]
            memory_grants["controlled_expand"] = True
            if "expand_budget" in request:
                memory_grants["expand_budget"] = request["expand_budget"]
            elif "budget" in request:
                memory_grants["budget"] = request["budget"]
        result = self.memory_query_service.query(
            run_id=run_id,
            query=query,
            scope=scope,
            session_id=session_id if isinstance(session_id, str) and session_id else None,
            grants=grants,
            caller_context={
                "run_id": run_id,
                "session_id": session_id,
                "caller": "agent_loop",
                "purpose": "agent_recall",
            },
            controlled_expand=controlled_expand,
        )
        return {"step_status": "completed", **result}

    def run_agent_loop_planner_step(self, run_id: str, planner_output: dict[str, Any]) -> dict[str, Any]:
        return run_agent_loop_planner_step(self, run_id, planner_output)

    def run_agent_loop_real_planner_contract_step(
        self,
        run_id: str,
        provider_result: dict[str, Any],
    ) -> dict[str, Any]:
        return run_agent_loop_real_planner_contract_step(self, run_id, provider_result)


def _memory_query_controlled_expand(request: dict[str, Any]) -> bool:
    value = request.get("controlled_expand", False)
    if not isinstance(value, bool):
        raise ValueError("controlled_expand must be a boolean")
    return value
