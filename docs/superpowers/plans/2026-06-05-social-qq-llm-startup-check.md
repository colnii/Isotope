# Social QQ LLM Startup Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated QQ beta/profile packs explicitly expose the reply
provider setting, and make startup-check verify LLM reply configuration before a
real beta session can run with `runtime.reply_provider = "llm"`.

**Architecture:** Keep deterministic replies as the default because they keep
replay output stable. Treat `runtime.reply_provider` as a normal runtime config
field:

- generated beta packs write `runtime.reply_provider = "deterministic"`;
- profile docs explain how to switch a beta pack to `llm`;
- startup-check always reports `llm_reply_provider`;
- `llm_reply_provider` passes for deterministic mode and resolves the shared
  Isotope LLM provider for LLM mode.

---

### Task 1: Red Tests

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`

- [x] **Step 1: Beta/profile config tests**

Assert that generated beta configs include `runtime.reply_provider =
"deterministic"`, profile docs explain the optional LLM switch, and
`apply-profile` preserves the runtime config.

- [x] **Step 2: Startup gate tests**

Assert startup-check reports an `llm_reply_provider` check and blocks when the
beta config selects `llm` but the shared LLM provider resolver reports missing
configuration.

### Task 2: Implementation

**Files:**
- Modify: `src/isotope/features/social/beta_pack.py`
- Modify: `src/isotope/features/social/profile_pack.py`
- Modify: `src/isotope/features/social/startup_gate.py`

- [x] **Step 1: Write runtime config**

Add `runtime.reply_provider = "deterministic"` to generated beta pack config.

- [x] **Step 2: Document optional LLM switch**

Add beta/profile README guidance for switching to `runtime.reply_provider =
"llm"` and running startup-check.

- [x] **Step 3: Add startup gate check**

Add `llm_reply_provider` to startup-check. Deterministic mode passes without
model configuration; LLM mode calls `resolve_llm_chat_provider()`.

### Task 3: Verification

- [x] **Step 1: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/unit/llm/test_system_prompt_assets.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Generated beta configs make reply-provider mode visible.
- `startup-check` blocks LLM reply mode when the LLM provider is not configured.
- Deterministic reply mode remains the default and keeps existing replay flow
  stable.
- Operator docs explain exactly how to switch to LLM and what check enforces it.
