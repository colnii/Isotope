# Social QQ Reply Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect `persona_instructions` and `chat_context` to actual social
reply generation instead of keeping QQ replies as a fixed text template.

**Architecture:** Keep `SocialDecisionLoop` responsible for wake/silence,
sticker preference, and arbiter selection. Add a `SocialReplyProvider` boundary
for text replies:

- `DeterministicSocialReplyProvider` preserves current deterministic behavior
  and adds reply-provider metadata for audit.
- `LLMSocialReplyProvider` renders markdown-backed prompts with
  `persona_instructions` and `chat_context`, calls an existing chat provider,
  and parses a JSON reply draft.
- QQ runtime config `runtime.reply_provider = "llm"` enables the LLM reply path
  through the existing LLM provider resolver. Missing LLM configuration is a
  clear runtime error, not a hidden fallback.

---

### Task 1: Reply Provider Boundary

**Files:**
- Modify: `tests/unit/features/social/test_social_decision_loop.py`
- Create: `src/isotope/features/social/reply_provider.py`
- Modify: `src/isotope/features/social/loop.py`
- Modify: `src/isotope/features/social/__init__.py`

- [x] **Step 1: Write red test**

Assert that `SocialDecisionLoop` passes the full decision request and wake reason
to a reply provider, and uses the provider's reply text and metadata in the
`reply_text` candidate.

- [x] **Step 2: Implement provider contract**

Add `SocialReplyDraft`, `SocialReplyProvider`, and
`DeterministicSocialReplyProvider`. Wire the deterministic provider into
`SocialDecisionLoop` by default.

### Task 2: LLM Reply Provider

**Files:**
- Create: `tests/unit/features/social/test_social_reply_provider.py`
- Modify: `src/isotope/features/social/reply_provider.py`
- Modify: `src/isotope/llm/prompts/__init__.py`
- Create: `src/isotope/llm/prompts/social_reply.md`
- Create: `src/isotope/llm/prompts/social_reply_user.md`
- Modify: `tests/unit/llm/test_system_prompt_assets.py`

- [x] **Step 1: Write red test**

Assert that the LLM provider prompt contains wake reason, persona instructions,
chat context, and a required JSON shape.

- [x] **Step 2: Implement LLM provider**

Use existing prompt loading/rendering and chat provider `generate(...)`. Parse
only JSON object output with a non-empty `text` field.

### Task 3: QQ Runtime Config

**Files:**
- Modify: `tests/unit/features/social/test_social_runner.py`
- Modify: `src/isotope/features/social/qq_runtime_commands.py`

- [x] **Step 1: Write red test**

Set `runtime.reply_provider` to `llm`, monkeypatch the existing LLM resolver,
and assert that `qq dry-run` proposes the LLM-generated text.

- [x] **Step 2: Wire runtime**

Build `SocialDecisionLoop(reply_provider=LLMSocialReplyProvider(...))` when the
runtime config selects `llm`; otherwise keep deterministic behavior.

### Task 4: Verification

- [x] **Step 1: Final verification**

Run:

```bash
PYTHONPATH=src /home/lumber/Github/isotope/.venv/bin/python -m pytest tests/unit/features/social/test_social_decision_loop.py tests/unit/features/social/test_social_reply_provider.py tests/unit/features/social/test_social_runner.py tests/unit/features/social tests/unit/llm/test_system_prompt_assets.py tests/unit/integrations/qq/test_onebot_adapter.py tests/unit/integrations/qq/test_onebot_ws_client.py tests/integration/social/test_qq_runtime_wiring.py tests/integration/social/test_social_fake_platform_flow.py tests/integration/qq/test_fake_onebot_flow.py tests/unit/docs/test_qq_group_chatbot_docs.py -q
git diff --check
```

Expected: tests pass and whitespace check has no output.

### Acceptance Standard

- Default QQ/social decisions keep the old deterministic reply text.
- A custom reply provider can generate the text candidate from the full
  persona/chat context.
- `runtime.reply_provider = "llm"` enables LLM-generated text through the
  existing provider resolver.
- LLM prompts are markdown assets, and model output is constrained to JSON with a
  non-empty text field.
