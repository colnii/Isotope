import importlib

import pytest


MODULE_ALIASES = (
    ("isotope.action_compiler", "isotope.runtime.action_compiler"),
    ("isotope.artifact_store", "isotope.workspace.artifacts"),
    ("isotope.checkpoint_store", "isotope.platform.state.checkpoint_store"),
    ("isotope.event_schema", "isotope.platform.events.event_schema"),
    ("isotope.event_store", "isotope.platform.state.event_store"),
    ("isotope.events", "isotope.platform.events.events"),
    ("isotope.ids", "isotope.platform.ids"),
    ("isotope.ingestion", "isotope.rag.ingestion"),
    ("isotope.models", "isotope.platform.schemas.models"),
    ("isotope.projector", "isotope.platform.state.projector"),
    ("isotope.refs", "isotope.platform.schemas.refs"),
    ("isotope.retrieval", "isotope.rag.retrieval"),
    ("isotope.server", "isotope.runtime.in_process"),
    ("isotope.tool_protocol", "isotope.platform.schemas.tool_protocol"),
)


ATTRIBUTE_PROXIES = (
    ("isotope.action_registry", "isotope.platform.registry.actions", "ActionTypeRegistry"),
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
    ("isotope.errors", "isotope.platform.errors", "IsotopeError"),
    ("isotope.execution.terminal_backend", "isotope.execution.terminal_runner", "TerminalBackendAdapter"),
    ("isotope.executor", "isotope.execution.executor", "Executor"),
    ("isotope.features.chat.product_chat", "isotope.features.chat.flow", "submit_llm_product_chat_user_message_with_preflight"),
    ("isotope.http_api", "isotope.interfaces.http", "create_http_app"),
    ("isotope.integrations.llm.provider", "isotope.llm.provider", "LLMToolCall"),
    ("isotope.integrations.llm.tool_bridge", "isotope.llm.tool_bridge", "submit_model_tool_call"),
    ("isotope.llm_product_chat_app", "isotope.features.chat.flow", "submit_llm_product_chat_user_message_with_preflight"),
    ("isotope.llm_provider", "isotope.llm.provider", "LLMToolCall"),
    ("isotope.model_tool_bridge", "isotope.llm.tool_bridge", "submit_model_tool_call"),
    ("isotope.real_planner_adapter_contract", "isotope.agents.loop.planner_contract", "run_agent_loop_real_planner_contract_step"),
    ("isotope.terminal", "isotope.capabilities.tools.terminal", "ControlledTerminalRunner"),
    ("isotope.terminal_backend", "isotope.execution.terminal_runner", "TerminalBackendAdapter"),
    ("isotope.terminal_system_runner", "isotope.execution.terminal_runner", "LinuxSystemTerminalRunner"),
)


REMOVED_EMPTY_PROXIES = (
    "isotope.agent_runtime",
    "isotope.assistant.runtime",
    "isotope.core.runtime",
)


@pytest.mark.parametrize(("legacy_path", "target_path"), MODULE_ALIASES)
def test_compat_module_alias_points_to_target_module(legacy_path, target_path):
    legacy = importlib.import_module(legacy_path)
    target = importlib.import_module(target_path)

    assert legacy is target


@pytest.mark.parametrize(("legacy_path", "target_path", "attribute"), ATTRIBUTE_PROXIES)
def test_compat_proxy_reexports_key_attribute(legacy_path, target_path, attribute):
    legacy = importlib.import_module(legacy_path)
    target = importlib.import_module(target_path)

    assert getattr(legacy, attribute) is getattr(target, attribute)


@pytest.mark.parametrize("module_path", REMOVED_EMPTY_PROXIES)
def test_empty_runtime_compat_proxies_are_removed(module_path):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_path)
