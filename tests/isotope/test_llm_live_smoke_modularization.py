import isotope.llm_live_smoke as llm_live_smoke
from isotope import llm_live_smoke_config
from isotope import llm_live_smoke_runs


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
