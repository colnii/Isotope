from __future__ import annotations

import argparse
import inspect
import json

from isotope.features.supervisor import runner
from isotope.features.supervisor.commands import capacity as capacity_command
from isotope.capabilities.catalog import Capability, CapabilityCatalog
from isotope.capabilities.runner import CapabilityRunner
from isotope.llm.provider import LLMResponse


class FakeCapacityProvider:
    provider = "fake"
    model = "capacity-test"

    def __init__(self, content: str):
        self.content = content
        self.messages = []

    def generate(self, messages, *, max_tokens=512):
        self.messages.append(messages)
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.content,
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            raw={},
        )


def test_supervisor_capacity_plan_uses_capacity_calling_graph_and_capability_runner(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"artifact.review","arguments":{},"confidence":0.91,'
        '"rationale":"low risk review"}'
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="检查低敏 artifact review 能力是否可用",
        provider=provider,
        state_root=tmp_path / "state",
        execute_agent_loop=False,
    )

    assert result["status"] == "ok"
    assert result["status_reason"] == "ready"
    assert result["selection"]["kind"] == "capacity_call_selection"
    assert result["selection"]["capacity_id"] == "artifact.review"
    assert result["selection"]["status"] == "ready_to_call"
    assert result["capacity_graph"]["kind"] == "capacity_graph_plan"
    assert result["capacity_graph"]["status"] == "ready"
    assert result["capability_launch_plan"]["kind"] == "capability_launch_plan"
    assert result["capability_launch_plan"]["capability_id"] == "artifact.review"
    assert result["capability_launch_plan"]["can_launch"] is True
    assert result["agent_loop"] is None
    assert "artifact.review" in provider.messages[0][1]["content"]


