import isotope.demo.format.format as demo_format
from isotope.demo.format import agent_loop as demo_format_agent_loop
from isotope.demo.format import core as demo_format_core
from isotope.demo.format import llm as demo_format_llm


def test_demo_format_facade_uses_scenario_formatter_modules():
    assert (
        demo_format._format_agent_loop_tick_policy_trace_plain_text
        is demo_format_agent_loop._format_agent_loop_tick_policy_trace_plain_text
    )
    assert (
        demo_format._format_llm_provider_route_plain_text
        is demo_format_llm._format_llm_provider_route_plain_text
    )
    assert (
        demo_format._format_project_workspace_plain_text
        is demo_format_core._format_project_workspace_plain_text
    )
