import isotope.demo.llm_live_smoke as llm_live_smoke
from isotope.demo import llm_live_smoke_config
from isotope.demo import llm_live_smoke_cli_support
from isotope.demo import llm_live_smoke_diagnosis
from isotope.demo import llm_live_smoke_product_chat_entry_state
from isotope.demo import llm_live_smoke_runs
from isotope.demo import llm_live_smoke_terminal_diagnosis


def test_llm_live_smoke_facade_preserves_config_exports():
    assert llm_live_smoke.LLMToolCallLiveSmokeConfig is llm_live_smoke_config.LLMToolCallLiveSmokeConfig
    assert llm_live_smoke.DeepSeekToolCallLiveSmokeConfig is llm_live_smoke_config.DeepSeekToolCallLiveSmokeConfig
    assert (
        llm_live_smoke.LLMTerminalToolLiveSmokeConfig
        is llm_live_smoke_config.LLMTerminalToolLiveSmokeConfig
    )
    assert (
        llm_live_smoke.LLMProductChatLiveSmokeConfig
        is llm_live_smoke_config.LLMProductChatLiveSmokeConfig
    )


def test_llm_live_smoke_facade_preserves_run_exports():
    assert llm_live_smoke.run_llm_tool_call_live_smoke is llm_live_smoke_runs.run_llm_tool_call_live_smoke
    assert (
        llm_live_smoke.run_llm_terminal_tool_live_smoke
        is llm_live_smoke_runs.run_llm_terminal_tool_live_smoke
    )
    assert (
        llm_live_smoke.run_llm_product_chat_live_smoke
        is llm_live_smoke_runs.run_llm_product_chat_live_smoke
    )
    assert (
        llm_live_smoke.diagnose_llm_product_chat_live_smoke
        is llm_live_smoke_runs.diagnose_llm_product_chat_live_smoke
    )


def test_llm_live_smoke_diagnosis_reexports_terminal_diagnosis_helpers():
    assert (
        llm_live_smoke_diagnosis._llm_terminal_tool_diagnosis_for
        is llm_live_smoke_terminal_diagnosis._llm_terminal_tool_diagnosis_for
    )
    assert (
        llm_live_smoke_diagnosis._llm_terminal_tool_preflight_for
        is llm_live_smoke_terminal_diagnosis._llm_terminal_tool_preflight_for
    )
    assert (
        llm_live_smoke_diagnosis._maybe_diagnose_terminal_tool_missing_configuration
        is llm_live_smoke_terminal_diagnosis._maybe_diagnose_terminal_tool_missing_configuration
    )
    assert (
        llm_live_smoke_diagnosis._terminal_error_reason_summary
        is llm_live_smoke_terminal_diagnosis._terminal_error_reason_summary
    )


def test_llm_live_smoke_cli_support_reexports_product_chat_entry_state_helpers():
    assert (
        llm_live_smoke_cli_support._maybe_write_product_chat_entry_state
        is llm_live_smoke_product_chat_entry_state._maybe_write_product_chat_entry_state
    )
    assert (
        llm_live_smoke_cli_support._load_product_chat_entry_state
        is llm_live_smoke_product_chat_entry_state._load_product_chat_entry_state
    )
    assert (
        llm_live_smoke_cli_support._mark_product_chat_entry_state_resumed
        is llm_live_smoke_product_chat_entry_state._mark_product_chat_entry_state_resumed
    )
    assert (
        llm_live_smoke_cli_support._product_chat_entry_error_payload
        is llm_live_smoke_product_chat_entry_state._product_chat_entry_error_payload
    )