def test_supervisor_capacity_plan_passes_selection_arguments_to_launch_plan(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text(
        "Supervisor request_context can retrieve project context.\n",
        encoding="utf-8",
    )
    codex_home = tmp_path / "codex-home"
    provider = FakeCapacityProvider(
        json.dumps(
            {
                "capacity_id": "supervisor.request_context",
                "arguments": {
                    "codex_home": str(codex_home),
                    "cwd": str(workspace),
                    "query": "request_context project context",
                    "max_results": 2,
                },
                "confidence": 0.91,
                "rationale": "needs existing project context",
            }
        )
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="搜索当前项目上下文",
        provider=provider,
        state_root=tmp_path / "state",
        execute_agent_loop=False,
    )

    assert result["status"] == "ok"
    assert result["selection"]["capacity_id"] == "supervisor.request_context"
    assert result["selection"]["arguments"]["query"] == "request_context project context"
    assert result["capability_launch_plan"]["capability_id"] == "supervisor.request_context"
    assert result["capability_launch_plan"]["can_launch"] is True
    assert result["capability_launch_plan"]["missing_inputs"] == []
    assert result["agent_loop"] is None


def test_supervisor_capacity_plan_can_execute_low_risk_agent_loop_step(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"artifact.review","arguments":{},"confidence":0.91,'
        '"rationale":"low risk review"}'
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="通过 agent loop 调用 artifact review 能力",
        provider=provider,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    loop = result["agent_loop"]
    assert loop["executed"] is True
    assert loop["tick_policy_before"]["should_continue"] is True
    assert loop["tick_policy_before"]["max_next_tick_kind"] == "planner_step"
    assert loop["planner_output_summary"] == {
        "planner_run_id": "supervisor_capacity:artifact.review",
        "selected_step": "call_capability",
        "capability_id": "artifact.review",
    }
    assert loop["tick_result"]["tick_status"] == "executed"
    assert loop["tick_result"]["planner_result"]["planner_status"] == "accepted"
    assert loop["tick_result"]["planner_result"]["selected_step"] == "call_capability"
    assert loop["tick_result"]["after_policy"]["tick_budget"] == {
        "max_ticks": 1,
        "ticks_used": 1,
        "remaining_ticks": 0,
        "budget_exhausted": True,
        "budget_basis": "supervisor_capacity:artifact.review",
    }
    step_result = loop["tick_result"]["planner_result"]["step_result"]
    assert step_result["step"] == "call_capability"
    assert step_result["status"] == "completed"
    assert loop["tick_policy_after"]["phase"] == "ready"
    assert loop["tick_policy_after"]["should_continue"] is True
    assert loop["tick_policy_after"]["must_stop_reason"] is None
    assert loop["handoff"] == {
        "initial_next_tick_kind": "planner_step",
        "post_step_phase": "ready",
        "post_step_should_continue": True,
        "post_step_stop_reason": None,
    }
    capability_run = step_result["action_result"]["capability_run"]
    assert capability_run["capability_id"] == "artifact.review"
    assert capability_run["status"] == "completed"


def test_supervisor_capacity_plan_reports_ready_supervisor_decision(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"artifact.review","arguments":{},"confidence":0.91,'
        '"rationale":"low risk review"}'
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="检查低敏 artifact review 能力是否可用",
        provider=provider,
        state_root=tmp_path / "state",
        execute_agent_loop=False,
    )

    assert result["supervisor_decision"] == {
        "kind": "supervisor_capacity_decision",
        "next_action": "call_capacity",
        "reason": "ready",
        "capacity_id": "artifact.review",
        "can_execute_agent_loop": True,
        "missing_inputs": [],
        "blocking_reasons": [],
    }


def test_supervisor_capacity_plan_only_offers_preflight_launchable_capabilities(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"artifact.review","arguments":{},"confidence":0.91,'
        '"rationale":"low risk review"}'
    )
    runner_with_unavailable_capabilities = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="artifact.review",
                    title="Artifact Review",
                    description="Review low-sensitive artifact summaries.",
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("artifact", "review"),
                    input_contract={"type": "object"},
                    output_contract={"type": "object"},
                    safety_boundaries=("low_sensitive_manifest_only",),
                ),
                Capability(
                    capability_id="llm.artifact.review",
                    title="LLM Artifact Review",
                    description="Provider-backed artifact review.",
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("artifact", "llm"),
                    input_contract={"type": "object"},
                    output_contract={"type": "object"},
                    safety_boundaries=("provider_required",),
                    required_env=("ISOTOPE_TEST_PROVIDER_KEY",),
                    network_required=True,
                    provider="test-provider",
                    model="test-model",
                ),
                Capability(
                    capability_id="context.search",
                    title="Context Search",
                    description="Deferred context search capability.",
                    maturity="v0.1",
                    shelf="product_candidate",
                    domain_tags=("context", "search"),
                    input_contract={"type": "object"},
                    output_contract={"type": "object"},
                    safety_boundaries=("low_sensitive_manifest_only",),
                ),
            ]
        )
    )

    capacity_command.build_supervisor_capacity_plan(
        goal="检查低敏 artifact review 能力是否可用",
        provider=provider,
        runner=runner_with_unavailable_capabilities,
        state_root=tmp_path / "state",
        execute_agent_loop=False,
    )

    offered_payload = json.loads(provider.messages[0][1]["content"])
    offered_ids = [
        capacity["capacity_id"] for capacity in offered_payload["capacities"]
    ]
    assert offered_ids == ["artifact.review"]


