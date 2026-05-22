from __future__ import annotations

import argparse
import inspect

from isotope.features.supervisor import runner
from isotope.features.supervisor.commands import capacity as capacity_command
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
    assert loop["step_result"]["step"] == "call_capability"
    assert loop["step_result"]["status"] == "completed"
    capability_run = loop["step_result"]["action_result"]["capability_run"]
    assert capability_run["capability_id"] == "artifact.review"
    assert capability_run["status"] == "completed"


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
