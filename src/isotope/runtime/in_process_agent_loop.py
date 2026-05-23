"""Agent-loop helpers for the in-process runtime facade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..agents.loop.control import build_agent_loop_control, build_agent_loop_tick_policy
from ..agents.loop.planner_adapter import run_agent_loop_planner_step
from ..agents.loop.planner_contract import run_agent_loop_real_planner_contract_step
from ..agents.loop.step import run_agent_loop_step
from ..platform.ids import new_id
from ..platform.schemas.actions import ActionExecution
from ..platform.schemas.memory import MemoryRecord


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

    def record_agent_loop_turn_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        run = self._runtime_context_for_write_helper(run_id)
        summary = self._dict_string(request, "summary")
        content = request.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("memory content must be a non-empty structured dict")
        scope = request.get("scope", "run")
        if scope not in {"thread", "run", "session"}:
            raise ValueError("memory scope must be thread, run, or session")
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

    def query_agent_loop_memory(self, run_id: str, request: dict[str, Any]) -> dict[str, Any]:
        self._validate_known_run_id(run_id)
        query = self._dict_string(request, "query")
        scope = request.get("scope")
        if scope is not None and scope not in {"thread", "run", "session"}:
            raise ValueError("memory query scope must be thread, run, or session")
        result = self.memory_query_service.query(
            run_id=run_id,
            query=query,
            scope=scope,
            grants={"memory": {"query": True}},
            caller_context={"run_id": run_id, "surface": "agent_loop"},
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