def test_supervisor_capacity_plan_blocks_when_no_capabilities_can_be_offered(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"llm.artifact.review","arguments":{},"confidence":0.91,'
        '"rationale":"provider required"}'
    )
    runner_with_unavailable_capability = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="llm.artifact.review",
                    title="LLM Artifact Review",
                    description="Provider-backed artifact review.",
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("artifact", "llm"),
                    input_contract={"type": "object"},
                    output_contract={"type": "object"},
                    safety_boundaries=("provider_required",),
                    required_env=("ISOTOPE_TEST_PROVIDER_KEY",),
                    network_required=True,
                    provider="test-provider",
                    model="test-model",
                )
            ]
        )
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="检查 provider-backed 能力",
        provider=provider,
        runner=runner_with_unavailable_capability,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    assert provider.messages == []
    assert result["status"] == "blocked"
    assert result["status_reason"] == "no_offered_capacities"
    assert result["capacity_blocked_reason"] == "no_offered_capacities"
    assert result["selection"] is None
    assert result["capacity_graph"]["status"] == "blocked"
    assert result["capability_launch_plan"] is None
    assert result["agent_loop"] is None
    assert result["supervisor_decision"] == {
        "kind": "supervisor_capacity_decision",
        "next_action": "blocked",
        "reason": "no_offered_capacities",
        "capacity_id": "unknown",
        "can_execute_agent_loop": False,
        "missing_inputs": [],
        "blocking_reasons": ["no_offered_capacities"],
    }


def test_execute_capacity_action_requires_matching_ready_decision(tmp_path, monkeypatch):
    calls: list[object] = []

    def fake_execute_agent_loop_capacity_step(**kwargs):
        calls.append(kwargs)
        raise AssertionError("stale capacity call spec must not execute")

    monkeypatch.setattr(
        capacity_command,
        "_execute_agent_loop_capacity_step",
        fake_execute_agent_loop_capacity_step,
    )

    result = capacity_command.execute_capacity_action(
        argparse.Namespace(codex_home=str(tmp_path / ".codex")),
        {
            "kind": "call_capacity",
            "capacity_id": "artifact.review",
            "reason": "stale spec",
        },
        {
            "capacity_call_specs": [
                {
                    "capacity_id": "artifact.review",
                    "goal": "检查 artifact review 能力。",
                    "inputs": {},
                }
            ],
            "capacity_decisions": [],
        },
    )

    assert result == {
        "kind": "call_capacity",
        "capacity_id": "artifact.review",
        "skipped": True,
        "reason": "capacity decision not ready",
    }
    assert calls == []


def test_capacity_call_specs_require_ready_plan_status():
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "call_capacity",
        "reason": "ready",
        "capacity_id": "artifact.review",
        "can_execute_agent_loop": True,
        "missing_inputs": [],
        "blocking_reasons": [],
    }
    plan = {
        "status": "blocked",
        "status_reason": "not_launchable",
        "selection": {
            "capacity_id": "artifact.review",
            "arguments": {"path": "notes.md"},
        },
        "supervisor_decision": decision,
    }

    assert capacity_command.capacity_call_specs(plan, goal="检查 artifact") == []

    plan["status"] = "ok"
    plan["status_reason"] = "ready"

    assert capacity_command.capacity_call_specs(plan, goal="检查 artifact") == [
        {
            "capacity_id": "artifact.review",
            "goal": "检查 artifact",
            "inputs": {"path": "notes.md"},
        }
    ]


def test_capacity_call_specs_require_launchable_capability_plan():
    plan = {
        "status": "ok",
        "status_reason": "ready",
        "selection": {
            "capacity_id": "context.search",
            "arguments": {"query": "capacity"},
        },
        "capability_launch_plan": {
            "capability_id": "context.search",
            "can_launch": False,
            "status": "not_allowlisted",
        },
        "supervisor_decision": {
            "kind": "supervisor_capacity_decision",
            "next_action": "call_capacity",
            "reason": "ready",
            "capacity_id": "context.search",
            "can_execute_agent_loop": True,
            "missing_inputs": [],
            "blocking_reasons": [],
        },
    }

    assert capacity_command.capacity_call_specs(plan, goal="搜索项目文档") == []


