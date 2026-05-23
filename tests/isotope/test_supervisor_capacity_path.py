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
    assert loop["step_result"]["step"] == "call_capability"
    assert loop["step_result"]["status"] == "completed"
    assert loop["tick_policy_after"]["phase"] == "ready"
    assert loop["tick_policy_after"]["should_continue"] is True
    assert loop["tick_policy_after"]["must_stop_reason"] is None
    assert loop["handoff"] == {
        "initial_next_tick_kind": "planner_step",
        "post_step_phase": "ready",
        "post_step_should_continue": True,
        "post_step_stop_reason": None,
    }
    capability_run = loop["step_result"]["action_result"]["capability_run"]
    assert capability_run["capability_id"] == "artifact.review"
    assert capability_run["status"] == "completed"


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
    assert result["selection"]["capacity_id"] == "context.search"
    assert result["selection"]["status"] == "missing_inputs"
    assert result["selection"]["missing_inputs"] == ["query"]
    assert result["capacity_graph"]["status"] == "blocked"
    assert result["capacity_graph"]["summary"]["ready"] == 0
    assert result["capacity_graph"]["calls"] == []
    assert result["agent_loop"] is None


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
    assert result["selection"]["status"] == "ready_to_call"
    assert result["capacity_graph"]["status"] == "ready"
    assert result["capability_launch_plan"]["can_launch"] is False
    assert result["capability_launch_plan"]["status"] == "not_allowlisted"
    assert result["agent_loop"] is None


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
    assert "agent_loop_executed: True" in output
    assert "agent_loop_next_tick_kind: planner_step" in output
    assert "agent_loop_post_step_phase: ready" in output
    assert "agent_loop_post_step_should_continue: True" in output
    assert "agent_loop_post_step_stop_reason: None" in output
