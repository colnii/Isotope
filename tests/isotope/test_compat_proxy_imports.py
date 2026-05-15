import importlib

import pytest


ATTRIBUTE_PROXIES = (
    ("isotope.agent_loop_control", "isotope.agents.loop.control", "build_agent_loop_control"),
    ("isotope.agent_loop_planner_adapter", "isotope.agents.loop.planner_adapter", "run_agent_loop_planner_step"),
    ("isotope.agent_loop_step", "isotope.agents.loop.step", "run_agent_loop_step"),
    ("isotope.assistant.loop_control", "isotope.agents.loop.control", "build_agent_loop_control"),
    ("isotope.assistant.loop_planner_adapter", "isotope.agents.loop.planner_adapter", "run_agent_loop_planner_step"),
    ("isotope.assistant.loop_step", "isotope.agents.loop.step", "run_agent_loop_step"),
    ("isotope.assistant.real_planner_contract", "isotope.agents.loop.planner_contract", "run_agent_loop_real_planner_contract_step"),
    ("isotope.capability_catalog", "isotope.capabilities.catalog", "CapabilityCatalog"),
    ("isotope.capability_runner", "isotope.capabilities.runner", "CapabilityRunner"),
    ("isotope.codex_cli", "isotope.integrations.codex.cli", "CodexCliBackend"),
    ("isotope.codex_live_smoke", "isotope.integrations.codex.live_smoke", "run_codex_live_smoke"),
    ("isotope.codex_server", "isotope.integrations.codex.server", "create_codex_cli_server"),
    ("isotope.codex_task", "isotope.integrations.codex.task", "CodexTaskAdapter"),
    ("isotope.core.loop_control", "isotope.agents.loop.control", "build_agent_loop_control"),
    ("isotope.core.loop_planner_adapter", "isotope.agents.loop.planner_adapter", "run_agent_loop_planner_step"),
    ("isotope.core.loop_step", "isotope.agents.loop.step", "run_agent_loop_step"),
    ("isotope.core.real_planner_contract", "isotope.agents.loop.planner_contract", "run_agent_loop_real_planner_contract_step"),
    ("isotope.execution.terminal_backend", "isotope.execution.terminal_runner", "TerminalBackendAdapter"),
    ("isotope.real_planner_adapter_contract", "isotope.agents.loop.planner_contract", "run_agent_loop_real_planner_contract_step"),
    ("isotope.terminal", "isotope.capabilities.tools.terminal", "ControlledTerminalRunner"),
    ("isotope.terminal_backend", "isotope.execution.terminal_runner", "TerminalBackendAdapter"),
    ("isotope.terminal_system_runner", "isotope.execution.terminal_runner", "LinuxSystemTerminalRunner"),
)


REMOVED_PROXIES = (
    "isotope.action_compiler",
    "isotope.action_registry",
    "isotope.agent_runtime",
    "isotope.artifact_store",
    "isotope.assistant.runtime",
    "isotope.checkpoint_store",
    "isotope.core.runtime",
    "isotope.executor",
    "isotope.event_schema",
    "isotope.event_store",
    "isotope.events",
    "isotope.errors",
    "isotope.features.chat.product_chat",
    "isotope.http_api",
    "isotope.ids",
    "isotope.ingestion",
    "isotope.integrations.llm",
    "isotope.integrations.llm.provider",
    "isotope.integrations.llm.tool_bridge",
    "isotope.llm_product_chat_app",
    "isotope.llm_provider",
    "isotope.model_tool_bridge",
    "isotope.models",
    "isotope.projector",
    "isotope.refs",
    "isotope.retrieval",
    "isotope.runtime.server",
    "isotope.server",
    "isotope.tool_protocol",
)


@pytest.mark.parametrize(("legacy_path", "target_path", "attribute"), ATTRIBUTE_PROXIES)
def test_compat_proxy_reexports_key_attribute(legacy_path, target_path, attribute):
    legacy = importlib.import_module(legacy_path)
    target = importlib.import_module(target_path)

    assert getattr(legacy, attribute) is getattr(target, attribute)


@pytest.mark.parametrize("module_path", REMOVED_PROXIES)
def test_removed_compat_proxies_are_not_importable(module_path):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_path)