def test_supervisor_capacity_plan_passes_arguments_into_agent_loop_inputs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.md").write_text(
        "Supervisor request_context can retrieve capacity arguments.\n",
        encoding="utf-8",
    )
    provider = FakeCapacityProvider(
        '{"capacity_id":"supervisor.request_context","arguments":{'
        f'"codex_home":"{tmp_path / "codex-home"}",'
        f'"cwd":"{workspace}",'
        '"query":"capacity arguments",'
        '"max_results":1'
        '},"confidence":0.88,"rationale":"need context"}'
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="通过 agent loop 调用带参数的 request_context 能力",
        provider=provider,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    assert result["status"] == "ok"
    assert result["capability_launch_plan"]["can_launch"] is True
    assert result["capacity_graph"]["calls"][0]["arguments"]["query"] == "capacity arguments"
    loop = result["agent_loop"]
    assert loop["step_request"] == {
        "step": "call_capability",
        "capability_id": "supervisor.request_context",
        "inputs": {
            "codex_home": str(tmp_path / "codex-home"),
            "cwd": str(workspace),
            "query": "capacity arguments",
            "max_results": 1,
        },
    }
    capability_run = loop["step_result"]["action_result"]["capability_run"]
    assert capability_run["capability_id"] == "supervisor.request_context"
    assert capability_run["status"] == "completed"
    assert capability_run["context_result"]["query"] == "capacity arguments"
    assert capability_run["context_result"]["item_count"] >= 1


def test_supervisor_capacity_plan_blocks_missing_inputs_without_graph_call_or_execution(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"context.search","arguments":{},"confidence":0.77,'
        '"rationale":"needs query"}'
    )
    runner_with_required_input = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="context.search",
                    title="Context Search",
                    description="Search project context.",
                    maturity="v0.1",
                    shelf="product_candidate",
                    domain_tags=("context", "search"),
                    input_contract={
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                    output_contract={"type": "object"},
                    safety_boundaries=("low_sensitive_manifest_only",),
                )
            ]
        )
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="搜索项目文档，但用户没有提供 query",
        provider=provider,
        runner=runner_with_required_input,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    assert result["status"] == "needs_input"
    assert result["status_reason"] == "needs_input"
    assert result["capacity_blocked_reason"] == "missing_inputs"
    assert result["selection"]["capacity_id"] == "context.search"
    assert result["selection"]["status"] == "missing_inputs"
    assert result["selection"]["missing_inputs"] == ["query"]
    assert result["capacity_graph"]["status"] == "blocked"
    assert result["capacity_graph"]["summary"]["ready"] == 0
    assert result["capacity_graph"]["calls"] == []
    assert result["agent_loop"] is None
    assert result["supervisor_decision"] == {
        "kind": "supervisor_capacity_decision",
        "next_action": "request_input",
        "reason": "needs_input",
        "capacity_id": "context.search",
        "can_execute_agent_loop": False,
        "missing_inputs": ["query"],
        "blocking_reasons": [],
    }


