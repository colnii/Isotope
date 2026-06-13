# QQ Mimo Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let QQ social runtime use the Mimo entry already present in the local TOML LLM pool without pretending Mimo is DeepSeek.

**Architecture:** Extend shared chat-provider resolution to optionally read TOML pool entries and select an OpenAI-compatible provider by `ISOTOPE_LLM_PROVIDER`. QQ keeps using `resolve_llm_chat_provider()`, so QQ-specific runtime code stays thin. Reuse `resolve_pool_entries_from_env()` and `create_chat_provider_from_pool_entry()`; do not add a Mimo-specific client.

**Tech Stack:** Python 3.13, pytest, existing `isotope.llm.pool`, existing OpenAI-compatible provider factory, QQ social runtime.

---

### Task 1: Add pool-backed chat provider resolution

**Files:**
- Modify: `src/isotope/llm/provider/resolution.py`
- Modify: `tests/unit/llm/test_llm_provider.py`

- [ ] **Step 1: Write failing resolver tests**

Add tests proving `ISOTOPE_LLM_PROVIDER=mimo` resolves from a TOML pool and missing pool entries produce `llm_provider_unsupported`.

- [ ] **Step 2: Run red test**

Run: `/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/llm/test_llm_provider.py::test_resolve_chat_provider_can_select_openai_compatible_pool_entry_by_provider -q`

Expected: fail because `resolve_llm_chat_provider()` currently returns `llm_provider_unsupported` for `mimo`.

- [ ] **Step 3: Implement minimal resolver support**

In `resolution.py`, add pool imports and a helper that reads `ISOTOPE_LLM_POOL_TOML_FILES` or default supervisor pool TOML, filters by normalized provider name, and builds a provider via `create_chat_provider_from_pool_entry()`.

- [ ] **Step 4: Run resolver tests**

Run: `/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/llm/test_llm_provider.py -q`

Expected: pass.

### Task 2: Prove QQ LLM config accepts Mimo

**Files:**
- Modify: `tests/unit/features/social/decision/test_social_qq_llm_participation_config.py`

- [ ] **Step 1: Write failing QQ config test**

Add a test that monkeypatches the QQ resolver to a Mimo-like configured provider and asserts `decision_loop_from_config()` builds both LLM participation and reply providers.

- [ ] **Step 2: Run red or confirm existing QQ contract**

Run: `/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/decision/test_social_qq_llm_participation_config.py -q`

Expected: pass if QQ already delegates cleanly to shared resolver; otherwise fail on provider wiring.

- [ ] **Step 3: Keep QQ runtime unchanged unless the test exposes a real gap**

If the test passes, do not edit `qq_runtime_commands.py`.

### Task 3: Document local Mimo setup and verify

**Files:**
- Modify: `docs/current/qq-group-chatbot.md`
- Modify: `docs/current/qq-group-chatbot-operations.md`

- [ ] **Step 1: Update docs with minimal Mimo/TOML setup**

Document `ISOTOPE_LLM_PROVIDER=mimo` plus `SUPERVISOR_LLM_POOL_TOML_FILES` or the default `supervisor_llm_pool.toml`, and state that real QQ still needs NapCat/OneBot on `ws://127.0.0.1:3001`.

- [ ] **Step 2: Run focused verification**

Run:
`/home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/llm/test_llm_provider.py tests/unit/features/social/decision/test_social_qq_llm_participation_config.py tests/unit/features/social/decision/test_llm_participation_provider.py tests/unit/features/social/test_social_reply_provider.py -q`

Run:
`ISOTOPE_QQ_REAL_SMOKE_CONFIG=/tmp/isotope-missing-qq-real-smoke.toml PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/integrations/qq/test_onebot_adapter.py tests/integration/qq/test_fake_onebot_flow.py -q`

Expected: all pass except the intentionally skipped real QQ smoke.