def test_supervisor_capacity_plan_does_not_execute_unlaunchable_capacity(tmp_path):
    provider = FakeCapacityProvider(
        '{"capacity_id":"context.search","arguments":{"query":"capacity"},'
        '"confidence":0.77,"rationale":"not allowlisted"}'
    )
    runner_with_deferred_capability = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="context.search",
                    title="Context Search",
                    description="Search project context.",
                    maturity="v0.1",
                    shelf="product_candidate",
                    domain_tags=("context", "search"),
                    input_contract={
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                    output_contract={"type": "object"},
                    safety_boundaries=("low_sensitive_manifest_only",),
                )
            ]
        )
    )

    result = capacity_command.build_supervisor_capacity_plan(
        goal="搜索项目文档",
        provider=provider,
        runner=runner_with_deferred_capability,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    assert result["status"] == "blocked"
    assert result["status_reason"] == "not_launchable"
    assert result["capacity_blocked_reason"] == "not_allowlisted"
    assert result["selection"]["status"] == "ready_to_call"
    assert result["capacity_graph"]["status"] == "ready"
    assert result["capability_launch_plan"]["can_launch"] is False
    assert result["capability_launch_plan"]["status"] == "not_allowlisted"
    assert result["agent_loop"] is None
    assert result["supervisor_decision"] == {
        "kind": "supervisor_capacity_decision",
        "next_action": "blocked",
        "reason": "not_launchable",
        "capacity_id": "context.search",
        "can_execute_agent_loop": False,
        "missing_inputs": [],
        "blocking_reasons": ["not_allowlisted"],
    }


def test_supervisor_capacity_command_handler_is_thin_and_runner_delegates():
    args = argparse.Namespace(
        capacity_command="plan",
        goal="检查 artifact review",
        state_root=None,
        execute_agent_loop=False,
        json=True,
    )

    source = inspect.getsource(capacity_command.handle_capacity_command)
    assert "select_capacity_call" not in source
    assert "CapacityRunner" not in source
    assert runner._COMMAND_HANDLERS["capacity"] is capacity_command.handle_capacity_command
    assert capacity_command.handle_capacity_command(
        args,
        provider=FakeCapacityProvider(
            '{"capacity_id":"artifact.review","arguments":{},"confidence":0.91,'
            '"rationale":"low risk review"}'
        ),
    ) == 0

def test_supervisor_capacity_command_handler_prints_json_status_reason(capsys):
    args = argparse.Namespace(
        capacity_command="plan",
        goal="搜索项目文档",
        state_root=None,
        execute_agent_loop=True,
        json=True,
    )
    runner_with_deferred_capability = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="context.search",
                    title="Context Search",
                    description="Search project context.",
                    maturity="v0.1",
                    shelf="product_candidate",
                    domain_tags=("context", "search"),
                    input_contract={
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                    output_contract={"type": "object"},
                    safety_boundaries=("low_sensitive_manifest_only",),
                )
            ]
        )
    )

    exit_code = capacity_command.handle_capacity_command(
        args,
        provider=FakeCapacityProvider(
            '{"capacity_id":"context.search","arguments":{"query":"capacity"},'
            '"confidence":0.77,"rationale":"not allowlisted"}'
        ),
        runner=runner_with_deferred_capability,
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["status_reason"] == "not_launchable"
    assert payload["agent_loop"] is None


def test_loop_capacity_payload_explains_no_offered_capacities():
    decision = {
        "kind": "supervisor_capacity_decision",
        "next_action": "blocked",
        "reason": "no_offered_capacities",
        "capacity_id": "unknown",
        "can_execute_agent_loop": False,
        "missing_inputs": [],
        "blocking_reasons": ["no_offered_capacities"],
    }

    class FakeCapacityApi:
        def resolve_capacity_calling_provider_from_env(self):
            return object()

        def build_supervisor_capacity_plan(self, **kwargs):
            return {
                "status": "blocked",
                "status_reason": "no_offered_capacities",
                "supervisor_decision": decision,
            }

    payload = capacity_command.loop_capacity_decision_payload(
        argparse.Namespace(capacity_decisions=True),
        active_goals=[{"goal": "检查 provider-backed 能力"}],
        explicit_goal=None,
        api=FakeCapacityApi(),
    )

    assert payload["status"] == "blocked"
    assert payload["reason"] == "no_offered_capacities"
    assert payload["capacity_blocked_reason"] == "no_offered_capacities"
    assert payload["capacity_decisions"] == [decision]
    assert payload["capacity_call_specs"] == []


def test_supervisor_capacity_plain_output_includes_agent_loop_handoff(tmp_path, capsys):
    args = argparse.Namespace(
        capacity_command="plan",
        goal="检查 artifact review",
        state_root=str(tmp_path / "state"),
        execute_agent_loop=True,
        json=False,
    )

    assert capacity_command.handle_capacity_command(
        args,
        provider=FakeCapacityProvider(
            '{"capacity_id":"artifact.review","arguments":{},"confidence":0.91,'
            '"rationale":"low risk review"}'
        ),
    ) == 0

    output = capsys.readouterr().out
    assert "supervisor_decision_next_action: call_capacity" in output
    assert "agent_loop_executed: True" in output
    assert "agent_loop_next_tick_kind: planner_step" in output
    assert "agent_loop_planner_selected_step: call_capability" in output
    assert "agent_loop_tick_status: executed" in output
    assert "agent_loop_tick_after_stop_reason: tick_budget_exhausted" in output
    assert "agent_loop_artifact_ref: artifact_" in output
    assert "agent_loop_post_step_phase: ready" in output
    assert "agent_loop_post_step_should_continue: True" in output
    assert "agent_loop_post_step_stop_reason: None" in output


def test_supervisor_capacity_plain_output_explains_missing_inputs(capsys):
    args = argparse.Namespace(
        capacity_command="plan",
        goal="搜索项目上下文但缺少参数",
        state_root=None,
        execute_agent_loop=True,
        json=False,
    )

    assert capacity_command.handle_capacity_command(
        args,
        provider=FakeCapacityProvider(
            json.dumps(
                {
                    "capacity_id": "supervisor.request_context",
                    "arguments": {},
                    "confidence": 0.74,
                    "rationale": "needs context",
                }
            )
        ),
    ) == 0

    output = capsys.readouterr().out
    assert "capacity_id: supervisor.request_context" in output
    assert "selection_status: missing_inputs" in output
    assert "status_reason: needs_input" in output
    assert "capacity_blocked_reason: missing_inputs" in output
    assert "capacity_missing_inputs: codex_home, cwd, query" in output
    assert "agent_loop_executed: False" in output


def test_supervisor_capacity_plain_output_explains_no_offered_capacities(
    tmp_path, capsys
):
    runner_with_unavailable_capability = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="llm.artifact.review",
                    title="LLM Artifact Review",
                    description="Provider-backed artifact review.",
                    maturity="v0.2",
                    shelf="product_candidate",
                    domain_tags=("artifact", "llm"),
                    input_contract={"type": "object"},
                    output_contract={"type": "object"},
                    safety_boundaries=("provider_required",),
                    required_env=("ISOTOPE_TEST_PROVIDER_KEY",),
                    network_required=True,
                    provider="test-provider",
                    model="test-model",
                )
            ]
        )
    )
    payload = capacity_command.build_supervisor_capacity_plan(
        goal="检查 provider-backed 能力",
        provider=FakeCapacityProvider(
            '{"capacity_id":"llm.artifact.review","arguments":{},'
            '"confidence":0.91,"rationale":"provider required"}'
        ),
        runner=runner_with_unavailable_capability,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    capacity_command._print_capacity_plan_plain(payload)

    output = capsys.readouterr().out
    assert "capacity_id: unknown" in output
    assert "selection_status: unknown" in output
    assert "status_reason: no_offered_capacities" in output
    assert "capacity_blocked_reason: no_offered_capacities" in output
    assert "agent_loop_executed: False" in output


def test_supervisor_capacity_plain_output_explains_not_launchable(tmp_path, capsys):
    provider = FakeCapacityProvider(
        '{"capacity_id":"context.search","arguments":{"query":"capacity"},'
        '"confidence":0.77,"rationale":"not allowlisted"}'
    )
    runner_with_deferred_capability = CapabilityRunner(
        catalog=CapabilityCatalog(
            capabilities=[
                Capability(
                    capability_id="context.search",
                    title="Context Search",
                    description="Search project context.",
                    maturity="v0.1",
                    shelf="product_candidate",
                    domain_tags=("context", "search"),
                    input_contract={
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                    output_contract={"type": "object"},
                    safety_boundaries=("low_sensitive_manifest_only",),
                )
            ]
        )
    )
    payload = capacity_command.build_supervisor_capacity_plan(
        goal="搜索项目文档",
        provider=provider,
        runner=runner_with_deferred_capability,
        state_root=tmp_path / "state",
        execute_agent_loop=True,
    )

    capacity_command._print_capacity_plan_plain(payload)

    output = capsys.readouterr().out
    assert "capacity_id: context.search" in output
    assert "selection_status: ready_to_call" in output
    assert "status_reason: not_launchable" in output
    assert "capacity_blocked_reason: not_allowlisted" in output
    assert "launch_status: not_allowlisted" in output
    assert "launch_blocking_reasons: not_allowlisted" in output
    assert "agent_loop_executed: False" in output
